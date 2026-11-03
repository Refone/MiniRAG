import pytest

from common.events.event_bus import InMemoryEventBus, sse_pack

pytestmark = pytest.mark.unit


def test_bus__overflow__drops_oldest_and_clear_all():
    """Given 缓冲上限 2 When push 3 条 Then 丢最旧；clear_all 清空通道。"""
    bus = InMemoryEventBus(max_events=2)
    bus.create("c")

    bus.push("c", "e0", {"i": 0})
    bus.push("c", "e1", {"i": 1})
    bus.push("c", "e2", {"i": 2})

    assert bus.take("c") == [("e1", {"i": 1}), ("e2", {"i": 2})]
    assert bus.channel_count() == 1

    bus.clear_all()
    assert bus.channel_count() == 0
    assert bus.take("c") == []


def test_sse_pack__format__event_and_json_data():
    """Given 事件与数据 When sse_pack Then 输出标准 SSE 帧。"""
    frame = sse_pack("delta", {"delta": "你好"})

    assert frame.startswith("event: delta\ndata: ")
    assert frame.endswith("\n\n")
    assert '"你好"' in frame
