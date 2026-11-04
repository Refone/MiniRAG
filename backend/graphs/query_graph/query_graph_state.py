import copy
import json
from typing import Annotated, TypedDict

from common.client.milvus_client import MilvusChunksRecall
from common.schema import WebSearchResult
from common.schema.token_usage import TokenUsage, sum_token_usage


class DataFrom:
    MILVUS: str = "Milvus"
    WEB: str = "Web"


class RerankResult(TypedDict):
    """
    重排序结果
    {
        'document': '巴黎是法国的首都。',
        'data_from': 'Milvus',
        'score': 0.95
    }
    """

    document: str  # 文档内容
    data_from: str  # 文档来源
    score: float  # 重排序得分


class QueryGraphState(TypedDict):
    session_id: str  # 会话 ID
    original_query: str  # 原始查询
    enable_web_search: bool  # 是否进行网络搜索
    enable_hyde: bool  # 是否进行HyDE 搜索

    rewritten_query: str  # 重写后的问题 (一级召回的查询文本, 直接匹配 docs 双向量)

    # minirag_docs 一级召回匹配结果 (对象为文档)
    confirm_list: list[int]  # 确认匹配的文档 id 列表 (二级召回唯一 doc_id 源)
    suspect_list: list[int]  # 疑似匹配的文档 id 列表 (confirm 为空时用于兜底提示)
    suspect_titles: list[str]  # 疑似文档标题 (兜底回答时提示用户)

    embedding_recalls: list[MilvusChunksRecall]  # 向量化查询匹配结果
    hyde_recalls: list[MilvusChunksRecall]  # HyDE 搜索匹配结果
    web_matches: list[WebSearchResult]  # 互联网搜索匹配结果

    rerank_results: list[RerankResult]  # 重排序结果

    # Token 计量累计值 (纯数据, 可 JSON 序列化): 消耗 token 的节点在结束时
    # 返回本节点的增量, 通道经 sum_token_usage reducer 逐字段累加;
    # 节点不得返回累计值本身 (会重复累加), 流结束由 service 读取并落库
    token_meter: Annotated[TokenUsage, sum_token_usage]


_DEFAULT_STATE: QueryGraphState = {
    "session_id": "",
    "original_query": "",
    "enable_web_search": True,
    "enable_hyde": True,
    "rewritten_query": "",
    "confirm_list": [],
    "suspect_list": [],
    "suspect_titles": [],
    "embedding_recalls": [],
    "hyde_recalls": [],
    "web_matches": [],
    "rerank_results": [],
    "token_meter": {
        "llm_tokens": 0,
        "vlm_tokens": 0,
        "embedding_tokens": 0,
        "reranker_tokens": 0,
    },
}


def create_state(**state_dict) -> QueryGraphState:
    state = copy.deepcopy(_DEFAULT_STATE)
    state.update(state_dict)
    return state


def save_state(state: QueryGraphState, file_path: str) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=4)


def load_state(file_path: str) -> QueryGraphState:
    with open(file_path, "r", encoding="utf-8") as f:
        state = json.load(f)
    return state


if __name__ == "__main__":
    from rich import print as rprint

    from common.config.path_config import snapshot_path

    state = create_state(
        session_id="12345", original_query="What is the capital of France?"
    )
    rprint(state)
    save_state(state, snapshot_path("query_state_test.json"))
