from common import client
from common.events.tracing import step_log, trace_node
from common.logging import logger
from graphs.query_graph.query_graph_state import QueryGraphState


@step_log(desc="校验并获取数据")
def step_1_validate_and_get_data(state: QueryGraphState) -> tuple[bool, str]:
    web_search_enable = state.get("enable_web_search", False)
    rewritten_query = state.get("rewritten_query", "")
    if not rewritten_query:
        raise ValueError("state['rewritten_query'] is empty")
    return web_search_enable, rewritten_query


@step_log(desc="调用 MCP 工具进行网络搜索")
def step_2_call_mcp_tool(rewritten_query: str) -> list[dict]:
    return client.search_web(rewritten_query)


@trace_node(desc="互联网搜索", need_push=True)
def node_search_web(state: QueryGraphState) -> QueryGraphState:

    web_search_enable, rewritten_query = step_1_validate_and_get_data(state)
    logger.info(f"重写后的查询: {rewritten_query}")

    search_results = []
    if web_search_enable:
        search_results = step_2_call_mcp_tool(rewritten_query)
    logger.info(f"是否启用网络搜索: {web_search_enable}")
    logger.info(f"网络搜索结果: {search_results}")

    return {"web_matches": search_results}


if __name__ == "__main__":
    from rich import print as rprint

    from common.config.path_config import snapshot_path
    from graphs.query_graph.query_graph_state import load_state, save_state

    prev_state = load_state(snapshot_path("query_01_intent_recognize.json"))
    prev_state["enable_web_search"] = True
    next_state = node_search_web(prev_state)
    rprint(next_state)

    new_state_json = snapshot_path("query_04_search_web.json")

    save_state(next_state, new_state_json)
    logger.info("互联网搜索处理完成")
    logger.info(f"状态保存路径: {new_state_json}")
