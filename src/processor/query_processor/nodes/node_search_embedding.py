from common.client import MILVUS_CLIENT
from common.client.milvus_client import HybridSearchHits
from utils.node_utils import step_log, trace_node
from utils.logging_utils import logger
from processor.query_processor.state import StateChunkHits, QueryGraphState


@step_log(desc="校验并获取数据")
def step_1_validate_and_get_data(state: QueryGraphState):
    milvus_items: list[str] = state.get("confirm_list", [])
    rewritten_query: str = state.get("rewritten_query", "")
    return milvus_items, rewritten_query


@step_log(desc="向量化查询")
def step_2_vectorize_query(
    rewritten_query: str,
    milvus_items: list[str],
) -> list[HybridSearchHits]:
    """
    根据 rewritten_query 在 Milvus 中进行向量化查询，
    限制搜索范围为已 item_name in [已确定实体](milvus_items) 中的条目
    """

    # 仅有一个 query_text, 因此取第一个结果列表
    chunks: list[list[HybridSearchHits]] = MILVUS_CLIENT.hybrid_search_chunks(
        query_text=[rewritten_query],
        item_names=milvus_items,
    )

    return chunks[0]


def step_3_process_chunks(
    chunk_matches: list[HybridSearchHits],
) -> list[StateChunkHits]:
    embedding_matches: list[StateChunkHits] = []
    for hit in chunk_matches:
        chunk = hit.get("entity", {})
        # entity 中不含主键 id, 需从 hit 顶层单独取出, 供后续 RRF 融合按 id 去重
        chunk["id"] = hit.get("id")
        chunk["score"] = hit.get("distance", 0.0)
        embedding_matches.append(chunk)
    return embedding_matches


@trace_node(desc="向量化查询", need_push=True)
def node_search_embedding(state: QueryGraphState) -> QueryGraphState:

    milvus_items, rewritten_query = step_1_validate_and_get_data(state)
    logger.info(f"Milvus 确认主体: {milvus_items}, 查询概括: {rewritten_query}")
    if not milvus_items or not rewritten_query:
        # 没有在文库中找到匹配项, 那向量化查询意义也不大了
        # 全库搜索太耗时，且可能返回大量无关结果, 因此直接跳过
        logger.warning("没有在文库中找到匹配项, 跳过向量化查询")
        return {}

    chunk_matches: list[HybridSearchHits] = step_2_vectorize_query(
        rewritten_query,
        milvus_items,
    )

    embedding_matches: list[StateChunkHits] = step_3_process_chunks(chunk_matches)

    return {"embedding_matches": embedding_matches}


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
