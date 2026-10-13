from pydantic import BaseModel


class UploadResponse(BaseModel):
    """POST /upload 的响应: 提交成功后立即返回任务 ID。"""

    task_id: str
    status: str


class UploadStatusResponse(BaseModel):
    """GET /upload/status/{task_id} 的响应: 任务进度快照。"""

    task_id: str
    status: str
    running_nodes: list[str]
    done_nodes: list[str]
    result: dict[str, str]


class QueryRequest(BaseModel):
    """POST /query 的请求体 (前端 ChatPage.tsx 以 JSON body 提交)。"""

    query: str
    session_id: str
    web_search: bool = True
