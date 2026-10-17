from common.config.app_config import APP_CONFIG
from utils.node_utils import trace_node
from utils.logging_utils import logger
from processor.query_processor.state import StateChunkHits, QueryGraphState


def step_1_validate_and_get_data(
    state: QueryGraphState,
) -> tuple[list[StateChunkHits], list[StateChunkHits]]:

    embedding_matches = state.get("embedding_matches", [])
    hyde_matches = state.get("hyde_matches", [])

    return embedding_matches, hyde_matches


def step_2_rrf_fusion(
    embedding_matches: list[StateChunkHits],
    hyde_matches: list[StateChunkHits],
) -> list[StateChunkHits]:
    data_list: list[tuple[float, list[StateChunkHits]]] = [
        (0.5, embedding_matches),
        (0.5, hyde_matches),
    ]
    logger.info(f"向量查询切片数量: {len(embedding_matches)}")
    logger.info(f"Hyde查询切片数量: {len(hyde_matches)}")
    logger.info(f"融合切片数量: {len(embedding_matches) + len(hyde_matches)}")

    # 以 chunk_id 作为 key，保证 score_dict 与 chunk_dict 一一对应
    score_dict: dict[int, float] = {}  # {<chunk_id>: rrf_score}
    chunk_dict: dict[int, StateChunkHits] = {}  # {<chunk_id>: chunk_entity}
    k = APP_CONFIG.rrf_k

    for weight, chunks in data_list:
        for rank, chunk in enumerate(chunks, start=1):
            chunk_id = chunk.get("id")
            if chunk_id is None:
                # 缺少主键 id 的切片无法去重，跳过以免全部塌缩到同一个 key
                logger.warning(f"切片缺少 id，跳过融合: {chunk}")
                continue
            rrf_score = weight * (1.0 / (k + rank))
            score_dict[chunk_id] = score_dict.get(chunk_id, 0.0) + rrf_score
            chunk_dict[chunk_id] = chunk

    # 按 RRF 得分从高到低排序，score_dict 与 chunk_dict 通过 chunk_id 一一对应
    fused_results: list[StateChunkHits] = [
        {**chunk_dict[chunk_id], "score": score}
        for chunk_id, score in sorted(
            score_dict.items(), key=lambda item: item[1], reverse=True
        )
    ]

    return fused_results[: APP_CONFIG.chunks_recall_topk]


@trace_node(desc="融合排序", need_push=True)
def node_rrf(state: QueryGraphState) -> QueryGraphState:
    embedding_matches, hyde_matches = step_1_validate_and_get_data(state)

    fused_results = step_2_rrf_fusion(embedding_matches, hyde_matches)
    logger.info(f"最终融合切片数量: {len(fused_results)}")

    return {"rrf_matches": fused_results}


if __name__ == "__main__":
    from rich import print as rprint
    from processor.query_processor.state import load_state, save_state
    from utils.path_utils import PROJECT_ROOT

    prev_state0 = load_state(PROJECT_ROOT / "output/tmp/query_01_intent_recognize.json")
    prev_state1 = load_state(PROJECT_ROOT / "output/tmp/query_02_search_embedding.json")
    prev_state2 = load_state(PROJECT_ROOT / "output/tmp/query_03_search_hyde.json")
    fused_state = {**prev_state0, **prev_state1, **prev_state2}
    next_state = node_rrf(fused_state)
    rprint(next_state)

    new_state_json = str(PROJECT_ROOT / "output/tmp/query_05_rrf.json")

    save_state(next_state, new_state_json)
    logger.info(f"RRF融合排序处理完成")
    logger.info(f"状态保存路径: {new_state_json}")
