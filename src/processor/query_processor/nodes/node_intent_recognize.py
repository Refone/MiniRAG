from collections import defaultdict

from common.client import MILVUS_CLIENT
from common.config.app_config import APP_CONFIG
from common.model import EMBEDDING, LLM
from common.prompt.prompt_conclude_query import ConcludeQueryResult, PromptConcludeQuery
from utils.logging_utils import brief_list, logger
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

    history_list = chat_history_manager.get_latest_messages(session_id=session_id)[::-1]

    history_summary_list: list[str] = []
    for index, item in enumerate(history_list):
        if item["role"] == MessageRole.USER:
            history_summary_list.append(f"编号 {index+1} | 用户提问 | {item['text']}")
        elif item["role"] == MessageRole.ASSISTANT:
            history_summary_list.append(f"编号 {index+1} | 助手回答 | {item['text']}")

    history_summary = "\n".join(history_summary_list)

    return history_summary


@step_log(desc="总结原始查询并提取关键词")
def step_3_conclude_query_and_key_words(
    history_summary: str,
    original_query: str,
) -> tuple[str, list[str]]:
    prompt = PromptConcludeQuery(history_summary, original_query)

    response = LLM.with_structured_output(ConcludeQueryResult).invoke(prompt.prompt)
    key_words = response.key_words
    conclude_query = response.conclude_query

    return conclude_query, key_words


@step_log(desc="从 Milvus item_name 表中选择匹配的主体")
def step_4_select_item_from_milvus(
    key_words: list[str],
) -> dict[str, list[tuple[str, float]]]:
    result_dict: dict[str, list[tuple[str, float]]] = defaultdict(list)
    """
    result_dict 的结构:
    {
        "关键词1": [("item_name1", distance), ("item_name2", distance), ...],
        "关键词2": [("item_name1", distance), ("item_name2", distance), ...],
        ...
    }
    ----
    item_namex 对应 Milvus (kb_item_name) 中要匹配的 item_name 字段。
    """
    if not key_words:
        return result_dict

    key_words_vector = EMBEDDING.embed_query_hybrid(
        key_words
    )  # 假设有一个 EMBEDDING_MODEL 用于将关键词转换为向量
    """
    key_words_vector:
    [
        {'dense':[...], 'sparse':[...]},
        {'dense':[...], 'sparse':[...]},
        ...
    ]
    """

    dense_vectors = [vec["dense"] for vec in key_words_vector]
    sparse_vectors = [vec["sparse"] for vec in key_words_vector]

    reqs_list = MILVUS_CLIENT.hybrid_search_item_name(
        dense_vectors=dense_vectors,
        sparse_vectors=sparse_vectors,
    )
    """
    reqs_list 的结构 (list[list[dict]] | None):
    外层 list 对应查询向量 (批量查询时长度为 len(key_words)),
    reqs_list[i] 是 key_words[i] 的 top-k 命中:
    [
        [  # key_words[0] 的命中
            {
                "id": 469734951640943804, -> entity 主键ID
                "distance": 0.8866561651229858, -> 最终融合得分, COSINE,IP 越大越相似, L2 越小越相似
                "entity": {
                    "item_name": ...
                }
            },
            ...
        ],
        [  # key_words[1] 的命中
            ...
        ],
    ]
    搜索失败时返回 None。
    """

    if not reqs_list:
        logger.warning("关键词的混合搜索无结果或失败")
        return result_dict

    for key_word, hits_list in zip(key_words, reqs_list):
        for hit in hits_list:
            try:
                item_name = hit["entity"]["item_name"]
                score = hit["distance"]
            except Exception as e:
                logger.error(
                    f"Failed to extract item_name and score from item: {hit}, error: {e}"
                )
                continue
            result_dict[key_word].append((item_name, score))

        # 匹配量小，sort 带来的性能影响可以忽略
        result_dict[key_word].sort(key=lambda x: x[1], reverse=True)

    return result_dict


@step_log(desc="根据关键词匹配结果生成确认主体和疑似主体列表")
def step_5_keywords_match_results(result_dict):

    confirm_set = set()
    suspect_set = set()

    """
    result_dict 的结构:
    {
        "关键词1": [("item_name1", distance), ("item_name2", distance), ...],
        "关键词2": [("item_name1", distance), ("item_name2", distance), ...],
        ...
    }
    """

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
def step_6_save_chat_message(
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

    query_conclude, key_words = step_3_conclude_query_and_key_words(
        history_summary,
        original_query,
    )
    logger.info(f"重写后的问题: {query_conclude}, 关键词: {', '.join(key_words)}")
    state["query_conclude"] = query_conclude if query_conclude else original_query
    state["key_words"] = key_words if key_words else []

    result_dict = step_4_select_item_from_milvus(key_words)
    logger.info(f"从 Milvus 中选取的结果: {result_dict}")

    confirm_list, suspect_list = step_5_keywords_match_results(result_dict)
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

    step_6_save_chat_message(
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
        original_query="请问一下, HAK180 和 RS-12 哪个性价比更高？",
    )
    next_state = node_intent_recognize(init_state)
    rprint(next_state)

    new_state_json = str(PROJECT_ROOT / "output/tmp/query_01_intent_recognize.json")

    save_state(next_state, new_state_json)
    logger.info(f"意图识别处理完成")
    logger.info(f"状态保存路径: {new_state_json}")
