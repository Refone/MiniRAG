from processor.import_processor.main_graph import import_processor
from processor.import_processor.state import ImportGraphState, create_state
from utils import task_utils
from utils.logging_utils import logger
from utils.sse_utils import SSEEvent, sse_push


async def arun_import(task_id: str, origin_file_path: str) -> ImportGraphState:
    """异步执行导入图, 返回最终状态。

    import_processor 是同步编译图; 这里用 ainvoke 让 LangGraph 把同步节点
    调度到线程池, 避免阻塞 FastAPI 事件循环。

    进度经 SSE 推送 (队列在 POST /upload 时创建, 前端连
    /api/upload/sse/{task_id} 消费):
    - 父任务节点 trace_node(need_push=True) 推送 progress 快照;
    - ZIP 分叉后 node_md_fork 推送 fork, 各 md 分支推送 child-progress;
    - 本函数在任务结束时推送父任务终态与关闭信号。
    """
    task_utils.clear_task(task_id)
    task_utils.set_task_status(task_id, task_utils.TaskStatus.PROCESSING.value)

    initial_state = create_state(
        task_id=task_id,
        origin_file_path=origin_file_path,
    )
    logger.info("导入任务启动: task_id={}, path={}", task_id, origin_file_path)

    try:
        end_state = await import_processor.ainvoke(initial_state)
    except Exception as e:
        task_utils.set_task_status(task_id, task_utils.TaskStatus.FAILED.value)
        task_utils.set_task_error(task_id, str(e))
        task_utils.task_push_sse(task_id)
        sse_push(sse_id=task_id, event=SSEEvent.ERROR, data={"error": str(e)})
        sse_push(sse_id=task_id, event=SSEEvent.CLOSE, data={})
        logger.exception("导入任务失败: task_id={}", task_id)
        raise

    task_utils.set_task_status(task_id, task_utils.TaskStatus.COMPLETE.value)
    task_utils.set_task_result(task_id, "result", "ok")
    task_utils.task_push_sse(task_id)
    sse_push(sse_id=task_id, event=SSEEvent.CLOSE, data={})
    logger.info("导入任务完成: task_id={}", task_id)
    return end_state
