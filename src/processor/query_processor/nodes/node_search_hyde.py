from common.client import MILVUS_CLIENT
from common.model import EMBEDDING, LLM
from common.prompt.prompt_hypo_answer import PromptHypoAnswer
from utils.brief_utils import brief
from utils.node_utils import trace_node
from utils.logging_utils import logger
from processor.query_processor.state import QueryGraphState


def step_1_validate_and_get_data(state: QueryGraphState) -> tuple[str, str]:
    milvus_items = state.get("confirm_list")
    if not milvus_items:
        raise ValueError("主体名称未找到")

    rewritten_query = state.get("rewritten_query")
    if not rewritten_query:
        raise ValueError("重写后的查询未找到")

    return milvus_items, rewritten_query


def step_2_generate_hypothetical_answer(
    rewritten_query: str,
) -> str:
    prompt = PromptHypoAnswer(rewritten_query).prompt
    hypo_answer = LLM.invoke(prompt)
    return hypo_answer.content


def step_3_hypo_match_in_milvus(
    milvus_items: list[str],
    hypo_answer: str,
) -> list[str]:

    chunks = MILVUS_CLIENT.hybrid_search_chunks(
        query_text=[hypo_answer],
        item_names=milvus_items,
    )[0]

    return chunks


def step_4_process_hyde_chunks(chunk_matches: list[dict]):
    hyde_matches: list[dict] = []
    for hit in chunk_matches:
        chunk = hit.get("entity", {})
        chunk["score"] = hit.get("distance", 0.0)
        hyde_matches.append(chunk)
    return hyde_matches


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

    chunks = step_3_hypo_match_in_milvus(milvus_items, hypo_answer)
    logger.info(f"匹配到的文档块: {brief(chunks)}")

    hyde_matches = step_4_process_hyde_chunks(chunks)

    return {"hyde_matches": hyde_matches}


if __name__ == "__main__":
    from rich import print as rprint
    from processor.query_processor.state import load_state, save_state
    from utils.path_utils import PROJECT_ROOT

    prev_state = load_state(PROJECT_ROOT / "output/tmp/query_02_search_embedding.json")
    next_state = node_search_hyde(prev_state)
    rprint(next_state)

    new_state_json = str(PROJECT_ROOT / "output/tmp/query_03_search_hyde.json")

    save_state(next_state, new_state_json)
    logger.info(f"海德搜索处理完成")
    logger.info(f"状态保存路径: {new_state_json}")
