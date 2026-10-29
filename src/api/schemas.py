"""HTTP 运输契约：只放 api 层自己的请求 / 响应信封。

领域形状（文档条目、切块、详情）在 `common.schema`，这里不重复定义，
信封只负责组合。`response_model` 可直接指向 common 模型，FastAPI 不关心定义位置。
"""

from pydantic import BaseModel

from common.events import TaskStatus
from common.schema import DocItem


class UploadResponse(BaseModel):
    """POST /upload 的响应: 提交成功后立即返回任务 ID。"""

    task_id: str
    status: TaskStatus


class QueryRequest(BaseModel):
    """POST /query 的请求体 (前端 ChatPage.tsx 以 JSON body 提交)。"""

    query: str
    session_id: str
    enable_web_search: bool = True
    enable_hyde: bool = True


class DocsListResponse(BaseModel):
    """GET /api/docs 响应 (分页信封)。"""

    total: int
    list: list[DocItem]


class DocsDeleteResponse(BaseModel):
    """DELETE /api/docs/{doc_id} 响应 (级联部分失败时 success=false)。"""

    success: bool
    detail: str = ""
