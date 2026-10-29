"""模型角色绑定（tier 2）。

`LLM` / `VLM` / `EMBEDDING` / `RERANKER` 是业务侧使用的角色名，
与供应商实现解耦：角色绑定哪个供应商实现在本文件声明，
切换供应商只改这里，供应商实现文件不感知角色名。
"""

from .deepseek_flash import DeepSeekFlash
from .qwen3_vl_plus import Qwen3_VL_Plus
from .qwen_embedding import QwenEmbedding
from .qwen_reranker import QwenReranker

# 角色 → 供应商实现：切换供应商时替换右侧实现
LLM = DeepSeekFlash()
VLM = Qwen3_VL_Plus()
EMBEDDING = QwenEmbedding()
RERANKER = QwenReranker()
