import asyncio
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from api import __version__
from api.schemas import (
    DocsDeleteResponse,
    DocsDetailResponse,
    DocsListResponse,
    QueryRequest,
    UploadResponse,
)
from api.sse import sse_stream
from api.startup_checks import startup_checks
from common.client import MINIO_CLIENT
from common.config.app_config import APP_CONFIG
from common.config.env_config import ENV_CONFIG
from common.config.path_config import UPLOAD_TMP_DIR
from common.events import EVENT_BUS, TASK_MANAGER, TaskStatus
from common.logging import logger
from common.store import CHAT_HISTORY_MANAGER
from common.store.chat_history import ChatMessage
from service import docs_service
from service.import_service import arun_import
from service.query_service import arun_query


async def _sweep_loop() -> None:
    """周期性回收过期的任务状态与 SSE 通道（进程内状态没有 GC）。"""
    while True:
        await asyncio.sleep(APP_CONFIG.sse_sweep_interval_seconds)
        try:
            gone_tasks = TASK_MANAGER.sweep(APP_CONFIG.task_ttl_seconds)
            gone_channels = EVENT_BUS.sweep(APP_CONFIG.sse_channel_ttl_seconds)
            if gone_tasks or gone_channels:
                logger.info(
                    "运行态清扫: 任务 {}/通道 {}/剩余通道 {}",
                    gone_tasks,
                    gone_channels,
                    EVENT_BUS.channel_count(),
                )
        except Exception:  # 清扫失败不能拖垮服务
            logger.exception("运行态清扫失败")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("MiniRAG API 启动 (version={})", __version__)
    startup_checks()
    sweeper = asyncio.create_task(_sweep_loop())
    try:
        yield
    finally:
        sweeper.cancel()
        logger.info("MiniRAG API 关闭 (残留通道 {})", EVENT_BUS.channel_count())


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

# 全部业务路由统一挂 /api 前缀 (nginx /api/ 原样透传, docker healthcheck
# 探 /api/health 均据此成立); swagger 文档仍在 app 级 /docs 不受影响
router = APIRouter(prefix="/api")


_UPLOAD_CHUNK = 1024 * 1024


async def _save_upload(file: UploadFile, dest: Path) -> None:
    """分块落盘并强制体积上限（超限 413，不留半截文件）。"""
    max_bytes = APP_CONFIG.max_upload_bytes
    written = 0
    with dest.open("wb") as f:
        while chunk := await file.read(_UPLOAD_CHUNK):
            written += len(chunk)
            if written > max_bytes:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"文件超过上限 {max_bytes // (1024 * 1024)}MB"
                        f"（已读 {written / (1024 * 1024):.1f}MB）"
                    ),
                )
            f.write(chunk)


@router.get("/health")
async def health() -> dict:
    """健康检查, 同时用于 docker-compose healthcheck。"""
    return {"status": "ok", "version": __version__}


@router.post("/upload", response_model=UploadResponse, status_code=202)
async def import_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> UploadResponse:
    """导入文档接口, 异步处理上传文件。"""

    logger.info(f"[{str(request.url)}], file={file.filename}")

    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    task_id = uuid.uuid4().hex
    # 每个任务独立子目录：并发上传同名文件互不覆盖
    upload_dir = UPLOAD_TMP_DIR / task_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / Path(file.filename).name
    await _save_upload(file, dest)

    EVENT_BUS.create(task_id)

    background_tasks.add_task(arun_import, task_id=task_id, origin_file_path=str(dest))

    return UploadResponse(
        task_id=task_id,
        status=TaskStatus.PENDING.value,
    )


@router.get("/upload/sse/{task_id}")
async def upload_sse(
    request: Request,
    task_id: str,
):
    """导入任务订阅 SSE 推流。"""

    logger.info(f"[{str(request.url)}], task_id={task_id}")

    return StreamingResponse(
        sse_stream(
            sse_id=task_id,
            request=request,
        ),
        media_type="text/event-stream",
    )


@router.post("/query")
def query(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: QueryRequest,
):
    """查询接口, 异步处理用户查询。"""

    logger.info(
        f"[{str(request.url)}], session_id={payload.session_id}, "
        f"query={payload.query}, enable_web_search={payload.enable_web_search}, "
        f"enable_hyde={payload.enable_hyde}"
    )

    EVENT_BUS.create(payload.session_id)

    background_tasks.add_task(
        arun_query,
        session_id=payload.session_id,
        query=payload.query,
        enable_web_search=payload.enable_web_search,
        enable_hyde=payload.enable_hyde,
    )

    return {
        "status": "ok",
        "msg": "查询已异步启动",
        "session_id": payload.session_id,
    }


@router.get("/query/sse/{session_id}")
async def query_sse(
    request: Request,
    session_id: str,
) -> StreamingResponse:
    """查询任务订阅 SSE 推流。"""

    logger.info(f"[{str(request.url)}], session_id={session_id}")

    return StreamingResponse(
        sse_stream(
            sse_id=session_id,
            request=request,
        ),
        media_type="text/event-stream",
    )


@router.get("/history/{session_id}")
def history(
    request: Request,
    session_id: str,
):
    """获取指定会话的历史聊天记录。"""

    logger.info(f"[{str(request.url)}], session_id={session_id}")

    message_list: list[ChatMessage] = CHAT_HISTORY_MANAGER.get_latest_messages(
        session_id,
        # 历史页需展示全部记录, 不做条数限制;
        # 查询分析场景 (意图识别等) 仍按 APP_CONFIG.chat_message_lookback_count 回溯
        limit=None,
    )

    return {"status": "ok", "history": message_list}


@router.delete("/history/{session_id}")
def delete_history(
    request: Request,
    session_id: str,
):
    """删除指定会话的历史聊天记录。"""

    logger.info(f"[{str(request.url)}], session_id={session_id}")

    deleted_count = CHAT_HISTORY_MANAGER.clear_history(session_id)
    return {
        "status": "ok",
        "msg": f"历史记录已删除: {session_id}, 删除条数: {deleted_count}",
    }


# ------------------------------------------------------------------ #
# 文档管理页
# ------------------------------------------------------------------ #


@router.get("/docs", response_model=DocsListResponse)
def list_docs(
    request: Request,
    offset: int = 0,
    limit: int = 20,
) -> DocsListResponse:
    """获取文档列表。"""

    logger.info(f"[{str(request.url)}], offset={offset}, limit={limit}")

    offset = max(0, offset)
    limit = max(1, min(limit, 100))  # 设置 100 安全上限

    return docs_service.list_docs(offset=offset, limit=limit)


@router.get("/docs/{doc_id}", response_model=DocsDetailResponse)
def get_doc_detail(
    request: Request,
    doc_id: str,
) -> DocsDetailResponse:
    """获取文档详情。"""

    logger.info(f"[{str(request.url)}], doc_id={doc_id}")

    try:
        doc_id_int = int(doc_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"文档不存在: doc_id={doc_id}")

    try:
        return docs_service.get_doc_detail(doc_id_int)
    except docs_service.DocNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/docs/{doc_id}", response_model=DocsDeleteResponse)
def delete_doc(
    request: Request,
    doc_id: str,
) -> DocsDeleteResponse:
    """删除指定文档。"""

    logger.info(f"[{str(request.url)}], doc_id={doc_id}")

    try:
        doc_id_int = int(doc_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"文档不存在: doc_id={doc_id}")

    try:
        docs_service.delete_doc(doc_id_int)
    except docs_service.DocNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        logger.error(f"删除文档级联清理未完整完成: doc_id={doc_id}, error={e}")
        # 契约 (后端方案 §6): 部分失败 → 500 + {"success": false, "detail": ...}
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": f"删除未完整完成: {e}"},
        )

    return DocsDeleteResponse(success=True)


@router.get("/files/{object_name:path}")
def get_file(
    request: Request,
    object_name: str,
):
    """代理文件请求, 避免 CORS 问题, 使外网能跨域访问 MinIO 获取对象内容"""

    logger.info(f"[{str(request.url)}], object_name={object_name}")

    # 安全加固: 仅允许四个业务目录前缀, 其余一律 404 (默认开启)
    allowed_prefixes = {
        f"{ENV_CONFIG.minio.image_dir}/",
        f"{ENV_CONFIG.minio.origin_dir}/",
        f"{ENV_CONFIG.minio.markdown_dir}/",
        f"{ENV_CONFIG.minio.chunks_dir}/",
    }
    if not any(object_name.startswith(prefix) for prefix in allowed_prefixes):
        raise HTTPException(status_code=404, detail=f"对象不存在: {object_name}")

    try:
        content_type, chunk_iter = MINIO_CLIENT.get_object_stream(object_name)
    except Exception:
        raise HTTPException(status_code=404, detail=f"对象不存在: {object_name}")

    # media_type 为 stat 出的 content_type (PDF inline 预览 / 图片渲染 / JSON)
    return StreamingResponse(
        chunk_iter,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400, immutable",
            # 缓存控制：public 表示可被任何缓存区缓存, max-age=86400 表示缓存一天, immutable 表示内容不会改变
        },
    )


app.include_router(router)
