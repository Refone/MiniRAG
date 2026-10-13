from utils.node_utils import trace_node
from processor.query_processor.state import QueryGraphState


@trace_node(desc="互联网搜索")
def node_search_internet(state: QueryGraphState) -> QueryGraphState:

    import time

    time.sleep(1)  # 模拟处理时间

    return {}
