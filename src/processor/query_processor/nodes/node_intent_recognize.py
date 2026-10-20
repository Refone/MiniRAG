from common.client import MILVUS_CLIENT
from common.client.milvus_client import MilvusDocsRecall
from common.config.app_config import APP_CONFIG
from common.model import LLM
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


@step_log(desc="从 Milvus docs 表中召回匹配文档")
def step_4_select_docs_from_milvus(
    rewritten_query: str,
) -> list[MilvusDocsRecall]:
    """
    一级召回: 直接拿重写后的完整查询在 minirag_docs 中混合检索,
    同时匹配 keywords_sparse_vector(关键词精确) 与 abstract_dense_vector(摘要语义),
    不做任何线索/关键词提取。

    历史上下文已由查询重写步骤融入 rewritten_query, 无需额外的实体继承逻辑。

    返回:
    list[MilvusDocsRecall] 按融合得分降序的文档命中列表
        [{"id": 1, "score": 0.9, "file_title": "...", "docs_abstract": "..."}, ...]
    """

    reqs_list: list[list[MilvusDocsRecall]] | None = MILVUS_CLIENT.hybrid_search_docs(
        texts=[rewritten_query]
    )

    if not reqs_list:
        logger.warning("文档级混合搜索无结果或失败")
        return []

    return reqs_list[0]


@step_log(desc="根据文档匹配结果生成确认/疑似文档列表")
def step_5_docs_match_results(
    hits: list[MilvusDocsRecall],
) -> tuple[list[int], list[int], dict[int, str]]:
    """
    返回:
    tuple[list[int], list[int], dict[int, str]]:
    - confirm_list: 确认文档 id 列表 (二级召回的唯一定位源)
    - suspect_list: 疑似文档 id 列表 (仅 confirm 为空时用于终止提示)
    - doc_titles: doc_id -> file_title 展示映射

    阈值说明: 疑似文档不参与二级召回, 故确认阈值已适当放宽 (docs_confirm_threshold),
    放宽引入的噪声由二级混合检索 + RRF + rerank 兜底。
    """

    confirm_list: list[int] = []
    suspect_list: list[int] = []
    doc_titles: dict[int, str] = {}

    for hit in hits:
        doc_id = hit["id"]
        score = hit["score"]
        doc_titles.setdefault(doc_id, hit.get("file_title", ""))

        if score >= APP_CONFIG.docs_confirm_threshold:
            if doc_id not in confirm_list:
                confirm_list.append(doc_id)
        elif score >= APP_CONFIG.docs_suspect_threshold:
            if doc_id not in suspect_list:
                suspect_list.append(doc_id)

    # 确认与疑似互斥: 已确认的不再进入疑似
    suspect_list = [doc_id for doc_id in suspect_list if doc_id not in confirm_list]

    confirm_list = confirm_list[: APP_CONFIG.docs_confirm_topk]
    suspect_list = suspect_list[: APP_CONFIG.docs_suspect_topk]

    return confirm_list, suspect_list, doc_titles


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

    rewritten_query = step_3_rewrite_query(history_summary, original_query)
    state["rewritten_query"] = rewritten_query if rewritten_query else original_query
    logger.info(f"重写后的查询: {state['rewritten_query']}")

    hits = step_4_select_docs_from_milvus(state["rewritten_query"])
    logger.info(f"从 Milvus 中选取的结果: {hits}")

    confirm_list, suspect_list, doc_titles = step_5_docs_match_results(hits)
    logger.info(
        f"确认匹配文档: {[doc_titles.get(doc_id, '') for doc_id in confirm_list]}"
    )
    logger.info(
        f"疑似匹配文档: {[doc_titles.get(doc_id, '') for doc_id in suspect_list]}"
    )
    state["confirm_list"] = confirm_list
    state["suspect_list"] = suspect_list
    state["doc_titles"] = doc_titles

    # 无确认文档时终止查询流程: 疑似文档仅用于提示, 不参与二级召回
    if not confirm_list:
        if suspect_list:
            suspect_titles = (
                "《"
                + "》《".join(doc_titles.get(doc_id, "") for doc_id in suspect_list)
                + "》"
            )
            state["answer"] = (
                f"文库暂无内容与您的查询内容匹配，可能相关的文档有{suspect_titles}"
            )
        else:
            state["answer"] = "文库暂无内容与您的查询内容匹配"

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
        original_query="RS-12 多功能表如何测量电阻？",
    )
    next_state = node_intent_recognize(init_state)
    rprint(next_state)

    new_state_json = str(PROJECT_ROOT / "output/tmp/query_01_intent_recognize.json")

    save_state(next_state, new_state_json)
    logger.info(f"意图识别处理完成")
    logger.info(f"状态保存路径: {new_state_json}")
