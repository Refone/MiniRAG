from contextlib import asynccontextmanager

from fastapi import (
    APIRouter,
    FastAPI,
    Request,
    BackgroundTasks,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from api import __version__
from api.schemas import (
    QueryRequest,
    UploadResponse,
    DocsListResponse,
    DocsDetailResponse,
    DocsDeleteResponse,
)
import uuid
from pathlib import Path
from common.client import MINIO_CLIENT
from common.config.env_config import ENV_CONFIG
from service import docs_service
from service.import_service import arun_import
from service.query_service import arun_query
from utils import task_utils
from api.startup_checks import startup_checks
from utils.logging_utils import logger
from utils.path_utils import PROJECT_ROOT
from utils.sse_utils import sse_create_queue, sse_generator
from common.store.chat_history import ChatMessage, chat_history_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("MiniRag API 启动 (version={})", __version__)
    startup_checks()
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

# 全部业务路由统一挂 /api 前缀 (nginx /api/ 原样透传, docker healthcheck
# 探 /api/health 均据此成立); swagger 文档仍在 app 级 /docs 不受影响
router = APIRouter(prefix="/api")


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

    logger.info(f"[{str(request.url)}], file={file.filename}")

    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    task_id = uuid.uuid4().hex
    upload_dir = Path(ENV_CONFIG.output_dir.upload_tmp_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{Path(file.filename).name}"
    dest.unlink(missing_ok=True)
    dest.write_bytes(await file.read())

    # 先建 SSE 队列再挂后台任务, 保证任务执行期间的进度推送有处可去
    # (前端上传成功后即连 /api/upload/sse/{task_id} 消费)
    sse_create_queue(task_id)

    background_tasks.add_task(arun_import, task_id=task_id, origin_file_path=str(dest))

    return UploadResponse(
        task_id=task_id,
        status=task_utils.TaskStatus.PENDING.value,
    )


@router.get("/upload/sse/{task_id}")
async def upload_sse(
    request: Request,
    task_id: str,
):
    """导入任务进度 SSE 推流 (对齐 /query/sse/{session_id} 的机制)。"""
    logger.info(f"[{str(request.url)}], task_id={task_id}")

    return StreamingResponse(
        sse_generator(
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
    logger.info(
        f"[{str(request.url)}], session_id={payload.session_id}, "
        f"query={payload.query}, enable_web_search={payload.enable_web_search}, "
        f"enable_hyde={payload.enable_hyde}"
    )

    sse_create_queue(payload.session_id)

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
):
    logger.info(f"[{str(request.url)}], session_id={session_id}")

    return StreamingResponse(
        sse_generator(
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
    logger.info(f"[{str(request.url)}], session_id={session_id}")

    message_list: list[ChatMessage] = chat_history_manager.get_latest_messages(
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
    logger.info(f"[{str(request.url)}], session_id={session_id}")

    deleted_count = chat_history_manager.clear_history(session_id)
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
    logger.info(f"[{str(request.url)}], offset={offset}, limit={limit}")

    # limit 校验范围 1~100 (越界 clamp); offset 为负时 Milvus 直接报错, 一并 clamp 到 0
    offset = max(0, offset)
    limit = max(1, min(limit, 100))

    return docs_service.list_docs(offset=offset, limit=limit)


@router.get("/docs/{doc_id}", response_model=DocsDetailResponse)
def get_doc_detail(
    request: Request,
    doc_id: str,
) -> DocsDetailResponse:
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
    # Session-MVVM V0: MinIO 对象以唯一 object_name 存放、无覆盖写, 可安全长缓存,
    # 浏览器 HTTP 缓存兜底跨刷新场景 (docs/feat/Session-MVVM/方案设计-V0.md §4.5.2)
    return StreamingResponse(
        chunk_iter,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


app.include_router(router)
