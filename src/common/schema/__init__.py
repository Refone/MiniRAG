"""共享领域契约（tier 0）。

跨层共用的纯数据形状放这里，业务侧一律 `from common.schema import XXX`。
"""

from .doc import DocChunk, DocDetail, DocItem
from .token_usage import (
    ModelTokenUsage,
    TokenScope,
    TokenUsage,
    TokenUsageSnapshot,
    build_snapshot,
    empty_token_usage,
    sum_token_usage,
)

__all__ = [
    "DocChunk",
    "DocDetail",
    "DocItem",
    "ModelTokenUsage",
    "TokenScope",
    "TokenUsage",
    "TokenUsageSnapshot",
    "build_snapshot",
    "empty_token_usage",
    "sum_token_usage",
]
