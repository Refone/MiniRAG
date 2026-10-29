"""文档管理页业务编排: 列表 / 详情 / 删除。

数据访问全部走 `DOCUMENT_REPO`（Milvus 行 + MinIO 制品），本层只做 DTO 组装与
异常翻译（`DocumentNotFoundError` → API 层的 404）。

库中三个 URL 字段与 final markdown 内嵌图片链接均存相对代理路径
`/api/files/<object_name>`，读写时的前缀换算由 repo 统一处理。
"""

from common.client.milvus_client import MilvusDocsField
from common.logging import logger
from common.store import DOCUMENT_REPO

# 保留原异常名对外暴露：api 层按 docs_service.DocNotFoundError 捕获
from common.store.document_repo import DocumentNotFoundError as DocNotFoundError

_PDF_SUFFIX = ".pdf"


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
    total = DOCUMENT_REPO.count()
    rows = DOCUMENT_REPO.list_page(offset=offset, limit=limit)

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


def get_doc_detail(doc_id: int) -> dict:
    """文档详情: 标题 + final markdown 原文 + 切块 + keywords/abstract。"""
    detail = DOCUMENT_REPO.get_detail(doc_id)
    if detail is None:
        raise DocNotFoundError(f"文档不存在: doc_id={doc_id}")

    return {
        "title": detail.title,
        "markdown_text": detail.markdown_text,
        "chunks": detail.chunks,
        # keywords / abstract 返回入库时的原始字符串, 前端自行拆分展示
        "keywords": detail.keywords,
        "abstract": detail.abstract,
    }


def delete_doc(doc_id: int) -> None:
    """删除文档及级联数据（顺序与同名覆盖流程共用 `DOCUMENT_REPO`）。

    - 行不存在: `DocNotFoundError`（API 返回 404）
    - 任一步失败: `RuntimeError`（API 返回 500，不自动补偿）
    """
    DOCUMENT_REPO.delete_by_id(doc_id)
