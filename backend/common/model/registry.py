"""模型角色绑定（tier 2）。

`get_llm` / `get_vlm` / `get_embedding` / `get_reranker` 是业务侧使用的访问器，
与供应商实现解耦：角色绑定哪个供应商实现在本文件声明，切换供应商只改这里。
访问器惰性构造，模块 import 不实例化任何模型。
"""

from functools import lru_cache

from .deepseek_flash import DeepSeekFlash
from .qwen3_vl_plus import Qwen3_VL_Plus
from .qwen_embedding import QwenEmbedding
from .qwen_reranker import QwenReranker


@lru_cache(maxsize=1)
def get_llm() -> DeepSeekFlash:
    """LLM 角色（DeepSeek）；首次调用时构造。"""
    return DeepSeekFlash()


@lru_cache(maxsize=1)
def get_vlm() -> Qwen3_VL_Plus:
    """VLM 角色（Qwen3-VL）；首次调用时构造。"""
    return Qwen3_VL_Plus()


@lru_cache(maxsize=1)
def get_embedding() -> QwenEmbedding:
    """Embedding 角色（Qwen text-embedding-v4）；首次调用时构造。"""
    return QwenEmbedding()


@lru_cache(maxsize=1)
def get_reranker() -> QwenReranker:
    """Reranker 角色（Qwen3.7-text-rerank）；首次调用时构造。"""
    return QwenReranker()
