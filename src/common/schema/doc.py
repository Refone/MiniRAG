"""文档域共享契约（pydantic 模型，tier 0）。

这里的模型是「领域形状」而非 HTTP DTO：生产侧在 `common/store`（Milvus + MinIO），
组装侧在 `service`，序列化侧在 `api`（FastAPI `response_model` 不关心模型定义在
哪一层）。保持纯数据语义——不携带 HTTP 默认值、状态信封、路由描述。

与生产侧 TypedDict 的关系：`DocChunk` 与 `common.utils.markdown_splitter.Chunk`
同 JSON 形状（`utils/` 同为 tier 0，不能反向依赖本包，故保留自己的 TypedDict）。
"""

from typing import Literal

from pydantic import BaseModel, Field


class DocChunk(BaseModel):
    """文档切块（chunks.json 的条目形状）。"""

    content: str
    level: int
    title_stack: list[str | None]


class DocItem(BaseModel):
    """GET /api/docs 文档列表单条。"""

    doc_id: str
    title: str
    type: Literal["pdf", "markdown"] = Field(
        description='文档类型："pdf" 或 "markdown"；非 PDF 文档统一为 "markdown"。'
    )
    pdf_link: str | None
    chunks_link: str


class DocDetail(BaseModel):
    """GET /api/docs/{doc_id} 文档详情。"""

    title: str
    markdown_text: str
    chunks: list[DocChunk]
    keywords: str
    abstract: str
