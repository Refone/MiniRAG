from .qwen_embedding import QwenEmbedding
from .deepseek_flash import DeepSeekFlash
from .qwen_vl_32b import Qwen_VL_32B

EMBEDDING = QwenEmbedding()
LLM = DeepSeekFlash()
VLM = Qwen_VL_32B()
