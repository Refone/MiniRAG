from .qwen_embedding import QwenEmbedding
from .qwen_reranker import QwenReranker
from .deepseek_flash import DeepSeekFlash
from .qwen3_vl_plus import Qwen3_VL_Plus

EMBEDDING = QwenEmbedding()
RERANKER = QwenReranker()
LLM = DeepSeekFlash()
VLM = Qwen3_VL_Plus()
