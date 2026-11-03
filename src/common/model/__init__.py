"""模型设施（tier 2）：LLM / VLM / Embedding / Reranker。

角色与供应商实现的绑定集中在 `registry`，这里只 re-export 访问器，
业务侧一律 `from common import model` 后调用 `model.get_llm()`。
"""

from .registry import get_embedding, get_llm, get_reranker, get_vlm

__all__ = ["get_llm", "get_vlm", "get_embedding", "get_reranker"]
