import json
from collections.abc import Iterator
from mimetypes import guess_type
from minio import Minio
from minio.deleteobjects import DeleteObject
from utils.logging_utils import logger
from utils.net_utils import probe_tcp
from common.config.env_config import ENV_CONFIG

# 入库的相对代理路径前缀 (upload_file 返回形态, docs_service 读回时去除)
_PROXY_FILES_PREFIX = "/api/files/"


class MiniRagMinioClient:
    def __init__(self):
        """只保存配置并构建惰性客户端, 不做任何网络请求。

        bucket 的创建放到了 prepare_bucket() 里, 由启动自检 (api/startup_checks.py)
        或 reset_db.py 显式调用: 若在 __init__ 里连网, MinIO 未启动时
        import common.client 就会直接抛异常, 自检流程根本来不及报告。
        """
        self.bucket_name = ENV_CONFIG.minio.bucket_name
        self.endpoint = ENV_CONFIG.minio.endpoint
        self.access_key = ENV_CONFIG.minio.access_key
        self.secret_key = ENV_CONFIG.minio.secret_key
        self.secure = ENV_CONFIG.minio.secure

        self._minio = Minio(
            endpoint=self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
        )

    def check_health(self) -> None:
        """连通性自检: TCP 可达 + list_buckets 能正常返回。"""
        probe_tcp(self.endpoint)
        buckets = self._minio.list_buckets()
        logger.success(f"MinIO 连接成功 ({self.endpoint}), bucket 数: {len(buckets)}")

    def prepare_bucket(self):
        """准备 bucket: 不存在则创建, 并设置匿名只读策略。

        不放在 __init__ 里 (构造必须无网络副作用), 由启动自检
        (api/startup_checks.py) 与 tools/reset_db.py 在需要时显式调用。
        """
        if self._minio.bucket_exists(self.bucket_name):
            logger.info(f"MinIO bucket '{self.bucket_name}' 已存在")
            return

        self._minio.make_bucket(self.bucket_name)
        logger.success(f"MinIO bucket '{self.bucket_name}' 创建成功")
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                # Statement 中每一条字典记录了一条规则
                {
                    # 这条规则是 允许 ｜ 拒绝
                    "Effect": "Allow",
                    # 这条规则对谁生效
                    "Principal": {"AWS": "*"},
                    # 允许或拒绝的操作
                    "Action": "s3:GetObject",
                    # 涉及到的资源
                    "Resource": f"arn:aws:s3:::{self.bucket_name}/*",
                },
            ],
        }
        self._minio.set_bucket_policy(self.bucket_name, json.dumps(policy))

    def clear_dir_if_exist(self, prefix: str) -> int:
        """
        清除路径下的所有文件(保留文件夹)
        Args:
            prefix: 路径(文件夹) 例如:"upload-images/hak180产品安全手册"
        Returns:
            成功删除的元素个数
        """
        objects = self._minio.list_objects(
            bucket_name=self.bucket_name, prefix=prefix, recursive=True
        )
        delete_objects = [DeleteObject(obj.object_name) for obj in objects]
        delete_cnt = len(delete_objects)
        errors = self._minio.remove_objects(
            bucket_name=self.bucket_name,
            delete_object_list=delete_objects,
        )
        # 删除逻辑放在了迭代器的 __next__ 方法中
        # 所以要想办法调用 errors 的迭代器
        # 在这个迭代器或者说生成器中，只有删除失败才会“生成”元素
        for error in errors:
            delete_cnt -= 1
            logger.info(f"删除失败 {error}")

        return delete_cnt

    def doc_artifact_prefix(self, doc_dir: str, file_title: str) -> str:
        """某文档单份制品在 MinIO 上的路径前缀: <doc_dir>/<file_title>。

        对象路径统一为 <dir>/<file_title>/<文件名>, 不含 task_id 层级
        (V1-7), 同名覆盖导入时单一前缀即可覆盖全部历史制品。
        """
        return f"{doc_dir}/{file_title}"

    def clear_doc_artifacts(self, file_title: str) -> int:
        """递归清理该文档的三份制品目录 (origin / markdown / chunks)。

        前缀带尾斜杠精确匹配到目录, 避免 file_title 前缀相似的兄弟文档
        被误删; 幂等, 目录不存在时返回 0。
        """
        doc_dirs = (
            ENV_CONFIG.minio.origin_dir,
            ENV_CONFIG.minio.markdown_dir,
            ENV_CONFIG.minio.chunks_dir,
        )
        total = 0
        for doc_dir in doc_dirs:
            prefix = f"{doc_dir}/{file_title}/"
            del_cnt = self.clear_dir_if_exist(prefix)
            total += del_cnt
            if del_cnt:
                logger.info(f"MinIO 制品清理: {prefix} 删除 {del_cnt} 个对象")
        return total

    def clear_doc_images(self, file_title: str) -> int:
        """递归清理该文档的图片目录 (markdown-images/<file_title>/)。

        与三份制品分开封装: 删除文档时需一并清理, 否则图片成孤儿对象。
        幂等, 目录不存在时返回 0。
        """
        prefix = f"{ENV_CONFIG.minio.image_dir}/{file_title}/"
        del_cnt = self.clear_dir_if_exist(prefix)
        if del_cnt:
            logger.info(f"MinIO 图片清理: {prefix} 删除 {del_cnt} 个对象")
        return del_cnt

    def remove_bucket(self) -> int:
        """删除 bucket 中的所有对象后删除 bucket，返回成功删除的对象数。

        幂等: bucket 已不存在时直接跳过 (连续执行 reset 不应报错)。
        """
        if not self._minio.bucket_exists(self.bucket_name):
            logger.info(f"MinIO bucket '{self.bucket_name}' 不存在, 跳过删除")
            return 0

        objects = self._minio.list_objects(bucket_name=self.bucket_name, recursive=True)
        delete_objects = [DeleteObject(obj.object_name) for obj in objects]

        if delete_objects:
            errors = list(
                self._minio.remove_objects(
                    bucket_name=self.bucket_name,
                    delete_object_list=delete_objects,
                )
            )
            if errors:
                details = "; ".join(
                    f"{error.object_name}: {error.message}" for error in errors
                )
                raise RuntimeError(f"MinIO 对象删除失败，未删除 bucket: {details}")

        self._minio.remove_bucket(self.bucket_name)
        return len(delete_objects)

    def upload_file(self, prefix: str, as_name: str, file_path: str) -> str:
        """上传一个文件

        Args:
            prefix: 云端路径 (带或不带尾斜杠均可, 拼接时统一归一)
            as_name: 云端文件名
            file_path: 本地文件路径
        Returns:
            相对代理路径 /api/files/<object_name> (浏览器经前端同源入口访问,
            入库即代理地址, 运行时零改写)
        """
        # 归一化尾斜杠: 调用侧前缀带尾斜杠 (如 {dir}/{file_title}/) 时不产生双斜杠
        object_name = f"{prefix.rstrip('/')}/{as_name}"

        res = self._minio.fput_object(
            bucket_name=self.bucket_name,
            object_name=object_name,
            file_path=file_path,
            content_type=guess_type(file_path)[0],
        )

        from rich import print as rprint

        rprint(res)

        return f"{_PROXY_FILES_PREFIX}{object_name}"

    def get_object_stream(self, object_name: str) -> tuple[str, Iterator[bytes]]:
        """流式读取一个对象, 供 FastAPI StreamingResponse 使用。

        stat_object 在返回前同步执行 (对象不存在时立即抛 S3Error,
        调用侧可据此返回 404), get_object 响应按 chunk 惰性迭代。

        Returns:
            (content_type, 字节块生成器)
        """
        stat = self._minio.stat_object(
            bucket_name=self.bucket_name, object_name=object_name
        )
        response = self._minio.get_object(
            bucket_name=self.bucket_name, object_name=object_name
        )

        def _iter_chunks() -> Iterator[bytes]:
            try:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                response.close()
                response.release_conn()

        return stat.content_type or "application/octet-stream", _iter_chunks()


if __name__ == "__main__":
    from rich import print as rprint

    client = MiniRagMinioClient()
    client.check_health()
    client.prepare_bucket()
    rprint(client._minio.list_buckets())
