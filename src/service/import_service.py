from common.events import EVENT_BUS, TASK_MANAGER, SSEEvent, TaskStatus
from common.logging import logger
from graphs.import_graph.import_graph import import_graph
from graphs.import_graph.import_graph_state import ImportGraphState, create_state


def _push_parent_progress(task_id: str) -> None:
    """父任务进度推送的组合点：先取快照（task_manager），再推帧（event_bus）。"""
    snapshot = TASK_MANAGER.snapshot(task_id)
    if snapshot is not None:
        EVENT_BUS.push(task_id, SSEEvent.PROGRESS, snapshot)


async def arun_import(task_id: str, origin_file_path: str) -> ImportGraphState:
    """异步执行导入图, 返回最终状态。

    import_graph 是同步编译图; 这里用 ainvoke 让 LangGraph 把同步节点
    调度到线程池, 避免阻塞 FastAPI 事件循环。

    进度经 SSE 推送 (队列在 POST /upload 时创建, 前端连
    /api/upload/sse/{task_id} 消费):
    - 父任务节点 trace_node(need_push=True) 推送 progress 快照;
    - ZIP 分叉后 node_md_fork 推送 fork, 各 md 分支推送 child-progress;
    - 本函数在任务结束时推送父任务终态与关闭信号。
    """
    TASK_MANAGER.clear(task_id)
    TASK_MANAGER.set_status(task_id, TaskStatus.PROCESSING)

    initial_state = create_state(
        task_id=task_id,
        origin_file_path=origin_file_path,
    )
    logger.info("导入任务启动: task_id={}, path={}", task_id, origin_file_path)

    try:
        end_state = await import_graph.ainvoke(initial_state)
    except Exception as e:
        TASK_MANAGER.set_status(task_id, TaskStatus.FAILED)
        TASK_MANAGER.set_error(task_id, str(e))
        _push_parent_progress(task_id)
        EVENT_BUS.push(task_id, SSEEvent.ERROR, {"error": str(e)})
        EVENT_BUS.push(task_id, SSEEvent.CLOSE, {})
        logger.exception("导入任务失败: task_id={}", task_id)
        raise

    TASK_MANAGER.set_status(task_id, TaskStatus.COMPLETE)
    TASK_MANAGER.set_result(task_id, "result", "ok")
    _push_parent_progress(task_id)
    EVENT_BUS.push(task_id, SSEEvent.CLOSE, {})
    logger.info("导入任务完成: task_id={}", task_id)
    return end_state
