from common.client.milvus_client import MilvusChunksRecall
from common.config.app_config import APP_CONFIG
from common.config.env_config import ENV_CONFIG
from common.events.tracing import step_log, trace_node
from common.logging import logger
from common.model import LLM, RERANKER
from common.prompt.prompt_rerank_text_refine import PromptRerankRefineText
from common.utils.tokenizer import compute_token
from graphs.query_graph.nodes.node_search_web import WebSearchResult
from graphs.query_graph.query_graph_state import DataFrom, QueryGraphState, RerankResult


@step_log(desc="验证并获取数据")
def step_1_validate_and_get_data(
    state: QueryGraphState,
) -> tuple[
    str, list[MilvusChunksRecall], list[MilvusChunksRecall], list[WebSearchResult]
]:

    query = state.get("rewritten_query", "")
    embedding_recalls = state.get("embedding_recalls", [])
    hyde_recalls = state.get("hyde_recalls", [])
    web_matches = state.get("web_matches", [])

    return query, embedding_recalls, hyde_recalls, web_matches


@step_log(desc="RRF融合")
def step_2_rrf_fusion(
    embedding_recalls: list[MilvusChunksRecall],
    hyde_recalls: list[MilvusChunksRecall],
) -> list[MilvusChunksRecall]:
    def _filter_below_threshold(
        chunks: list[MilvusChunksRecall],
    ) -> list[MilvusChunksRecall]:
        """剔除混合检索原始分数低于阈值的切片。

        注意: 此处过滤的是 Milvus 混合检索 (WeightedRanker) 归一化后的原始
        分数, 而非 RRF 排名分。RRF 分是基于排名倒数的加权和, 量级极小,
        不能用 chunks_recall_threshold 这种 [0,1] 阈值去过滤。
        """
        threshold = APP_CONFIG.chunks_recall_threshold
        kept = [c for c in chunks if c.get("score", 0.0) >= threshold]
        dropped = len(chunks) - len(kept)
        if dropped:
            logger.info(f"召回阈值 {threshold} 过滤掉 {dropped} 条低分切片")
        return kept

    embedding_recalls = _filter_below_threshold(embedding_recalls)
    hyde_recalls = _filter_below_threshold(hyde_recalls)

    embedding_weight, hyde_weight = APP_CONFIG.rrf_weights
    data_list: list[tuple[float, list[MilvusChunksRecall]]] = [
        (embedding_weight, embedding_recalls),
        (hyde_weight, hyde_recalls),
    ]
    logger.info(f"向量查询切片数量: {len(embedding_recalls)}")
    logger.info(f"Hyde查询切片数量: {len(hyde_recalls)}")
    logger.info(f"融合切片数量: {len(embedding_recalls) + len(hyde_recalls)}")

    # 以 chunk_id 作为 key，保证 score_dict 与 chunk_dict 一一对应
    score_dict: dict[int, float] = {}  # {<chunk_id>: rrf_score}
    chunk_dict: dict[int, MilvusChunksRecall] = {}  # {<chunk_id>: chunk_entity}
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
    fused_results: list[MilvusChunksRecall] = [
        {**chunk_dict[chunk_id], "score": score}
        for chunk_id, score in sorted(
            score_dict.items(), key=lambda item: item[1], reverse=True
        )
    ]

    return fused_results[: APP_CONFIG.chunks_recall_topk]


def _ensure_answer_token_limit(question: str, answer: str) -> str:
    result = answer
    # 这里有些不严谨，近似计算
    answer_token_limit = ENV_CONFIG.dashscope.rerank_max_text_length - compute_token(
        question
    )
    if compute_token(answer) > answer_token_limit:
        # 截断文本以确保不超过 token 限制
        # 这里简单地按字符数截断，实际可根据具体 tokenizer 实现更精确的截断
        prompt = PromptRerankRefineText(
            question=question,
            answer=answer,
            limit=answer_token_limit,
        )
        llm_conclude = LLM.invoke(prompt.prompt)
        result = llm_conclude.content

    return result


@step_log(desc="重排序")
def step_3_rerank(
    rewritten_query: str,
    fused_results: list[MilvusChunksRecall],
    web_matches: list[WebSearchResult],
) -> list[RerankResult]:
    question = rewritten_query

    # 组装 question-answer 对: Milvus 切片在前, Web 搜索结果在后。
    # 该顺序与 rerank 返回结果中的 index 一一对应, 用于回填原文与来源。
    candidates: list[tuple[str, str]] = []  # [(answer, data_from), ...]

    for chunk in fused_results:
        answer = _ensure_answer_token_limit(question, chunk.get("chunk_content", ""))
        candidates.append((answer, DataFrom.MILVUS))

    for web_page in web_matches:
        answer = _ensure_answer_token_limit(question, web_page.get("snippet", ""))
        candidates.append((answer, DataFrom.WEB))

    documents = [answer for answer, _ in candidates]

    logger.info(f"待重排序文档数量: {len(documents)}")
    logger.info(f"待重排序文档内容: {documents}")

    results = RERANKER.rerank(
        query=question,
        documents=documents,
        return_documents=True,
    )

    # 将 rerank 结果映射回 RerankResult: 通过 index 找回原文与来源, 得分取相关性得分
    rerank_results: list[RerankResult] = []
    for result in results:
        answer, data_from = candidates[result["index"]]
        rerank_results.append(
            {
                "document": answer,
                "data_from": data_from,
                "score": result["relevance_score"],
            }
        )

    # 显式按相关性得分降序排序 (rerank 接口通常已有序, 此处兜底保证)
    rerank_results.sort(key=lambda r: r["score"], reverse=True)

    return rerank_results


@step_log(desc="动态TopK")
def step_4_dynamic_topk(rerank_results: list[RerankResult]) -> list[RerankResult]:
    """绝对分数下限 + 断崖检测实现动态 TopK。

    1. 先按绝对分数下限 (rerank_score_floor) 丢弃低相关候选:
       断崖检测只在相邻得分差上做文章, 当分数平滑下降时 (重排序模型常见)
       低分候选会全部幸存, 因此必须有独立的绝对下限兜底。
    2. 再对剩余结果做断崖检测: 从 min_topk 位置起向后扫描相邻两条的得分差。
       一旦发现“断崖”(绝对差值或相对降幅超过阈值), 即认为其后的召回片段
       相关度偏低, 予以剔除, 避免低质量片段污染最终答案。

    参数:
        rerank_results: 重排序结果列表 (已按 score 降序)

    返回:
         截断后的重排序结果列表
    """
    total = len(rerank_results)
    if total == 0:
        return rerank_results

    # 1. 绝对分数下限: 低于该分数的候选直接丢弃 (不依赖断崖检测)
    floor = APP_CONFIG.rerank_score_floor
    kept = [r for r in rerank_results if r.get("score", 0.0) >= floor]
    dropped = total - len(kept)
    if dropped:
        logger.info(f"重排分数下限 {floor} 过滤掉 {dropped} 条低相关候选")
    # 若全部低于下限, 保留最高分一条作为兜底, 维持"至少 1 条"的既有语义
    if not kept:
        logger.warning(f"全部候选低于分数下限 {floor}, 兜底保留最高分 1 条")
        kept = rerank_results[:1]
    rerank_results = kept

    # 2. 断崖检测
    total = len(rerank_results)

    # 硬上限: 最多保留前 N 条 (不超过候选总数)
    max_top_k = min(APP_CONFIG.rerank_max_topk, total)
    # 硬下限: 至少保留前 N 条 (至少 1 条, 且不超过硬上限)
    min_top_k = max(1, min(APP_CONFIG.rerank_min_topk, max_top_k))

    top_k = max_top_k

    # 只有硬上限 > 硬下限时才可能发生截断
    if max_top_k > min_top_k:
        for index in range(min_top_k - 1, max_top_k - 1):
            current = rerank_results[index]
            nxt = rerank_results[index + 1]

            current_score = current.get("score", 0.0)
            next_score = nxt.get("score", 0.0)

            # 相邻两条得分差: 绝对差 + 相对降幅 (当前得分为 0 时避免除零)
            abs_gap = current_score - next_score
            ratio_gap = abs_gap / current_score if current_score > 0 else 0.0

            if (abs_gap > APP_CONFIG.rerank_gap_abs) or (
                ratio_gap > APP_CONFIG.rerank_gap_ratio
            ):
                top_k = index + 1
                logger.debug(
                    f"下标 {index} 处发生断崖: 当前得分={current_score}, "
                    f"下一条得分={next_score}, 截断 TopK={top_k}"
                )
                break

    return rerank_results[:top_k]


@trace_node(desc="融合排序", need_push=True)
def node_rrf_and_rerank(state: QueryGraphState) -> QueryGraphState:
    rewritten_query, embedding_recalls, hyde_recalls, web_matches = (
        step_1_validate_and_get_data(state)
    )

    fused_results = step_2_rrf_fusion(embedding_recalls, hyde_recalls)
    logger.info(f"最终融合切片数量: {len(fused_results)}")

    rerank_results = step_3_rerank(rewritten_query, fused_results, web_matches)
    logger.info(f"重排序结果: {rerank_results}")
    logger.info(f"重排序结果数量: {len(rerank_results)}")

    rerank_results = step_4_dynamic_topk(rerank_results)
    logger.info(f"动态 TopK 后结果: {rerank_results}")
    logger.info(f"动态 TopK 后结果数量: {len(rerank_results)}")

    return {"rerank_results": rerank_results}


if __name__ == "__main__":
    from rich import print as rprint

    from common.config.path_config import snapshot_path
    from graphs.query_graph.query_graph_state import load_state, save_state

    prev_state1 = load_state(snapshot_path("query_01_intent_recognize.json"))
    prev_state2 = load_state(snapshot_path("query_02_search_embedding.json"))
    prev_state3 = load_state(snapshot_path("query_03_search_hyde.json"))
    prev_state4 = load_state(snapshot_path("query_04_search_web.json"))
    fused_state = {
        **prev_state1,
        **prev_state2,
        **prev_state3,
        **prev_state4,
    }
    next_state = node_rrf_and_rerank(fused_state)
    rprint(next_state)

    new_state_json = snapshot_path("query_05_rrf_and_rerank.json")

    save_state(next_state, new_state_json)
    logger.info("RRF融合排序处理完成")
    logger.info(f"状态保存路径: {new_state_json}")
