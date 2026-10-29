from common.events import EVENT_BUS, TASK_REGISTRY, SSEEvent, TaskStatus
from common.logging import logger
from graphs.import_graph.import_graph import import_graph
from graphs.import_graph.import_graph_state import ImportGraphState, create_state


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
    TASK_REGISTRY.clear(task_id)
    TASK_REGISTRY.set_status(task_id, TaskStatus.PROCESSING)

    initial_state = create_state(
        task_id=task_id,
        origin_file_path=origin_file_path,
    )
    logger.info("导入任务启动: task_id={}, path={}", task_id, origin_file_path)

    try:
        end_state = await import_graph.ainvoke(initial_state)
    except Exception as e:
        TASK_REGISTRY.set_status(task_id, TaskStatus.FAILED)
        TASK_REGISTRY.set_error(task_id, str(e))
        TASK_REGISTRY.publish(task_id)
        EVENT_BUS.push(task_id, SSEEvent.ERROR, {"error": str(e)})
        EVENT_BUS.push(task_id, SSEEvent.CLOSE, {})
        logger.exception("导入任务失败: task_id={}", task_id)
        raise

    TASK_REGISTRY.set_status(task_id, TaskStatus.COMPLETE)
    TASK_REGISTRY.set_result(task_id, "result", "ok")
    TASK_REGISTRY.publish(task_id)
    EVENT_BUS.push(task_id, SSEEvent.CLOSE, {})
    logger.info("导入任务完成: task_id={}", task_id)
    return end_state
