import pytest

from common.events import EVENT_BUS, SSEEvent
from common.events.metering import push_usage_delta

pytestmark = pytest.mark.unit


def test_usage_delta__invalid_kind_or_zero__not_pushed():
    """Given 非法 kind / 0 token / 空通道 When push Then 只保留合法增量。"""
    channel = "usage-delta"
    EVENT_BUS.create(channel)

    push_usage_delta(channel, "llm", 0)
    push_usage_delta(channel, "unknown", 5)
    push_usage_delta("", "llm", 5)
    push_usage_delta(channel, "llm", 5)

    assert EVENT_BUS.take(channel) == [
        (SSEEvent.USAGE_DELTA, {"kind": "llm", "tokens": 5})
    ]
