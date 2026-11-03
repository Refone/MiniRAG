"""Token 计量纯函数单测（零外部依赖）。

覆盖 usage 提取（LangChain 消息 / dashscope 响应）、TokenUsage 累加 reducer
与快照组装。Mongo 读写与模型链路仍靠节点 `__main__` 点火 + 方案验收条件
人工核对。
"""

import pytest
from langchain_core.messages import AIMessage

from common.model.metering import dashscope_total_tokens, message_usage_tokens
from common.schema.token_usage import (
    ModelTokenUsage,
    TokenUsage,
    build_snapshot,
    empty_token_usage,
    sum_token_usage,
)

pytestmark = pytest.mark.unit


def test_message_usage_tokens():
    message = AIMessage(
        content="hi",
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )
    assert message_usage_tokens(message) == 15


def test_message_usage_tokens_missing():
    message = AIMessage(content="hi", usage_metadata=None)
    assert message_usage_tokens(message) == 0
    assert message_usage_tokens("not-a-message") == 0


def test_dashscope_total_tokens():
    assert dashscope_total_tokens({"input_tokens": 7, "output_tokens": 3}) == 10
    assert dashscope_total_tokens({"total_tokens": 9}) == 9
    assert dashscope_total_tokens(None) == 0


def test_empty_token_usage():
    assert empty_token_usage() == {
        "llm_tokens": 0,
        "vlm_tokens": 0,
        "embedding_tokens": 0,
        "reranker_tokens": 0,
    }


def test_sum_token_usage_accumulates_deltas():
    """模拟通道 reducer: 累计值 + 节点增量 → 新的累计值。"""
    base = empty_token_usage()
    base = sum_token_usage(base, TokenUsage(llm_tokens=100, embedding_tokens=30))
    base = sum_token_usage(base, TokenUsage(llm_tokens=50, reranker_tokens=20))
    assert base == {
        "llm_tokens": 150,
        "vlm_tokens": 0,
        "embedding_tokens": 30,
        "reranker_tokens": 20,
    }


def test_sum_token_usage_tolerates_none_and_partial():
    base = sum_token_usage(None, None)
    assert base == empty_token_usage()
    base = sum_token_usage(base, {"llm_tokens": 5})
    assert base["llm_tokens"] == 5
    assert base["vlm_tokens"] == 0


def test_build_snapshot_derives_totals():
    query = ModelTokenUsage(llm_tokens=620, embedding_tokens=905, reranker_tokens=350)
    upload = ModelTokenUsage(llm_tokens=486, vlm_tokens=1264, embedding_tokens=890)
    snapshot = build_snapshot("sess-x", query=query, upload=upload, updated_at=1.5)
    assert snapshot.llm_tokens == 1106
    assert snapshot.vlm_tokens == 1264
    assert snapshot.embedding_tokens == 1795
    assert snapshot.reranker_tokens == 350
    assert snapshot.total_tokens == 4515
    assert snapshot.query.total_tokens == 1875
    assert snapshot.upload.total_tokens == 2640
    assert snapshot.updated_at == 1.5


def test_build_snapshot_empty():
    snapshot = build_snapshot("sess-y")
    assert snapshot.total_tokens == 0
    assert snapshot.updated_at is None
    assert snapshot.user_ip == ""
