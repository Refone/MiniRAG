"""模型设施（tier 2）：LLM / VLM / Embedding / Reranker。

角色与供应商实现的绑定集中在 `registry`，这里只 re-export，
业务侧一律 `from common.model import XXX`。
"""

from .registry import EMBEDDING, LLM, RERANKER, VLM

__all__ = ["LLM", "VLM", "EMBEDDING", "RERANKER"]
