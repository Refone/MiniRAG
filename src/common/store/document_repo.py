"""文档制品与元数据的读写（MinIO 三制品 + Milvus docs/chunks）。

为什么要有这一层：

1. **删除顺序只有一份**。「同名覆盖导入」与「删除文档接口」原本各写一遍
   "MinIO 制品 → chunks → docs"，改一处忘一处就留孤儿对象。
2. **图节点不再直接写库**。`node_document_embedding` 原先自己拼 insert / 校验
   insert_count / 查回 auto_id，无法离线测试；这些都收敛到这里，节点只做
   状态流转与错误处理。

两条删除路径的差异（务必保持）：

| 场景 | 顺序 | 是否清图片 |
| --- | --- | --- |
| 同名覆盖导入（`delete_by_title`） | 三制品 → chunks → docs | **否**（图片刚由 node_md_img 重传） |
| 删除文档接口（`delete_by_id`） | 三制品 → 图片 → chunks → docs | **是** |
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from common.client import MILVUS_CLIENT, MINIO_CLIENT
from common.client.milvus_client import (
    MilvusChunksItem,
    MilvusDocsField,
    MilvusDocsItem,
)
from common.config.app_config import APP_CONFIG
from common.config.env_config import ENV_CONFIG
from common.logging import logger
from common.schema import DocChunk, DocDetail


class DocumentNotFoundError(Exception):
    """文档不存在（Milvus 行缺失或 MinIO 制品缺失）。"""


@dataclass(frozen=True)
class DocumentArtifacts:
    """三份制品在库里的代理 URL。"""

    origin_file_url: str
    final_markdown_url: str
    chunks_url: str


@dataclass(frozen=True)
class DeleteResult:
    """删除结果，供调用方打日志（不参与业务判断）。"""

    docs_rows: int
    minio_objects: int


def _object_name_from_proxy_url(proxy_url: str) -> str:
    """库里存的是相对代理路径，读 MinIO 对象时去掉前缀得到 object_name。"""
    prefix = APP_CONFIG.files_proxy_prefix
    if proxy_url.startswith(prefix):
        return proxy_url[len(prefix) :]
    return proxy_url


def _read_object_bytes(proxy_url: str, label: str, doc_id: int) -> bytes:
    """按代理路径读回 MinIO 对象全文，对象缺失/读取失败视为文档不可用。"""
    object_name = _object_name_from_proxy_url(proxy_url)
    try:
        _, chunk_iter = MINIO_CLIENT.get_object_stream(object_name)
        return b"".join(chunk_iter)
    except Exception as e:
        raise DocumentNotFoundError(
            f"文档 {label} 对象缺失或读取失败: "
            f"doc_id={doc_id}, object_name={object_name}, error={e}"
        )


def _read_chunks_json(proxy_url: str, doc_id: int) -> list[DocChunk]:
    """读回 chunks.json 并校验为领域模型（shape 见 `common.schema.DocChunk`）。"""
    data = _read_object_bytes(proxy_url, "chunks.json", doc_id)
    try:
        chunks = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise DocumentNotFoundError(f"chunks.json 解析失败: doc_id={doc_id}, error={e}")

    if not isinstance(chunks, list):
        raise DocumentNotFoundError(
            f"chunks.json 结构异常 (期望数组): doc_id={doc_id}, "
            f"got={type(chunks).__name__}"
        )

    try:
        return [DocChunk(**chunk) for chunk in chunks]
    except (TypeError, ValidationError) as e:
        raise DocumentNotFoundError(f"chunks.json 字段非法: doc_id={doc_id}, error={e}")


class DocumentRepo:
    """文档读写的唯一入口（Milvus 行 + MinIO 制品）。"""

    # ------------------------------------------------------------------ 读
    def count(self) -> int:
        """docs 集合行数（文档列表分页用）。"""
        return MILVUS_CLIENT.count_docs()

    def list_page(self, offset: int, limit: int) -> list[dict]:
        """按 id 降序分页返回 docs 标量列（不含向量）。"""
        return MILVUS_CLIENT.query_docs_page(offset=offset, limit=limit)

    def get(self, doc_id: int) -> dict | None:
        """按主键取单行标量列；不存在返回 None。"""
        return MILVUS_CLIENT.query_doc_by_id(doc_id)

    def get_detail(self, doc_id: int) -> DocDetail | None:
        """详情 = 行元数据 + final markdown 原文 + chunks.json；行缺失返回 None。"""
        row = MILVUS_CLIENT.query_doc_by_id(doc_id)
        if row is None:
            return None

        markdown_text = _read_object_bytes(
            row.get(MilvusDocsField.FINAL_MARKDOWN_URL) or "", "final markdown", doc_id
        ).decode("utf-8", errors="replace")
        chunks = _read_chunks_json(row.get(MilvusDocsField.CHUNKS_URL) or "", doc_id)

        return DocDetail(
            title=row.get(MilvusDocsField.FILE_TITLE) or "",
            markdown_text=markdown_text,
            chunks=chunks,
            # keywords / abstract 返回入库时的原始字符串，前端自行拆分展示
            keywords=row.get(MilvusDocsField.DOCS_KEYWORDS) or "",
            abstract=row.get(MilvusDocsField.DOCS_ABSTRACT) or "",
        )

    # ------------------------------------------------------------------ 写
    def delete_by_title(self, file_title: str) -> DeleteResult:
        """同名覆盖：清三制品 + 该标题的全部 chunks/docs（不动图片目录）。

        按 file_title 兜底清理历史遗留行，避免新旧行并存导致检索双份命中。
        """
        old_rows = MILVUS_CLIENT.query_doc_rows_by_file_title(file_title)
        old_ids = [row["id"] for row in old_rows]

        minio_objects = MINIO_CLIENT.clear_doc_artifacts(file_title)

        try:
            MILVUS_CLIENT.delete_chunks_by_doc_ids(old_ids)
            MILVUS_CLIENT.delete_chunks_by_file_title(file_title)
            MILVUS_CLIENT.delete_docs_by_file_title(file_title)
        except Exception as e:
            raise RuntimeError(
                f"同名覆盖清理旧文档失败: file_title={file_title}, error={e}"
            )

        return DeleteResult(docs_rows=len(old_ids), minio_objects=minio_objects)

    def delete_by_id(self, doc_id: int) -> DeleteResult:
        """删除文档接口：清三制品 + 图片目录 + chunks/docs。

        任一步失败抛 RuntimeError（不自动补偿：残留对象可在同名覆盖导入时被清理）。
        """
        row = MILVUS_CLIENT.query_doc_by_id(doc_id)
        if row is None:
            raise DocumentNotFoundError(f"文档不存在: doc_id={doc_id}")

        file_title = row.get(MilvusDocsField.FILE_TITLE) or ""
        return self._delete_row(doc_id=doc_id, file_title=file_title, with_images=True)

    def upload_artifacts(
        self,
        file_title: str,
        *,
        origin: Path | None,
        markdown: Path,
        chunks: Path,
    ) -> DocumentArtifacts:
        """上传三份制品，返回入库用的代理 URL。

        origin 可以为 None（原始文件缺失时留空，不阻断导入）。
        """
        origin_url = ""
        if origin is not None and origin.is_file():
            origin_url = MINIO_CLIENT.upload_file(
                prefix=MINIO_CLIENT.doc_artifact_prefix(
                    ENV_CONFIG.minio.origin_dir, file_title
                ),
                as_name=origin.name,
                file_path=str(origin),
            )

        markdown_url = MINIO_CLIENT.upload_file(
            prefix=MINIO_CLIENT.doc_artifact_prefix(
                ENV_CONFIG.minio.markdown_dir, file_title
            ),
            as_name=markdown.name,
            file_path=str(markdown),
        )

        chunks_url = MINIO_CLIENT.upload_file(
            prefix=MINIO_CLIENT.doc_artifact_prefix(
                ENV_CONFIG.minio.chunks_dir, file_title
            ),
            as_name=chunks.name,
            file_path=str(chunks),
        )

        return DocumentArtifacts(
            origin_file_url=origin_url,
            final_markdown_url=markdown_url,
            chunks_url=chunks_url,
        )

    def save_meta(
        self,
        *,
        task_id: str,
        file_title: str,
        artifacts: DocumentArtifacts,
        keywords: str,
        abstract: str,
        keywords_sparse: dict[int, float],
        abstract_dense: list[float],
    ) -> int:
        """写入 minirag_docs 一行并返回 auto_id 主键。"""
        ret = MILVUS_CLIENT.insert(
            collection_name=ENV_CONFIG.milvus.collection_docs,
            data=[
                MilvusDocsItem(
                    task_id=task_id,
                    file_title=file_title,
                    origin_file_url=artifacts.origin_file_url,
                    final_markdown_url=artifacts.final_markdown_url,
                    chunks_url=artifacts.chunks_url,
                    created_at=int(time.time() * 1000),
                    docs_keywords=keywords,
                    docs_abstract=abstract,
                    keywords_sparse_vector=keywords_sparse,
                    abstract_dense_vector=abstract_dense,
                )
            ],
        )

        insert_count = ret.get("insert_count", 0)
        if insert_count != 1:
            raise RuntimeError(
                f"写入 minirag_docs 条数不一致: 预期=1, 实际={insert_count}"
            )

        doc_id = self._extract_doc_id(ret, task_id, file_title)
        logger.success(
            f"文档写入 minirag_docs 完成: doc_id=[{doc_id}] "
            f"task_id=[{task_id}] file_title=[{file_title}]"
        )
        return doc_id

    def save_chunks(self, *, doc_id: int, file_title: str, embedded: list[dict]) -> int:
        """写入 minirag_chunks（携带 doc_id 与 chunk_index），返回写入条数。"""
        if not embedded:
            logger.warning("切片向量列表为空, 直接跳过写入")
            return 0

        ret = MILVUS_CLIENT.insert(
            collection_name=ENV_CONFIG.milvus.collection_chunks,
            data=[
                MilvusChunksItem(
                    doc_id=doc_id,
                    file_title=file_title,
                    chunk_index=index,
                    chunk_content=chunk["content"],
                    content_dense_vector=chunk["dense"],
                    content_sparse_vector=chunk["sparse"],
                )
                for index, chunk in enumerate(embedded)
            ],
        )

        insert_count = ret.get("insert_count", 0)
        if insert_count != len(embedded):
            raise RuntimeError(
                f"写入 minirag_chunks 条数不一致: 预期={len(embedded)}, "
                f"实际={insert_count}"
            )

        logger.success(
            f"切片写入 minirag_chunks 完成: doc_id=[{doc_id}] "
            f"file_title=[{file_title}] 切片数:[{insert_count}]"
        )
        return insert_count

    # -------------------------------------------------------------- 内部实现
    def _delete_row(
        self, *, doc_id: int, file_title: str, with_images: bool
    ) -> DeleteResult:
        """按固定顺序删除：三制品 →（图片）→ chunks → docs。"""
        try:
            minio_objects = MINIO_CLIENT.clear_doc_artifacts(file_title)
        except Exception as e:
            raise RuntimeError(
                f"清理 MinIO 制品失败: doc_id={doc_id}, "
                f"file_title={file_title}, error={e}"
            )

        if with_images:
            try:
                minio_objects += MINIO_CLIENT.clear_doc_images(file_title)
            except Exception as e:
                raise RuntimeError(
                    f"清理 MinIO 图片失败: doc_id={doc_id}, "
                    f"file_title={file_title}, error={e}"
                )

        try:
            MILVUS_CLIENT.delete_chunks_by_doc_ids([doc_id])
        except Exception as e:
            raise RuntimeError(f"删除 minirag_chunks 失败: doc_id={doc_id}, error={e}")

        try:
            MILVUS_CLIENT.delete_doc_by_id(doc_id)
        except Exception as e:
            raise RuntimeError(f"删除 minirag_docs 失败: doc_id={doc_id}, error={e}")

        logger.success(
            f"文档删除完成: doc_id=[{doc_id}] file_title=[{file_title}] "
            f"MinIO 对象清理 {minio_objects} 个"
        )
        return DeleteResult(docs_rows=1, minio_objects=minio_objects)

    @staticmethod
    def _extract_doc_id(ret: dict, task_id: str, file_title: str) -> int:
        """pymilvus 3.x 优先用返回的 auto_id；缺失时按 task_id + file_title 查回。"""
        ret_ids = ret.get("ids")
        if isinstance(ret_ids, list) and ret_ids:
            return int(ret_ids[0])
        if isinstance(ret_ids, int):
            return ret_ids

        doc_id = MILVUS_CLIENT.query_doc_id(task_id, file_title)
        if doc_id is None:
            raise RuntimeError(
                f"docs 写入后查回 doc_id 失败: "
                f"task_id={task_id}, file_title={file_title}"
            )
        return doc_id


DOCUMENT_REPO = DocumentRepo()
