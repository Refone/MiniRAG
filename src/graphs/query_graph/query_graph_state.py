from typing import TypedDict
import copy
import json

from enum import Enum

from common.client.milvus_client import MilvusChunksRecall


class WebSearchResult(TypedDict):
    """
    调用联网搜索 MCP 获得的搜索结果
    {
        'snippet': '如何使用电阻表测量电阻? 1. 断开...',
        'hostname': '百度教育',
        'hostlogo': 'https://mbs1.bdstatic.com/searchbox/mappconsole/image/20230906/3096e08a-869d-46a7-8d30-5e32adb66fdc.png',
        'title': '如何使用电阻表测量电阻?',
        'url': 'https://easylearn.baidu.com/edu-page/tiangong/questiondetail?id=1832280139494591726&fr=search'
    }
    """

    snippet: str  # 搜索结果的摘要信息
    hostname: str  # 搜索结果的主机名
    hostlogo: str  # 搜索结果的主机图标 URL
    title: str  # 搜索结果的标题
    url: str  # 搜索结果的链接


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
    suspect_list: list[int]  # 疑似匹配的文档 id 列表 (confirm 为空时用于终止提示)

    embedding_recalls: list[MilvusChunksRecall]  # 向量化查询匹配结果
    hyde_recalls: list[MilvusChunksRecall]  # HyDE 搜索匹配结果
    web_matches: list[WebSearchResult]  # 互联网搜索匹配结果

    rerank_results: list[RerankResult]  # 重排序结果

    answer: str  # 最终回答


_DEFAULT_STATE: QueryGraphState = {
    "session_id": "",
    "original_query": "",
    "enable_web_search": True,
    "enable_hyde": True,
    "rewritten_query": "",
    "confirm_list": [],
    "suspect_list": [],
    "embedding_recalls": [],
    "hyde_recalls": [],
    "web_matches": [],
    "rerank_results": [],
    "answer": "",
}


def create_state(**state_dict) -> QueryGraphState:
    state = copy.deepcopy(_DEFAULT_STATE)
    state.update(state_dict)
    return state


def get_default_state() -> QueryGraphState:
    return copy.deepcopy(_DEFAULT_STATE)


def save_state(state: QueryGraphState, file_path: str) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=4)


def load_state(file_path: str) -> QueryGraphState:
    with open(file_path, "r", encoding="utf-8") as f:
        state = json.load(f)
    return state


if __name__ == "__main__":
    from rich import print as rprint
    from utils.path_utils import snapshot_path

    state = create_state(
        session_id="12345", original_query="What is the capital of France?"
    )
    rprint(state)
    save_state(state, snapshot_path("query_state_test.json"))
