from utils.node_utils import trace_node
from processor.query_processor.state import QueryGraphState


@trace_node(desc="重排序", need_push=True)
def node_rerank(state: QueryGraphState) -> QueryGraphState:

    import time

    time.sleep(1)  # 模拟处理时间

    return {}
