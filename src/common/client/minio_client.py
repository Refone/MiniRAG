import json
from mimetypes import guess_type
from minio import Minio
from minio.deleteobjects import DeleteObject
from utils.logging_utils import logger
from utils.net_utils import probe_tcp
from common.config.env_config import ENV_CONFIG


class MiniRagMinioClient:
    def __init__(self):
        """只保存配置并构建惰性客户端, 不做任何网络请求。

        bucket 的创建放到了 prepare_bucket() 里, 由启动自检 (api/setup.py)
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
        (api/setup.py) 与 tools/reset_db.py 在需要时显式调用。
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
            prefix: 云端路径
            as_name: 云端文件名
            file_path: 本地文件路径
        Returns:
            云端文件 url
        """
        res = self._minio.fput_object(
            bucket_name=self.bucket_name,
            object_name=prefix + "/" + as_name,
            file_path=file_path,
            content_type=guess_type(file_path)[0],
        )

        from rich import print as rprint

        rprint(res)

        return f"http://{self.endpoint}/{self.bucket_name}/{prefix}/{as_name}"


if __name__ == "__main__":
    from rich import print as rprint

    client = MiniRagMinioClient()
    client.check_health()
    client.prepare_bucket()
    rprint(client._minio.list_buckets())
