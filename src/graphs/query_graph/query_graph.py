from langgraph.graph import END, StateGraph

from graphs.query_graph.nodes import (
    node_answer_output,
    node_intent_recognize,
    node_rrf_and_rerank,
    node_search_embedding,
    node_search_hyde,
    node_search_web,
)
from graphs.query_graph.query_graph_state import QueryGraphState

builder = StateGraph(QueryGraphState)

builder.add_node(node_intent_recognize)
builder.add_node(node_search_embedding)
builder.add_node(node_search_hyde)
builder.add_node(node_search_web)
builder.add_node(node_rrf_and_rerank)
builder.add_node(node_answer_output)


def after_node_intent_recognize(state: QueryGraphState):
    if state.get("answer"):
        return "node_answer_output"
    # 勾选HyDE 搜索时才进入HyDE 搜索节点, 否则跳过 node_search_hyde
    # 勾选网络搜索时才进入联网搜索节点, 否则跳过 node_search_web
    next_nodes = ["node_search_embedding"]
    if state.get("enable_hyde"):
        next_nodes.append("node_search_hyde")
    if state.get("enable_web_search"):
        next_nodes.append("node_search_web")
    return next_nodes


builder.set_entry_point("node_intent_recognize")
builder.add_conditional_edges(
    "node_intent_recognize",
    after_node_intent_recognize,
    {
        "node_answer_output": "node_answer_output",
        "node_search_embedding": "node_search_embedding",
        "node_search_hyde": "node_search_hyde",
        "node_search_web": "node_search_web",
    },
)

builder.add_edge("node_search_embedding", "node_rrf_and_rerank")
builder.add_edge("node_search_hyde", "node_rrf_and_rerank")
builder.add_edge("node_search_web", "node_rrf_and_rerank")
builder.add_edge("node_rrf_and_rerank", "node_answer_output")
builder.add_edge("node_answer_output", END)

query_graph = builder.compile()

if __name__ == "__main__":
    from rich import print as rprint

    from common.logging import logger
    from graphs.query_graph.query_graph_state import create_state

    logger.info("Starting query graph...")

    start = create_state(
        session_id="test-flow-session-id",
        original_query="使用 HAK180 时，有什么注意事项？",
    )
    end = query_graph.invoke(start)
    rprint(end)

    logger.info("Query graph finished.")
