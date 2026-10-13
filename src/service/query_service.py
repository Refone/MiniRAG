from processor.query_processor.main_graph import query_processor
from utils.sse_utils import SSEEvent, sse_push
from utils.task_utils import clear_task, set_task_status, TaskStatus
from utils.logging_utils import logger
from processor.query_processor.state import create_state


async def arun_query(
    session_id: str,
    query: str,
    web_search: bool = True,
) -> dict:
    try:
        clear_task(session_id)
        set_task_status(session_id, TaskStatus.PROCESSING.value)

        start_state = create_state(
            session_id=session_id,
            original_query=query,
            web_search=web_search,
        )
        end_state = await query_processor.ainvoke(start_state)

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
