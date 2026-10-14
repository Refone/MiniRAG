from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    Request,
    BackgroundTasks,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from api import __version__
from api.schemas import QueryRequest, UploadResponse, UploadStatusResponse
import uuid
from pathlib import Path
from service.import_service import arun_import
from service.query_service import arun_query
from utils import task_utils
from api.setup import setup
from utils.logging_utils import logger
from utils.path_utils import PROJECT_ROOT
from utils.sse_utils import sse_create_queue, sse_generator
from processor.query_processor.chat_history import ChatMessage, chat_history_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("MiniRag API 启动 (version={})", __version__)
    setup()
    yield
    logger.info("MiniRag API 关闭")


app = FastAPI(
    title="MiniRag API",
    description="前端经 FastAPI 调用 LangGraph 服务的网关",
    version=__version__,
    lifespan=lifespan,
)

# 开发阶段放开 CORS; 生产由 nginx 同源反代, 可收紧 allow_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    """健康检查, 同时用于 docker-compose healthcheck。"""
    return {"status": "ok", "version": __version__}


UPLOAD_DIR = PROJECT_ROOT / "output" / "uploads"


@app.post("/upload", response_model=UploadResponse, status_code=202)
async def import_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> UploadResponse:

    logger.info(f"[{str(request.url)}], file={file.filename}")

    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    task_id = uuid.uuid4().hex
    upload_dir = UPLOAD_DIR
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{Path(file.filename).name}"
    dest.unlink(missing_ok=True)
    dest.write_bytes(await file.read())

    background_tasks.add_task(arun_import, task_id=task_id, origin_file_path=str(dest))

    return UploadResponse(
        task_id=task_id,
        status=task_utils.TaskStatus.PENDING.value,
    )


@app.get("/upload/status/{task_id}", response_model=UploadStatusResponse)
async def import_status(
    request: Request,
    task_id: str,
) -> UploadStatusResponse:

    logger.info(f"[{str(request.url)}], task_id={task_id}")

    status = task_utils.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    return UploadStatusResponse(
        task_id=task_id,
        status=status,
        running_nodes=task_utils.get_task_running_nodes(task_id),
        done_nodes=task_utils.get_task_done_nodes(task_id),
        result=task_utils.get_task_results(task_id),
    )


@app.post("/query")
def query(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: QueryRequest,
):
    logger.info(
        f"[{str(request.url)}], session_id={payload.session_id}, "
        f"query={payload.query}, web_search={payload.web_search}"
    )

    sse_create_queue(payload.session_id)

    background_tasks.add_task(
        arun_query,
        session_id=payload.session_id,
        query=payload.query,
        web_search=payload.web_search,
    )

    return {
        "status": "ok",
        "msg": "查询已异步启动",
        "session_id": payload.session_id,
    }


@app.get("/query/sse/{session_id}")
async def query_sse(
    request: Request,
    session_id: str,
):
    logger.info(f"[{str(request.url)}], session_id={session_id}")

    return StreamingResponse(
        sse_generator(
            sse_id=session_id,
            request=request,
        ),
        media_type="text/event-stream",
    )


@app.get("/history/{session_id}")
def history(
    request: Request,
    session_id: str,
):
    logger.info(f"[{str(request.url)}], session_id={session_id}")

    message_list: list[ChatMessage] = chat_history_manager.get_latest_messages(
        session_id
    )

    return {"status": "ok", "history": message_list}


@app.delete("/history/{session_id}")
def delete_history(
    request: Request,
    session_id: str,
):
    logger.info(f"[{str(request.url)}], session_id={session_id}")

    deleted_count = chat_history_manager.clear_history(session_id)
    return {
        "status": "ok",
        "msg": f"历史记录已删除: {session_id}, 删除条数: {deleted_count}",
    }
