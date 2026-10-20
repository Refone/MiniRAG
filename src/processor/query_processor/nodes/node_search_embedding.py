from common.client import MILVUS_CLIENT
from common.client.milvus_client import MilvusChunksRecall
from utils.node_utils import step_log, trace_node
from utils.logging_utils import logger
from processor.query_processor.state import QueryGraphState


@step_log(desc="校验并获取数据")
def step_1_validate_and_get_data(state: QueryGraphState):
    doc_ids: list[int] = state.get("confirm_list", [])
    rewritten_query: str = state.get("rewritten_query", "")
    return doc_ids, rewritten_query


@step_log(desc="向量化查询")
def step_2_vectorize_query(
    rewritten_query: str,
    doc_ids: list[int],
) -> list[MilvusChunksRecall]:
    """
    根据 rewritten_query 在 minirag_chunks 中进行向量化查询，
    检索范围严格限定为确认文档 doc_ids 中的条目。
    """

    # 仅有一个 query_text, 因此取第一个结果列表
    chunks: list[list[MilvusChunksRecall]] | None = MILVUS_CLIENT.hybrid_search_chunks(
        query_text=[rewritten_query],
        doc_ids=doc_ids,
    )

    return chunks[0] if chunks else []


@trace_node(desc="向量化查询", need_push=True)
def node_search_embedding(state: QueryGraphState) -> QueryGraphState:

    doc_ids, rewritten_query = step_1_validate_and_get_data(state)
    logger.info(f"确认文档 doc_id: {doc_ids}, 查询概括: {rewritten_query}")
    if not doc_ids or not rewritten_query:
        # 没有确认匹配的文档, 向量化查询意义不大
        # (intent_recognize 在 confirm 为空时会终止流程, 此处为兜底)
        logger.warning("没有确认匹配的文档, 跳过向量化查询")
        return {}

    embedding_recalls: list[MilvusChunksRecall] = step_2_vectorize_query(
        rewritten_query,
        doc_ids,
    )

    return {"embedding_recalls": embedding_recalls}


if __name__ == "__main__":
    from rich import print as rprint
    from processor.query_processor.state import load_state, save_state
    from utils.path_utils import PROJECT_ROOT

    prev_state = load_state(PROJECT_ROOT / "output/tmp/query_01_intent_recognize.json")
    next_state = node_search_embedding(prev_state)
    rprint(next_state)

    new_state_json = str(PROJECT_ROOT / "output/tmp/query_02_search_embedding.json")

    save_state(next_state, new_state_json)
    logger.info(f"向量化查询处理完成")
    logger.info(f"状态保存路径: {new_state_json}")
