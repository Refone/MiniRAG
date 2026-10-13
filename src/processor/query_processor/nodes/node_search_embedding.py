from utils.node_utils import trace_node
from processor.query_processor.state import QueryGraphState


@trace_node(desc="向量化查询", need_push=True)
def node_search_embedding(state: QueryGraphState) -> QueryGraphState:

    import time

    time.sleep(1)  # 模拟处理时间

    return {}
