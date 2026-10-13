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
        clear_task(session_id=session_id)
        set_task_status(session_id=session_id, status=TaskStatus.PROCESSING)

        start_state = create_state(
            session_id=session_id,
            original_query=query,
            web_search=web_search,
        )
        end_state = query_processor.invoke(start_state)

        sse_push(
            session_id=session_id,
            event=SSEEvent.FINAL,
            data={},
        )

        set_task_status(session_id=session_id, status=TaskStatus.COMPLETED)

        return end_state
    except Exception as e:
        # 处理异常, 例如记录日志
        set_task_status(session_id=session_id, status=TaskStatus.FAILED)
        sse_push(
            session_id=session_id,
            event=SSEEvent.ERROR,
            data={},
        )
        logger.error(f"查询处理失败: {str(e)}")
        return {"reply": f"查询处理失败: {str(e)}"}
