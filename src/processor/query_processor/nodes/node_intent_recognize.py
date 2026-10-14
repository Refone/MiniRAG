from processor.query_processor.chat_history import chat_history_manager
from utils.node_utils import trace_node
from processor.query_processor.state import QueryGraphState


@trace_node(desc="意图识别", need_push=True)
def node_intent_recognize(state: QueryGraphState) -> QueryGraphState:

    chat_history_manager.save_message(
        session_id=state.get("session_id"),
        role="user",
        text=state.get("original_query"),
    )

    return {}
