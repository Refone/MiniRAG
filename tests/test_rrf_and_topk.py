"""RRF 融合与动态 TopK（查询链路里唯一的纯计算段）。

改这里等于改召回质量，因此断言写成"可解释的数值"，而不是快照。
"""

import pytest

from graphs.query_graph.nodes.node_rrf_and_rerank import (
    step_2_rrf_fusion,
    step_4_dynamic_topk,
)

# 与 app_config 默认值一致；改配置时这些用例会失败，属于预期的提醒
RRF_K = 60
RRF_WEIGHT = (0.7, 0.3)
RECALL_THRESHOLD = 0.55
SCORE_FLOOR = 0.5


def _chunk(chunk_id: int, score: float) -> dict:
    return {
        "id": chunk_id,
        "score": score,
        "doc_id": 1,
        "file_title": "t",
        "chunk_index": chunk_id,
        "chunk_content": f"c{chunk_id}",
    }


def _rerank(document: str, score: float) -> dict:
    return {"document": document, "data_from": "Milvus", "score": score}


def test_rrf_fusion_merges_same_id_and_orders_by_score():
    emb = [_chunk(1, 0.9), _chunk(2, 0.8)]
    hyde = [_chunk(2, 0.95), _chunk(3, 0.7)]

    fused = step_2_rrf_fusion(emb, hyde)

    assert [c["id"] for c in fused] == [2, 1, 3]
    emb_w, hyde_w = RRF_WEIGHT
    assert fused[0]["score"] == pytest.approx(
        (emb_w / (RRF_K + 2)) + (hyde_w / (RRF_K + 1))
    )
    assert fused[1]["score"] == pytest.approx(emb_w / (RRF_K + 1))
    assert fused[2]["score"] == pytest.approx(hyde_w / (RRF_K + 2))


def test_rrf_fusion_drops_candidates_below_recall_threshold():
    emb = [_chunk(1, 0.9), _chunk(9, RECALL_THRESHOLD - 0.01)]
    hyde = [_chunk(2, 0.8)]

    fused = step_2_rrf_fusion(emb, hyde)

    assert {c["id"] for c in fused} == {1, 2}


def test_rrf_fusion_skips_chunk_without_id():
    fused = step_2_rrf_fusion([{"score": 0.9}, _chunk(2, 0.8)], [])

    assert [c["id"] for c in fused] == [2]


def test_rrf_fusion_empty_input():
    assert step_2_rrf_fusion([], []) == []


def test_dynamic_topk_drops_scores_below_floor():
    results = [_rerank("a", 0.9), _rerank("b", 0.85), _rerank("c", SCORE_FLOOR - 0.1)]

    assert len(step_4_dynamic_topk(results)) == 2


def test_dynamic_topk_cuts_at_cliff():
    results = [_rerank("a", 0.9), _rerank("b", 0.6), _rerank("c", 0.58)]

    # 0.9 → 0.6 绝对差 0.3 > rerank_gap_abs(0.2)，断崖后全部丢弃
    assert [r["document"] for r in step_4_dynamic_topk(results)] == ["a"]


def test_dynamic_topk_keeps_gradual_curve():
    results = [_rerank(str(i), s) for i, s in enumerate([0.9, 0.85, 0.8, 0.7])]

    # 逐级下降、无断崖 → 全部保留
    assert len(step_4_dynamic_topk(results)) == 4


def test_dynamic_topk_falls_back_to_best_when_all_below_floor():
    results = [_rerank("a", 0.2), _rerank("b", 0.1)]

    assert [r["document"] for r in step_4_dynamic_topk(results)] == ["a"]


def test_dynamic_topk_empty():
    assert step_4_dynamic_topk([]) == []
