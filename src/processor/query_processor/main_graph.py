from langgraph.graph import END, StateGraph

from processor import query_processor
from processor.query_processor.state import QueryGraphState
from processor.query_processor.nodes import *

builder = StateGraph(QueryGraphState)

builder.add_node(node_intent_recognize)
builder.add_node(node_search_embedding)
builder.add_node(node_search_hyde)
builder.add_node(node_search_internet)
builder.add_node(node_rrf)
builder.add_node(node_rerank)
builder.add_node(node_answer_output)


def after_node_intent_recognize(state: QueryGraphState):
    if state.get("answer"):
        return "node_answer_output"
    return "node_search_embedding", "node_search_hyde", "node_search_internet"


builder.set_entry_point("node_intent_recognize")
builder.add_conditional_edges(
    "node_intent_recognize",
    after_node_intent_recognize,
    {
        "node_answer_output": "node_answer_output",
        "node_search_embedding": "node_search_embedding",
        "node_search_hyde": "node_search_hyde",
        "node_search_internet": "node_search_internet",
    },
)

builder.add_edge("node_search_embedding", "node_rrf")
builder.add_edge("node_search_hyde", "node_rrf")
builder.add_edge("node_search_internet", "node_rrf")
builder.add_edge("node_rrf", "node_rerank")
builder.add_edge("node_rerank", "node_answer_output")
builder.add_edge("node_answer_output", END)

query_processor = builder.compile()

if __name__ == "__main__":
    from utils.logging_utils import logger
    from processor.query_processor.state import get_default_state
    from rich import print as rprint

    logger.info("Starting query processor...")

    start = get_default_state()
    end = query_processor.invoke(start)
    rprint(end)

    logger.info("Query processor finished.")
