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
