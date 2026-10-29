"""SSE 传输适配：把 `EVENT_BUS` 的通道转成 FastAPI 的流式响应。

**本模块是全仓唯一允许 import fastapi 的事件相关代码**（见 AGENTS.md 分层规则）：
`graphs` / `service` 只调 `EVENT_BUS.push`，不感知 HTTP。

循环结构（1s 一轮）：
1. 取走通道里已缓冲的事件并无条件吐出；
2. 检查客户端是否断开（`request.is_disconnected()`）；
3. `wait_for_event` 等新事件或超时，回到 1。

等待用 `asyncio.Event` + `call_soon_threadsafe` 唤醒，**不占线程**；
旧实现是每连接一个线程池线程轮询 `queue.Queue`。
"""

import asyncio
from collections.abc import AsyncIterator

from fastapi import Request

from common.events import EVENT_BUS, SSEEvent
from common.events.bus import sse_pack
from common.logging import logger

_POLL_INTERVAL = 1.0


async def sse_stream(sse_id: str, request: Request) -> AsyncIterator[str]:
    """订阅 `sse_id` 通道并持续产出 SSE 帧，直到 `__close__` 或客户端断开。"""
    if not EVENT_BUS.exists(sse_id):
        logger.warning("SSE 订阅的通道不存在（可能已过期）: {}", sse_id)
        return

    try:
        yield sse_pack(SSEEvent.READY, {})
        while True:
            for event, data in EVENT_BUS.take(sse_id):
                yield sse_pack(event, data)
                if event == SSEEvent.CLOSE:
                    return

            if await request.is_disconnected():
                logger.debug("SSE 客户端断开: {}", sse_id)
                break

            await EVENT_BUS.wait_for_event(sse_id, timeout=_POLL_INTERVAL)

    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        logger.debug("SSE 连接中断: {}", sse_id)
    finally:
        EVENT_BUS.remove(sse_id)


if __name__ == "__main__":
    import time

    class FakeRequest:
        """模拟 Starlette Request，只实现 sse_stream 用到的 is_disconnected()"""

        def __init__(self, disconnect_after: float = 3.0):
            self.disconnect_after = disconnect_after
            self._start: float | None = None

        async def is_disconnected(self) -> bool:
            if self._start is None:
                self._start = time.monotonic()
            return (time.monotonic() - self._start) > self.disconnect_after

    async def demo_consumer(sse_id: str, request: FakeRequest) -> None:
        print(f"--- 开始消费 session: {sse_id} ---")
        async for chunk in sse_stream(sse_id, request):
            print(f"<<< {chunk!r}")
        print(f"--- 消费结束 session: {sse_id} ---")

    async def demo_producer(sse_id: str) -> None:
        await asyncio.sleep(0.3)
        EVENT_BUS.push(sse_id, SSEEvent.PROGRESS, {"node": "node_entry", "pct": 10})
        await asyncio.sleep(0.3)
        EVENT_BUS.push(sse_id, SSEEvent.DELTA, {"delta": "你好"})
        await asyncio.sleep(0.3)
        EVENT_BUS.push(sse_id, SSEEvent.CLOSE, {})

    async def main() -> None:
        sse_id = "demo-session"
        EVENT_BUS.create(sse_id)
        request = FakeRequest(disconnect_after=5.0)
        await asyncio.gather(
            demo_consumer(sse_id, request),
            demo_producer(sse_id),
        )
        print("通道是否已清理:", not EVENT_BUS.exists(sse_id))

    asyncio.run(main())
