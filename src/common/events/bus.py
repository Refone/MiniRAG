"""SSE 事件总线（**不 import fastapi**）。

线程模型
--------
生产者是 LangGraph 的同步节点（跑在线程池里），消费者是 FastAPI 的异步流。
`push()` 只做两件事：把事件追加到该通道的 `list` 缓冲、通过
`loop.call_soon_threadsafe(wake.set)` 唤醒等待者——**不占线程、不轮询**。

（旧实现是 `queue.Queue` + 每个连接一个线程池线程 `run_in_executor(get, 0.1s)`，
连接数一多就把默认线程池顶穿。）

生命周期
--------
- `create()` 在 POST 受理任务时调用（此时还没有订阅者，先缓冲）；
- `take()` / `wait_for_event()` 由 `api/sse.py` 的流循环调用；
- 客户端从不连 SSE 时通道会残留，由 `sweep(ttl)` 兜底回收（lifespan 里定时跑）。

缓冲上限：单通道超过 `sse_channel_max_events` 时丢最旧并告警，避免异常任务撑爆内存。
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from common.config.app_config import APP_CONFIG
from common.logging import logger

__DEBUG__ = False


class SSEEvent:
    READY = "ready"  # 连接建立
    PROGRESS = "progress"  # 任务节点进度
    FORK = "fork"  # ZIP 解析完成, 下发 md 子任务清单
    CHILD_PROGRESS = "child-progress"  # 单个 md 子任务的进度快照
    DELTA = "delta"  # LLM 流式输出增量
    FINAL = "final"  # 最终完整答案
    ERROR = "error"  # 错误信息
    CLOSE = "__close__"  # 关闭连接信号


def _debug_print(msg: str) -> None:
    if __DEBUG__:
        print(msg)


def sse_pack(event: str, data: dict[str, Any]) -> str:
    """把一条事件编码为 SSE 帧。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@dataclass
class _Channel:
    channel_id: str
    buffer: list[tuple[str, dict]] = field(default_factory=list)
    created_at: float = field(default_factory=time.monotonic)
    last_access: float = field(default_factory=time.monotonic)
    dropped: int = 0
    wake: asyncio.Event | None = None
    loop: asyncio.AbstractEventLoop | None = None


class InMemoryEventBus:
    """进程内单机事件总线（可替换为 Redis 实现，接口保持）。"""

    def __init__(self, max_events: int | None = None) -> None:
        self._max_events = max_events or APP_CONFIG.sse_channel_max_events
        self._channels: dict[str, _Channel] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------- 生命周期
    def create(self, channel_id: str) -> None:
        with self._lock:
            if channel_id not in self._channels:
                self._channels[channel_id] = _Channel(channel_id=channel_id)
        _debug_print(f"[SSE] channel created: {channel_id}")

    def remove(self, channel_id: str) -> None:
        with self._lock:
            self._channels.pop(channel_id, None)
        _debug_print(f"[SSE] channel removed: {channel_id}")

    def exists(self, channel_id: str) -> bool:
        with self._lock:
            return channel_id in self._channels

    def channel_count(self) -> int:
        with self._lock:
            return len(self._channels)

    def sweep(self, ttl_seconds: float) -> int:
        """清掉 `ttl_seconds` 内无任何读写的通道，返回清理数量。"""
        cutoff = time.monotonic() - ttl_seconds
        with self._lock:
            stale = [
                cid for cid, ch in self._channels.items() if ch.last_access < cutoff
            ]
            for cid in stale:
                self._channels.pop(cid, None)
        return len(stale)

    # ----------------------------------------------------------------- 生产
    def push(self, channel_id: str, event: str, data: dict[str, Any]) -> None:
        with self._lock:
            ch = self._channels.get(channel_id)
            if ch is None:
                _debug_print(f"[SSE] no channel for {channel_id}, drop {event}")
                return
            ch.buffer.append((event, data))
            ch.last_access = time.monotonic()
            if len(ch.buffer) > self._max_events:
                overflow = len(ch.buffer) - self._max_events
                del ch.buffer[:overflow]
                ch.dropped += overflow
                logger.warning(
                    "SSE 通道缓冲溢出: channel={}, 丢弃 {} 条最旧事件(累计 {})",
                    channel_id,
                    overflow,
                    ch.dropped,
                )
            wake, loop = ch.wake, ch.loop

        if wake is not None and loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(wake.set)

    # ----------------------------------------------------------------- 消费
    def take(self, channel_id: str) -> list[tuple[str, dict]]:
        """取走当前缓冲的全部事件（非阻塞）。"""
        with self._lock:
            ch = self._channels.get(channel_id)
            if ch is None:
                return []
            batch, ch.buffer = ch.buffer, []
            ch.last_access = time.monotonic()
            return batch

    async def wait_for_event(self, channel_id: str, timeout: float = 1.0) -> None:
        """等待新事件或超时（给调用方留出检查客户端断开的空隙）。"""
        with self._lock:
            ch = self._channels.get(channel_id)
            if ch is None:
                await asyncio.sleep(timeout)
                return
            if ch.wake is None:
                ch.wake = asyncio.Event()
            ch.loop = asyncio.get_running_loop()
            ch.last_access = time.monotonic()
            wake = ch.wake

        try:
            await asyncio.wait_for(wake.wait(), timeout=timeout)
        except TimeoutError:
            pass
        finally:
            wake.clear()


EVENT_BUS = InMemoryEventBus()
