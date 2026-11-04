from common import store
from common.events import EVENT_BUS, TASK_MANAGER, SSEEvent, TaskStatus
from common.logging import logger
from common.schema.token_usage import TokenScope, TokenUsage
from graphs.query_graph.query_graph import query_graph
from graphs.query_graph.query_graph_state import create_state


def _flush_token_usage(session_id: str, user_ip: str, usage: TokenUsage) -> None:
    """请求结束统一 flush: 落库 + 推一帧 usage（有消耗才推）。

    计量失败只告警，不阻塞主流程。
    """
    if not session_id or not usage or not any(usage.values()):
        return

    try:
        token_usage = store.get_token_usage_manager()
        token_usage.add_usage(session_id, user_ip, TokenScope.QUERY, usage)
        snapshot = token_usage.get_usage(session_id)
        EVENT_BUS.push(session_id, SSEEvent.USAGE, snapshot.model_dump())
    except Exception:
        logger.warning(f"Token 统计落库失败: session_id={session_id}")


async def arun_query(
    session_id: str,
    query: str,
    enable_web_search: bool = True,
    enable_hyde: bool = True,
    user_ip: str = "",
) -> dict:
    try:
        TASK_MANAGER.clear(session_id)
        TASK_MANAGER.set_status(session_id, TaskStatus.PROCESSING)

        start_state = create_state(
            session_id=session_id,
            original_query=query,
            enable_web_search=enable_web_search,
            enable_hyde=enable_hyde,
        )
        end_state = await query_graph.ainvoke(start_state)

        # token_meter 通道经 sum_token_usage reducer 累计本流全部节点增量;
        # 推送粒度为逐请求: 请求返回后统一 flush, 有消耗就推一帧 usage
        _flush_token_usage(session_id, user_ip, end_state.get("token_meter") or {})

        EVENT_BUS.push(session_id, SSEEvent.CLOSE, {})

        TASK_MANAGER.set_status(session_id, TaskStatus.COMPLETE)

        return end_state
    except Exception as e:
        # 图抛异常时通道累计值随运行中止而不可达, 失败路径不落库
        # (计量为旁路, 不阻塞错误处理与关流)
        TASK_MANAGER.set_status(session_id, TaskStatus.FAILED)
        try:
            EVENT_BUS.push(session_id, SSEEvent.ERROR, {"error": str(e)})
        finally:
            # 失败路径也要关流: 与导入流对齐, 前端不需要再靠"error 后关流"的隐含约定
            EVENT_BUS.push(session_id, SSEEvent.CLOSE, {})
        logger.error(f"查询处理失败: {str(e)}")
        return {"reply": f"查询处理失败: {str(e)}"}
