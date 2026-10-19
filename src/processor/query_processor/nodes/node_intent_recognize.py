from collections import defaultdict
from re import M

from common.client import MILVUS_CLIENT
from common.client.milvus_client import MilvusItemNameRecall
from common.config.app_config import APP_CONFIG
from common.model import LLM
from common.prompt.prompt_item_names_of_query import (
    PromptItemNamesOfQuery,
    ItemNamesOfQueryPydantic,
)
from common.prompt.prompt_query_rewrite import PromptQueryRewrite
from utils.logging_utils import logger
from processor.query_processor.chat_history import chat_history_manager, MessageRole
from utils.node_utils import step_log, trace_node
from processor.query_processor.state import QueryGraphState


@step_log(desc="校验并获取数据")
def step_1_validate_and_get_data(state: QueryGraphState) -> tuple[str, str]:
    original_query = state.get("original_query")
    if not original_query:
        raise ValueError("原始查询未找到")

    session_id = state.get("session_id")
    if not session_id:
        raise ValueError("会话 ID 未找到")

    logger.info(f"原始问题: {original_query}, Session ID: {session_id}")

    return original_query, session_id


@step_log(desc="根据会话 ID 获取聊天记录")
def step_2_summary_history(session_id: str) -> str:
    return chat_history_manager.summary_history(session_id=session_id)


@step_log(desc="重写查询")
def step_3_rewrite_query(
    history_summary: str,
    original_query: str,
) -> str:
    prompt = PromptQueryRewrite(history_summary, original_query)

    response = LLM.invoke(prompt.prompt)

    return response.content


@step_log(desc="识别主体")
def step_4_recognize_item_names(
    rewritten_query: str,
    history_summary: str,
) -> list[str]:
    """
    输入参数:
    - rewritten_query: str 重写后的查询
    - history_summary: str 历史聊天记录摘要

    返回:
    list[str] 识别出的主体列表
    """

    prompt = PromptItemNamesOfQuery(
        query=rewritten_query,
        history_text=history_summary,
    )

    response = LLM.with_structured_output(ItemNamesOfQueryPydantic).invoke(
        prompt.prompt
    )

    return response.item_names


@step_log(desc="从 Milvus item_name 表中选择匹配的主体")
def step_5_select_item_from_milvus(
    item_names: list[str],
) -> dict[str, list[tuple[str, float]]]:
    """
    输入参数:
    - item_names: list[str] 识别出的询问主体列表
        ["主体1", "主体2", ...]

    返回:

    dict[str, list[tuple[str, float]]] 匹配结果字典，键为主体，值为匹配的 item_name 及其得分列表

        {
            "主体1": [("item_name1", distance), ("item_name2", distance), ...],
            "主体2": [("item_name1", distance), ("item_name2", distance), ...],
            ...
        }

    item_name* 对应 Milvus (minirag_item_name) 中要匹配的 item_name 字段。
    """

    result_dict: dict[str, list[tuple[str, float]]] = defaultdict(list)

    if not item_names:
        return result_dict

    reqs_list: list[list[MilvusItemNameRecall]] = MILVUS_CLIENT.hybrid_search_item_name(
        texts=item_names
    )

    if not reqs_list:
        logger.warning("主体名称的混合搜索无结果或失败")
        return result_dict

    for item_name, hits_list in zip(item_names, reqs_list):
        for hit in hits_list:
            hit_item_name = hit["item_name"]
            score = hit["score"]
            result_dict[item_name].append((hit_item_name, score))

        # 匹配量小，sort 带来的性能影响可以忽略
        result_dict[item_name].sort(key=lambda x: x[1], reverse=True)

    return result_dict


@step_log(desc="根据主体匹配结果生成确认主体和疑似主体列表")
def step_6_item_name_match_results(
    result_dict: dict[str, list[tuple[str, float]]],
) -> tuple[list[str], list[str]]:
    """
    输入参数:
    - result_dict: dict[str, list[tuple[str, float]]] 匹配结果字典，键为主体，值为匹配的 item_name 及其得分列表

        {
            "主体1": [("item_name1", distance), ("item_name2", distance), ...],
            "主体2": [("item_name1", distance), ("item_name2", distance), ...],
            ...
        }

    返回:
    tuple[list[str], list[str]] 确认主体列表和疑似主体列表
    """

    confirm_set = set()
    suspect_set = set()

    for matche_list in result_dict.values():

        for item_name, score in matche_list:
            if score >= APP_CONFIG.item_name_confirm_threshold:
                confirm_set.add(item_name)
            elif score >= APP_CONFIG.item_name_suspect_threshold:
                suspect_set.add(item_name)

    suspect_set -= confirm_set

    return (
        list(confirm_set)[: APP_CONFIG.item_name_confirm_topk],
        list(suspect_set)[: APP_CONFIG.item_name_suspect_topk],
    )


@step_log(desc="将聊天消息落库 mongodb")
def step_7_save_chat_message(
    original_query: str,
    session_id: str,
) -> None:
    chat_history_manager.save_message(
        text=original_query,
        session_id=session_id,
        role=MessageRole.USER,
    )


@trace_node(desc="意图识别", need_push=True)
def node_intent_recognize(state: QueryGraphState) -> QueryGraphState:

    original_query, session_id = step_1_validate_and_get_data(state)

    history_summary = step_2_summary_history(session_id=session_id)
    logger.info(f"历史记录摘要:\n{history_summary}")

    rewritten_query = step_3_rewrite_query(history_summary, original_query)
    state["rewritten_query"] = rewritten_query if rewritten_query else original_query
    logger.info(f"重写后的查询: {state['rewritten_query']}")

    item_names = step_4_recognize_item_names(rewritten_query, history_summary)
    state["item_names"] = item_names if item_names else []
    logger.info(f"识别的主体: {item_names}")

    result_dict = step_5_select_item_from_milvus(item_names)
    logger.info(f"从 Milvus 中选取的结果: {result_dict}")

    confirm_list, suspect_list = step_6_item_name_match_results(result_dict)
    logger.info(f"确认匹配: {confirm_list}")
    logger.info(f"疑似匹配: {suspect_list}")
    state["confirm_list"] = confirm_list if confirm_list else []
    state["suspect_list"] = suspect_list if suspect_list else []
    if not confirm_list:
        if suspect_list:
            state["answer"] = (
                f"未能在文库中找到相关匹配, 您想询问的是否是: {', '.join(suspect_list)}?"
            )
        else:
            state["answer"] = "未能在文库中找到相关匹配"

    step_7_save_chat_message(
        original_query=original_query,
        session_id=session_id,
    )

    return state


if __name__ == "__main__":
    from rich import print as rprint
    from processor.query_processor.state import create_state, save_state
    from utils.path_utils import PROJECT_ROOT

    init_state = create_state(
        session_id="test-flow-session-id",
        original_query="RS-12 多功能表如何测量电阻？",
    )
    next_state = node_intent_recognize(init_state)
    rprint(next_state)

    new_state_json = str(PROJECT_ROOT / "output/tmp/query_01_intent_recognize.json")

    save_state(next_state, new_state_json)
    logger.info(f"意图识别处理完成")
    logger.info(f"状态保存路径: {new_state_json}")
