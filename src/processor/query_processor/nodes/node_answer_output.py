from utils.node_utils import trace_node
from processor.query_processor.state import QueryGraphState


@trace_node(desc="答案输出")
def node_answer_output(state: QueryGraphState) -> QueryGraphState:

    # FAKE:
    base_answer = f"这是关于 \"{state.get('original_query')}\" 的测试回答，正在演示打字机流式输出效果"

    final_text = ""
    for ch in base_answer:
        final_text += ch

    return {}
