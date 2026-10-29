from common.events import EVENT_BUS, TASK_REGISTRY, SSEEvent, TaskStatus
from common.logging import logger
from graphs.query_graph.query_graph import query_graph
from graphs.query_graph.query_graph_state import create_state


async def arun_query(
    session_id: str,
    query: str,
    enable_web_search: bool = True,
    enable_hyde: bool = True,
) -> dict:
    try:
        TASK_REGISTRY.clear(session_id)
        TASK_REGISTRY.set_status(session_id, TaskStatus.PROCESSING)

        start_state = create_state(
            session_id=session_id,
            original_query=query,
            enable_web_search=enable_web_search,
            enable_hyde=enable_hyde,
        )
        end_state = await query_graph.ainvoke(start_state)

        EVENT_BUS.push(session_id, SSEEvent.CLOSE, {})

        TASK_REGISTRY.set_status(session_id, TaskStatus.COMPLETE)

        return end_state
    except Exception as e:
        # 处理异常, 例如记录日志
        TASK_REGISTRY.set_status(session_id, TaskStatus.FAILED)
        try:
            EVENT_BUS.push(session_id, SSEEvent.ERROR, {"error": str(e)})
        finally:
            # 失败路径也要关流: 与导入流对齐, 前端不需要再靠"error 后关流"的隐含约定
            EVENT_BUS.push(session_id, SSEEvent.CLOSE, {})
        logger.error(f"查询处理失败: {str(e)}")
        return {"reply": f"查询处理失败: {str(e)}"}
