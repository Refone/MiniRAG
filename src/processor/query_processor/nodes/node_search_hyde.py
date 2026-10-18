from common.client import MILVUS_CLIENT
from common.client.milvus_client import MilvusChunksRecall
from common.model import LLM
from common.prompt.prompt_hypo_answer import PromptHypoAnswer
from utils.brief_utils import brief
from utils.node_utils import trace_node, step_log
from utils.logging_utils import logger
from processor.query_processor.state import QueryGraphState


@step_log(desc="校验并获取数据")
def step_1_validate_and_get_data(state: QueryGraphState) -> tuple[list[str], str]:
    milvus_items: list[str] = state.get("confirm_list", [])
    rewritten_query: str = state.get("rewritten_query", "")
    if not rewritten_query:
        raise ValueError("重写后的查询未找到")

    return milvus_items, rewritten_query


@step_log(desc="生成假设性回答")
def step_2_generate_hypothetical_answer(
    rewritten_query: str,
) -> str:
    prompt = PromptHypoAnswer(rewritten_query).prompt
    hypo_answer = LLM.invoke(prompt)
    return hypo_answer.content


@step_log(desc="在 Milvus 中匹配假设性回答")
def step_3_hypo_match_in_milvus(
    milvus_items: list[str],
    hypo_answer: str,
) -> list[MilvusChunksRecall]:

    chunks = MILVUS_CLIENT.hybrid_search_chunks(
        query_text=[hypo_answer],
        item_names=milvus_items,
    )

    return chunks[0] if chunks else []


@trace_node(desc="海德搜索", need_push=True)
def node_search_hyde(state: QueryGraphState) -> QueryGraphState:
    """
    HyDE (Hypothetical Document Embeddings) search node.
    假设性搜索:
    先让大模型生成一个“理想的答案”或“可能的问题”，再用这个生成的内容去检索。
    """
    milvus_items, rewritten_query = step_1_validate_and_get_data(state)
    logger.info(f"Milvus 确认主体: {milvus_items}, 查询概括: {rewritten_query}")

    hypo_answer = step_2_generate_hypothetical_answer(rewritten_query)
    logger.info(f"生成的假设性回答: {hypo_answer}")

    hyde_recalls: list[MilvusChunksRecall] = step_3_hypo_match_in_milvus(
        milvus_items, hypo_answer
    )
    logger.info(f"匹配到的文档块: {brief(hyde_recalls)}")

    return {"hyde_recalls": hyde_recalls}


if __name__ == "__main__":
    from rich import print as rprint
    from processor.query_processor.state import load_state, save_state
    from utils.path_utils import PROJECT_ROOT

    prev_state = load_state(PROJECT_ROOT / "output/tmp/query_01_intent_recognize.json")
    next_state = node_search_hyde(prev_state)
    rprint(next_state)

    new_state_json = str(PROJECT_ROOT / "output/tmp/query_03_search_hyde.json")

    save_state(next_state, new_state_json)
    logger.info(f"海德搜索处理完成")
    logger.info(f"状态保存路径: {new_state_json}")
