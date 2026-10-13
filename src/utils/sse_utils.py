import queue
import json
import asyncio
from typing import Any

from requests import Request


class SSEEvent:
    READY = "ready"  # 连接建立
    PROGRESS = "progress"  # 任务节点进度
    DELTA = "delta"  # LLM 流式输出增量
    FINAL = "final"  # 最终完整答案
    ERROR = "error"  # 错误信息
    CLOSE = "__close__"  # 关闭连接信号


_session_stream: dict[str, queue.Queue] = {}


def get_sse_queue(session_id: str) -> queue.Queue | None:
    return _session_stream.get(session_id)


def create_sse_queue(session_id: str) -> queue.Queue:
    print(f"[SSE] queue created for session_id: {session_id}")
    _session_stream[session_id] = queue.Queue()
    return _session_stream[session_id]


def remove_sse_queue(session_id: str) -> None:
    print(f"[SSE] queue removed for session_id: {session_id}")
    _session_stream.pop(session_id, None)


def _sse_pack(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def push_to_session(session_id: str, event: str, data: dict[str, Any]) -> None:
    print(f"[SSE] Pushing to SSE queue for session_id: {session_id}")
    sse_queue = get_sse_queue(session_id)
    if sse_queue:
        sse_queue.put({"event": event, "data": data})
    else:
        raise ValueError(f"No SSE queue found for session_id: {session_id}")


async def sse_generator(session_id: str, request: Request):
    stream_queue = get_sse_queue(session_id)
    if not stream_queue:
        return

    loop = asyncio.get_event_loop()
    try:
        yield _sse_pack(SSEEvent.READY, {})
        print(f"[SSE] {session_id}: sending ready signal")

        while True:
            if await request.is_disconnected():
                # 前端调用 es.close() 断开连接
                print(f"[SSE] {session_id}: client disconnected")
                break

            try:
                msg = await loop.run_in_executor(
                    None, stream_queue.get, True, 0.1  # 阻塞等待  # 超时时间
                )
            except queue.Empty:
                continue

            event = msg["event"]
            data = msg["data"]

            print(f"[SSE] {session_id}: sending event: {event}, data: {data}")
            yield _sse_pack(event, data)

            if event == SSEEvent.CLOSE:
                print(f"[SSE] {session_id}: received close signal")
                break

    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError) as e:
        print(f"[SSE] {session_id}: client disconnected: {e}")
    except Exception as e:
        print(f"[SSE] {session_id}: encountered exception: {e}")
    finally:
        print(f"[SSE] {session_id}: closing SSE generator")
        remove_sse_queue(session_id)


if __name__ == "__main__":
    import time

    class FakeRequest:
        """模拟 Starlette Request，只实现 sse_generator 用到的 is_disconnected()"""

        def __init__(self, disconnect_after: float = 3.0):
            self.disconnect_after = disconnect_after
            self._start: float | None = None

        async def is_disconnected(self) -> bool:
            if self._start is None:
                self._start = time.monotonic()
            return (time.monotonic() - self._start) > self.disconnect_after

    async def demo_consumer(session_id: str, request: FakeRequest) -> None:
        print(f"--- 开始消费 session: {session_id} ---")
        async for chunk in sse_generator(session_id, request):
            print(f"<<< {chunk!r}")
        print(f"--- 消费结束 session: {session_id} ---")

    async def demo_producer(session_id: str) -> None:
        await asyncio.sleep(0.2)
        push_to_session(
            session_id, SSEEvent.PROGRESS, {"node": "parse_query", "pct": 10}
        )

        await asyncio.sleep(0.2)
        push_to_session(session_id, SSEEvent.DELTA, {"text": "你好"})

        await asyncio.sleep(0.2)
        push_to_session(session_id, SSEEvent.DELTA, {"text": "，世界"})

        await asyncio.sleep(0.2)
        push_to_session(session_id, SSEEvent.FINAL, {"answer": "你好，世界"})

        await asyncio.sleep(0.2)
        push_to_session(session_id, SSEEvent.CLOSE, {})

    async def main() -> None:
        session_id = "demo-session"

        # 生产者会在 ~1s 内推完全部事件，客户端 5s 后才算断开
        create_sse_queue(session_id)
        request = FakeRequest(disconnect_after=5.0)

        await asyncio.gather(
            demo_consumer(session_id, request),
            demo_producer(session_id),
        )

        # 验证 finally 里确实清理了队列
        print("队列是否已清理:", get_sse_queue(session_id) is None)

    asyncio.run(main())
