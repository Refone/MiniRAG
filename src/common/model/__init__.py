from .qwen_embedding import QwenEmbedding
from .qwen_reranker import QwenReranker
from .deepseek_flash import DeepSeekFlash
from .qwen_vl_32b import Qwen_VL_32B

EMBEDDING = QwenEmbedding()
RERANKER = QwenReranker()
LLM = DeepSeekFlash()
VLM = Qwen_VL_32B()
