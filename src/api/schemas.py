from typing import Literal

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    """POST /upload 的响应: 提交成功后立即返回任务 ID。"""

    task_id: str
    status: str


class QueryRequest(BaseModel):
    """POST /query 的请求体 (前端 ChatPage.tsx 以 JSON body 提交)。"""

    query: str
    session_id: str
    enable_web_search: bool = True
    enable_hyde: bool = True


class DocsListItem(BaseModel):
    """GET /api/docs 文档列表单条。"""

    doc_id: str
    title: str
    type: Literal["pdf", "markdown"] = Field(
        description='文档类型："pdf" 或 "markdown"；非 PDF 文档统一为 "markdown"。'
    )
    pdf_link: str | None
    chunks_link: str


class DocsListResponse(BaseModel):
    """GET /api/docs 响应。"""

    total: int
    list: list[DocsListItem]


class DocsChunkItem(BaseModel):
    """GET /api/docs/{doc_id} 详情中的单个切块 (与 chunks.json 结构一致)。"""

    content: str
    level: int
    title_stack: list[str | None]


class DocsDetailResponse(BaseModel):
    """GET /api/docs/{doc_id} 响应。"""

    title: str
    markdown_text: str
    chunks: list[DocsChunkItem]
    keywords: str
    abstract: str


class DocsDeleteResponse(BaseModel):
    """DELETE /api/docs/{doc_id} 响应 (级联部分失败时 success=false)。"""

    success: bool
    detail: str = ""
