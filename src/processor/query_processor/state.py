from typing import TypedDict
import copy
import json

from utils.path_utils import PROJECT_ROOT


class QueryGraphState(TypedDict):
    session_id: str  # 会话 ID
    original_query: str  # 原始查询
    web_search: bool  # 是否进行网络搜索

    query_conclude: str  # 重写后的问题
    key_words: list[str]  # 关键词

    # Milvus item_name 匹配结果
    confirm_list: list[str]  # 确认匹配的列表
    suspect_list: list[str]  # 疑似匹配的列表

    answer: str  # 最终回答


_DEFAULT_STATE: QueryGraphState = {
    "session_id": "",
    "original_query": "",
    "web_search": True,
    "query_conclude": "",
    "key_words": [],
    "confirm_list": [],
    "suspect_list": [],
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

    state = create_state(
        session_id="12345", original_query="What is the capital of France?"
    )
    rprint(state)
    save_state(state, str(PROJECT_ROOT / "output/tmp/query_state_test.json"))
