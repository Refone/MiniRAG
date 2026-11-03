import pytest

from graphs.query_graph.query_graph import after_node_intent_recognize

pytestmark = pytest.mark.unit


def test_route__flags__correct_nodes():
    """Given HyDE/联网开关 When 路由 Then 只返回启用的检索节点。"""
    embedding = "node_search_embedding"
    hyde = "node_search_hyde"
    web = "node_search_web"

    assert after_node_intent_recognize(
        {"enable_hyde": False, "enable_web_search": False}
    ) == [embedding]
    assert after_node_intent_recognize(
        {"enable_hyde": True, "enable_web_search": False}
    ) == [embedding, hyde]
    assert after_node_intent_recognize(
        {"enable_hyde": False, "enable_web_search": True}
    ) == [embedding, web]
    assert after_node_intent_recognize(
        {"enable_hyde": True, "enable_web_search": True}
    ) == [embedding, hyde, web]
