import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from api.schemas.all_schema import UploadResponse, UploadStatusResponse

from service.import_service import arun_import
from utils import task_utils
from utils.path_utils import PROJECT_ROOT

router = APIRouter(prefix="/import", tags=["import"])

# 上传暂存目录 (生产建议换成 MinIO / 共享卷, 避免多副本写本地盘不一致)
UPLOAD_DIR = PROJECT_ROOT / "output" / "uploads"

# 后台任务强引用集合: 防止 asyncio.Task 被垃圾回收提前取消
_background_tasks: set[asyncio.Task] = set()


@router.post("/upload", response_model=UploadResponse, status_code=202)
async def import_document(file: UploadFile = File(...)) -> UploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    task_id = uuid.uuid4().hex
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / f"{Path(file.filename).name}"
    dest.unlink(missing_ok=True)
    dest.write_bytes(await file.read())

    task = asyncio.create_task(arun_import(task_id=task_id, origin_file_path=str(dest)))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return UploadResponse(
        task_id=task_id,
        status=task_utils.TaskStatus.PENDING.value,
    )


@router.get("/status/{task_id}", response_model=UploadStatusResponse)
async def import_status(task_id: str) -> UploadStatusResponse:
    """查询任务进度 (状态 / 运行中节点 / 已完成节点 / 结果)。"""
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
