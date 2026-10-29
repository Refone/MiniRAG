"""共享领域契约（tier 0）。

跨层共用的纯数据形状放这里，业务侧一律 `from common.schema import XXX`。
"""

from .doc import DocChunk, DocDetail, DocItem

__all__ = ["DocChunk", "DocDetail", "DocItem"]
