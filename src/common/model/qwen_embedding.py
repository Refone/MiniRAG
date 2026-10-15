from typing import TypedDict

from dashscope import TextEmbedding

from common.config.env_config import ENV_CONFIG
from common.model.rate_limiter import SlidingWindowRateLimiter


class HybridVector(TypedDict):
    """稠密 + 稀疏混合向量。"""

    dense: list[float]
    sparse: dict[int, float]


# https://www.qianwenai.com/models/text-embedding-v4
class QwenEmbedding:
    """Qwen text-embedding-v4 嵌入模型（稠密 + 稀疏混合）。

    供 Milvus 稠密 + 稀疏混合检索使用。
    text_type 区分 document(适合被匹配) 与 query(适合去匹配)。

    (没有继承 Embeddings 因为 Embeddings 只支持稠密向量)
    """

    def __init__(self):
        self._model = ENV_CONFIG.embedding.model
        self._dense_dimension = ENV_CONFIG.embedding.dense_dimension
        self._api_key = ENV_CONFIG.qwen.api_key
        self._limiter = SlidingWindowRateLimiter(ENV_CONFIG.embedding.rpm)

    # ---- 项目自定义：混合向量（稠密 + 稀疏） ----
    def embed_document_hybrid(self, texts: list[str]) -> list[HybridVector]:
        """嵌入文本列表，返回稠密 + 稀疏混合向量（默认按 document）。"""
        return self._embed(texts, text_type="document")

    def embed_query_hybrid(self, texts: list[str]) -> list[HybridVector]:
        """查询文本的混合向量（text_type=query）。"""
        return self._embed(texts, text_type="query")

    # ---- 内部实现 ----
    def _embed(self, texts: list[str], *, text_type: str) -> list[HybridVector]:
        self._limiter.acquire()  # 在调用嵌入接口前进行速率限制

        resp = TextEmbedding.call(
            model=self._model,
            api_key=self._api_key,
            input=texts,
            output_type="dense&sparse",  # 同时返回稠密和稀疏向量
            text_type=text_type,  # document / query
            dimension=self._dense_dimension,  # 稠密向量的维度（不影响稀疏向量）
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"TextEmbedding 调用失败: code={resp.status_code}, "
                f"message={getattr(resp, 'message', resp)}"
            )

        result: list[HybridVector] = []
        for emb in resp["output"]["embeddings"]:
            sparse_obj = emb.get("sparse_embedding") or {}
            result.append(
                {
                    "dense": emb["embedding"],
                    "sparse": {
                        int(item["index"]): float(item["value"]) for item in sparse_obj
                    },
                }
            )

        return result


if __name__ == "__main__":
    from rich import print as rprint

    embedding = QwenEmbedding()
    result = embedding.embed_document_hybrid(["Hello World", "Hello RAG", "你好, 朋友"])
    for i, r in enumerate(result):
        rprint(f"Text {i}:")
        rprint(f"  Dense: {r['dense'][0:5]}")
        rprint(f"  Sparse: {r['sparse']}")
