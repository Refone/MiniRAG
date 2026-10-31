"""模型调用级 Token 增量推送（usage-delta 事件）。

节点在每次模型调用（LLM / VLM / Embedding / Reranker）返回后立即调用
`push_usage_delta`, 前端据此在请求运行期间即时弹「+N 模型」气泡；
总账仍由 service 在请求结束时 flush 落库并推 usage 快照帧。
"""

from .event_bus import EVENT_BUS, SSEEvent

USAGE_DELTA_KINDS = ("llm", "vlm", "embedding", "reranker")


def push_usage_delta(channel_id: str, kind: str, tokens: int) -> None:
    """推一帧 usage-delta（通道为空 / 无消耗 / 未知模型时不推）。"""
    if not channel_id or not tokens or tokens <= 0:
        return
    if kind not in USAGE_DELTA_KINDS:
        return
    EVENT_BUS.push(channel_id, SSEEvent.USAGE_DELTA, {"kind": kind, "tokens": tokens})
