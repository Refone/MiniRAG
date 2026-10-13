from utils.node_utils import trace_node
from processor.query_processor.state import QueryGraphState


@trace_node(desc="意图识别")
def node_intent_recognize(state: QueryGraphState) -> QueryGraphState:

    import time

    time.sleep(1)  # 模拟处理时间

    return {}
