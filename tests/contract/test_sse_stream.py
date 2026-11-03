from uuid import uuid4

import pytest

from common.events import EVENT_BUS, SSEEvent
from tests.support.sse import parse_sse

pytestmark = pytest.mark.contract


def test_sse__preloaded_frames__ready_delta_close_then_cleanup(client):
    """Given 通道已有 delta+close When 订阅 SSE Then ready→delta→close 并清理通道。"""
    session_id = f"test-{uuid4().hex}"
    EVENT_BUS.create(session_id)
    EVENT_BUS.push(session_id, SSEEvent.DELTA, {"delta": "你"})
    EVENT_BUS.push(session_id, SSEEvent.CLOSE, {})

    with client.stream("GET", f"/api/query/sse/{session_id}") as response:
        body = "".join(response.iter_text())

    frames = parse_sse(body)
    assert [frame.event for frame in frames] == [
        "ready",
        SSEEvent.DELTA,
        SSEEvent.CLOSE,
    ], f"期望 ready→delta→close，实际 {[frame.event for frame in frames]!r}"
    assert not EVENT_BUS.exists(session_id), "流结束后通道应被 sse_stream 清理"
