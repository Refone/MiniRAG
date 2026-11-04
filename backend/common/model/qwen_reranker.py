from typing import TypedDict

from dashscope import TextReRank

from common.config.env_config import ENV_CONFIG
from common.model.metering import dashscope_total_tokens
from common.model.rate_limiter import SlidingWindowRateLimiter


class QwenRerankResult(TypedDict):
    """单条候选文档的重排序结果。"""

    index: int  # 原始 documents 列表中的下标
    relevance_score: float  # 与 query 的相关性得分
    document: dict | None  # 原文档(return_documents=True 时返回)


# https://www.qianwenai.com/models/qwen3.7-text-rerank
class QwenReranker:
    """Qwen3.7-text-rerank 文本重排序模型封装。

    对 query 与候选 documents 计算相关性得分，并按得分降序返回，
    供 RRF 融合后的切片精排使用。
    """

    def __init__(self):
        self._model = ENV_CONFIG.dashscope.rerank_model
        self._api_key = ENV_CONFIG.dashscope.api_key
        self._limiter = SlidingWindowRateLimiter(ENV_CONFIG.dashscope.rerank_rpm)

    def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_n: int | None = None,
        return_documents: bool = False,
    ) -> tuple[list[QwenRerankResult], int]:
        """对候选文档进行重排序, 返回 (结果列表, 本次调用 token 数)。

        输出格式(按相关性得分降序):
        [
            {
                "index": int,  # 原始 documents 列表中的下标
                "relevance_score": float,  # 与 query 的相关性得分
                "document": dict | None,  # 原文档(return_documents=True 时返回)
            },
            ...
        ]
        """
        self._limiter.acquire()  # 在调用重排序接口前进行速率限制

        resp = TextReRank.call(
            model=self._model,
            query=query,
            documents=documents,
            top_n=top_n,
            return_documents=return_documents,
            api_key=self._api_key,
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"TextReRank 调用失败: code={resp.status_code}, "
                f"message={getattr(resp, 'message', resp)}"
            )

        results: list[QwenRerankResult] = []
        for item in resp["output"]["results"]:
            results.append(
                {
                    "index": int(item["index"]),
                    "relevance_score": float(item["relevance_score"]),
                    "document": item.get("document"),
                }
            )

        # 保险起见显式按相关性降序(API 通常已按此顺序返回)
        results.sort(key=lambda r: r["relevance_score"], reverse=True)

        return results, dashscope_total_tokens(resp.get("usage"))


if __name__ == "__main__":
    from rich import print as rprint

    reranker = QwenReranker()
    results, tokens = reranker.rerank(
        query="什么是文本排序模型",
        documents=[
            "文本排序模型广泛用于搜索引擎和推荐系统中，它们根据文本相关性对候选文本进行排序",
            "量子计算是计算科学的一个前沿领域",
            "预训练语言模型的发展给文本排序模型带来了新的进展",
        ],
        return_documents=True,
    )
    for r in results:
        rprint(f"[{r['index']}] score={r['relevance_score']:.4f} text={r['document']}")
    rprint(f"Tokens: {tokens}")
