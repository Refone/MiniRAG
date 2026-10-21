"""文档管理页业务编排: 列表 / 详情 / 删除。

数据来源:
- Milvus `minirag_docs` (列表 / 详情元数据 / 删除主行) 与 `minirag_chunks` (级联删除);
- MinIO (final markdown 原文 / chunks.json / 三份制品与图片目录的清理)。

库中三个 URL 字段与 final markdown 内嵌图片链接均存相对代理路径
`/api/files/<object_name>`, 读回 MinIO 对象时去掉该前缀得到 object_name。
"""

import json

from common.client import MILVUS_CLIENT, MINIO_CLIENT
from common.client.milvus_client import MilvusDocsField
from utils.logging_utils import logger

# upload_file 入库的代理路径前缀 (与 minio_client._PROXY_FILES_PREFIX 保持一致)
_PROXY_FILES_PREFIX = "/api/files/"

_PDF_SUFFIX = ".pdf"


class DocNotFoundError(Exception):
    """文档不存在 (Milvus 行缺失或 MinIO 制品缺失)。"""


def _object_name_from_proxy_url(proxy_url: str) -> str:
    """库中存的是相对代理路径, 读 MinIO 对象时去掉前缀得到 object_name。"""
    if proxy_url.startswith(_PROXY_FILES_PREFIX):
        return proxy_url[len(_PROXY_FILES_PREFIX):]
    return proxy_url


def _derive_doc_type(origin_file_url: str) -> str:
    """按 origin_file_url (代理路径) 的文件名后缀推导文档类型。

    .pdf -> "pdf"; .md / .markdown / 空 / 未知 -> "markdown"
    (final markdown 制品必然存在)。
    """
    if origin_file_url.lower().endswith(_PDF_SUFFIX):
        return "pdf"
    return "markdown"


def list_docs(offset: int, limit: int) -> dict:
    """文档列表 (分页): total + 按 id 降序的 rows。

    doc_id 以 string 返回: Milvus auto_id 为 INT64 雪花 ID,
    超过 JS Number.MAX_SAFE_INTEGER, JSON 传输必须用字符串避免精度丢失。
    """
    total = MILVUS_CLIENT.count_docs()
    rows = MILVUS_CLIENT.query_docs_page(offset=offset, limit=limit)

    items = []
    for row in rows:
        origin_file_url = row.get(MilvusDocsField.ORIGIN_FILE_URL) or ""
        file_type = _derive_doc_type(origin_file_url)
        items.append(
            {
                "doc_id": str(row[MilvusDocsField.ID]),
                "title": row.get(MilvusDocsField.FILE_TITLE) or "",
                "type": file_type,
                "pdf_link": origin_file_url if file_type == "pdf" else None,
                "chunks_link": row.get(MilvusDocsField.CHUNKS_URL) or "",
            }
        )

    logger.debug(f"文档列表查询: total={total}, offset={offset}, limit={limit}")
    return {"total": total, "list": items}


def _read_object_bytes(proxy_url: str, label: str, doc_id: int) -> bytes:
    """按代理路径读回 MinIO 对象全文, 对象缺失/读取失败视为文档不可用。"""
    object_name = _object_name_from_proxy_url(proxy_url)
    try:
        _, chunk_iter = MINIO_CLIENT.get_object_stream(object_name)
        return b"".join(chunk_iter)
    except Exception as e:
        raise DocNotFoundError(
            f"文档 {label} 对象缺失或读取失败: "
            f"doc_id={doc_id}, object_name={object_name}, error={e}"
        )


def _read_chunks_json(proxy_url: str, doc_id: int) -> list[dict]:
    """读回 chunks.json 并解析为 [{content, level, title_stack}]。

    保持 chunks.json 原始字段与数组顺序 (demo-v4 切块卡片依赖 level,
    顺序即切块在原文中的先后)。
    """
    data = _read_object_bytes(proxy_url, "chunks.json", doc_id)
    try:
        chunks = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise DocNotFoundError(f"chunks.json 解析失败: doc_id={doc_id}, error={e}")

    if not isinstance(chunks, list):
        raise DocNotFoundError(
            f"chunks.json 结构异常 (期望数组): doc_id={doc_id}, "
            f"got={type(chunks).__name__}"
        )

    return [
        {
            "content": chunk.get("content", "") if isinstance(chunk, dict) else "",
            "level": chunk.get("level", 0) if isinstance(chunk, dict) else 0,
            "title_stack": chunk.get("title_stack", [])
            if isinstance(chunk, dict)
            else [],
        }
        for chunk in chunks
    ]


def get_doc_detail(doc_id: int) -> dict:
    """文档详情: 标题 + final markdown 原文 + 切块 + keywords/abstract。"""
    row = MILVUS_CLIENT.query_doc_by_id(doc_id)
    if row is None:
        raise DocNotFoundError(f"文档不存在: doc_id={doc_id}")

    markdown_url = row.get(MilvusDocsField.FINAL_MARKDOWN_URL) or ""
    chunks_url = row.get(MilvusDocsField.CHUNKS_URL) or ""

    markdown_text = _read_object_bytes(
        markdown_url, "final markdown", doc_id
    ).decode("utf-8", errors="replace")
    chunks = _read_chunks_json(chunks_url, doc_id)

    return {
        "title": row.get(MilvusDocsField.FILE_TITLE) or "",
        "markdown_text": markdown_text,
        "chunks": chunks,
        # keywords / abstract 返回入库时的原始字符串, 前端自行拆分展示
        "keywords": row.get(MilvusDocsField.DOCS_KEYWORDS) or "",
        "abstract": row.get(MilvusDocsField.DOCS_ABSTRACT) or "",
    }


def delete_doc(doc_id: int) -> None:
    """删除文档及级联数据 (顺序与同名覆盖流程 step_2 一致)。

    任一步失败抛 RuntimeError 带上下文, 由调用侧记录 error 日志并
    返回 500 (不自动补偿: 残留对象可在同名覆盖导入时被清理)。
    """
    row = MILVUS_CLIENT.query_doc_by_id(doc_id)
    if row is None:
        raise DocNotFoundError(f"文档不存在: doc_id={doc_id}")

    file_title = row.get(MilvusDocsField.FILE_TITLE) or ""

    # 1. 清理 MinIO 三份制品目录 (origin / markdown / chunks)
    try:
        del_cnt = MINIO_CLIENT.clear_doc_artifacts(file_title)
    except Exception as e:
        raise RuntimeError(
            f"清理 MinIO 制品失败: doc_id={doc_id}, file_title={file_title}, error={e}"
        )

    # 2. 清理 MinIO 图片目录 (否则成孤儿对象)
    try:
        del_cnt += MINIO_CLIENT.clear_doc_images(file_title)
    except Exception as e:
        raise RuntimeError(
            f"清理 MinIO 图片失败: doc_id={doc_id}, file_title={file_title}, error={e}"
        )

    # 3. 删 minirag_chunks
    try:
        MILVUS_CLIENT.delete_chunks_by_doc_ids([doc_id])
    except Exception as e:
        raise RuntimeError(f"删除 minirag_chunks 失败: doc_id={doc_id}, error={e}")

    # 4. 删 minirag_docs 行
    try:
        MILVUS_CLIENT.delete_doc_by_id(doc_id)
    except Exception as e:
        raise RuntimeError(f"删除 minirag_docs 失败: doc_id={doc_id}, error={e}")

    logger.success(
        f"文档删除完成: doc_id=[{doc_id}] file_title=[{file_title}] "
        f"MinIO 对象清理 {del_cnt} 个"
    )
