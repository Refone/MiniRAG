"""模型调用 usage 提取助手（tier 2，纯函数）。

从 LangChain 消息 / dashscope 响应中读取本次调用的 token 数，供调用节点
拼装 token_meter 增量。不持有任何状态、不注册任何回调、不依赖 contextvars：
usage 直接取自响应（invoke 返回的消息、流式末段 chunk、structured output 的
raw 消息、dashscope resp 的 usage 段）。
"""

from typing import Any


def message_usage_tokens(message: Any) -> int:
    """从 AIMessage / AIMessageChunk 的 usage_metadata 提取 token 总数。

    stream_usage=True 时, 流式末段 chunk 才携带 usage_metadata; 其余消息
    返回 0。
    """
    usage = getattr(message, "usage_metadata", None)
    if not usage:
        return 0
    return int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)


def dashscope_total_tokens(usage: Any) -> int:
    """从 dashscope 响应的 usage 段提取 token 总数（embedding / rerank 通用）。

    rerank 返回 input_tokens / output_tokens，embedding 返回 total_tokens，
    两种形状可能只出现其一。
    """
    if not isinstance(usage, dict):
        return 0
    total = int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)
    if total:
        return total
    return int(usage.get("total_tokens") or 0)
