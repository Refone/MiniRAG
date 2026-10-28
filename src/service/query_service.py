from graphs.query_graph.query_graph import query_graph
from graphs.query_graph.query_graph_state import create_state
from utils.logging_utils import logger
from utils.sse_utils import SSEEvent, sse_push
from utils.task_utils import TaskStatus, clear_task, set_task_status


async def arun_query(
    session_id: str,
    query: str,
    enable_web_search: bool = True,
    enable_hyde: bool = True,
) -> dict:
    try:
        clear_task(session_id)
        set_task_status(session_id, TaskStatus.PROCESSING.value)

        start_state = create_state(
            session_id=session_id,
            original_query=query,
            enable_web_search=enable_web_search,
            enable_hyde=enable_hyde,
        )
        end_state = await query_graph.ainvoke(start_state)

        sse_push(
            sse_id=session_id,
            event=SSEEvent.CLOSE,
            data={},
        )

        set_task_status(session_id, TaskStatus.COMPLETE.value)

        return end_state
    except Exception as e:
        # 处理异常, 例如记录日志
        set_task_status(session_id, TaskStatus.FAILED.value)
        try:
            sse_push(
                sse_id=session_id,
                event=SSEEvent.ERROR,
                data={"error": str(e)},
            )
        except Exception:
            pass
        logger.error(f"查询处理失败: {str(e)}")
        return {"reply": f"查询处理失败: {str(e)}"}
