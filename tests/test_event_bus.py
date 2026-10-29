"""EventBus：缓冲、唤醒与回收。

关键不变式（替换旧 `queue.Queue` 实现时必须保持）：
1. **先 push 后订阅** 的事件不能丢——POST 受理任务后前端才连 SSE；
2. push 能唤醒正在等待的消费者（线程 → 事件循环跨越）；
3. 缓冲有上限，超限丢**最旧**；
4. 没人订阅的通道能被 `sweep` 回收。
"""

import asyncio
import time

from common.events.bus import InMemoryEventBus, SSEEvent


def test_push_before_subscribe_is_buffered():
    bus = InMemoryEventBus(max_events=10)
    bus.create("c")

    bus.push("c", SSEEvent.PROGRESS, {"n": 1})

    assert bus.take("c") == [(SSEEvent.PROGRESS, {"n": 1})]
    assert bus.take("c") == []


def test_overflow_drops_oldest():
    bus = InMemoryEventBus(max_events=2)
    bus.create("c")

    for i in range(4):
        bus.push("c", "e", {"i": i})

    assert [payload["i"] for _, payload in bus.take("c")] == [2, 3]


def test_wait_for_event_wakes_on_push():
    async def scenario() -> list:
        bus = InMemoryEventBus(max_events=10)
        bus.create("c")

        async def producer() -> None:
            await asyncio.sleep(0.05)
            bus.push("c", SSEEvent.DELTA, {"delta": "x"})

        await asyncio.gather(producer(), bus.wait_for_event("c", timeout=2.0))
        return bus.take("c")

    assert asyncio.run(scenario()) == [(SSEEvent.DELTA, {"delta": "x"})]


def test_wait_for_event_times_out_without_blocking():
    async def scenario() -> float:
        bus = InMemoryEventBus(max_events=10)
        bus.create("c")
        started = time.monotonic()
        await bus.wait_for_event("c", timeout=0.05)
        return time.monotonic() - started

    assert asyncio.run(scenario()) >= 0.04


def test_push_to_missing_channel_is_noop():
    bus = InMemoryEventBus(max_events=10)

    bus.push("ghost", SSEEvent.PROGRESS, {})  # 不抛异常

    assert bus.take("ghost") == []


def test_sweep_removes_idle_channel():
    bus = InMemoryEventBus(max_events=10)
    bus.create("idle")
    time.sleep(0.01)

    assert bus.sweep(0.001) == 1
    assert not bus.exists("idle")
