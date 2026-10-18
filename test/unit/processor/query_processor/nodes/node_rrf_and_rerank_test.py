"""单元测试: src/processor/query_processor/nodes/node_rrf_and_rerank.py

被测对象:
    step_4_dynamic_topk    断崖检测实现动态 TopK, 剔除相关度偏低的召回片段

说明:
    - step_4_dynamic_topk 是纯函数, 输入已按 score 降序排列的 RerankResult 列表,
      无需 mock 外部依赖。
    - 阈值读取 APP_CONFIG 的默认值: max_topk=10 / min_topk=1 / gap_abs=0.5 /
      gap_ratio=0.25。
"""

from __future__ import annotations

import pytest

from processor.query_processor.nodes.node_rrf_and_rerank import step_4_dynamic_topk
from processor.query_processor.state import RerankResult


def _docs(scores: list[float]) -> list[RerankResult]:
    """按得分构造已降序排列的重排序结果。"""
    return [
        {"document": f"doc-{i}", "data_from": "Milvus", "score": score}
        for i, score in enumerate(scores)
    ]


def _scores(docs: list[RerankResult]) -> list[float]:
    return [d["score"] for d in docs]


# --------------------------------------------------------------------------- #
# 相对降幅断崖: 相邻得分相对下降超过 25% 即截断
# --------------------------------------------------------------------------- #
def test_relative_gap_truncates_at_cliff():
    # 0.99 -> 0.70: 绝对差 0.29 (< 0.5), 但相对降幅 0.29/0.99 ≈ 0.293 > 0.25
    docs = _docs([0.99, 0.70, 0.65, 0.60])

    result = step_4_dynamic_topk(docs)

    assert _scores(result) == [0.99]


# --------------------------------------------------------------------------- #
# 绝对差断崖: 相邻得分绝对差超过 0.5 即截断
# --------------------------------------------------------------------------- #
def test_absolute_gap_truncates_at_cliff():
    # 0.90 -> 0.35: 绝对差 0.55 > 0.5, 立即截断
    docs = _docs([0.90, 0.35, 0.30, 0.25])

    result = step_4_dynamic_topk(docs)

    assert _scores(result) == [0.90]


# --------------------------------------------------------------------------- #
# 断崖出现在中间位置: 保留断崖之前的所有片段
# --------------------------------------------------------------------------- #
def test_cliff_at_middle_keeps_head():
    # 0.91 -> 0.50: 相对降幅 0.41/0.91 ≈ 0.45 > 0.25, 断崖出现在第 3 条之后
    docs = _docs([0.95, 0.93, 0.91, 0.50, 0.48])

    result = step_4_dynamic_topk(docs)

    assert _scores(result) == [0.95, 0.93, 0.91]


# --------------------------------------------------------------------------- #
# 无断崖: 得分平滑下降, 保留全部候选
# --------------------------------------------------------------------------- #
def test_no_cliff_keeps_all():
    docs = _docs([0.99, 0.90, 0.82, 0.75, 0.69])

    result = step_4_dynamic_topk(docs)

    assert _scores(result) == [0.99, 0.90, 0.82, 0.75, 0.69]


# --------------------------------------------------------------------------- #
# 硬上限: 候选超过 max_topk 时, 即使无断崖也只保留前 N 条
# --------------------------------------------------------------------------- #
def test_max_topk_caps_result():
    # 12 条候选, 得分平滑下降无断崖 -> 最多保留前 10 条
    scores = [1.0 - i * 0.005 for i in range(12)]
    docs = _docs(scores)

    result = step_4_dynamic_topk(docs)

    assert len(result) == 10
    assert _scores(result) == scores[:10]


# --------------------------------------------------------------------------- #
# 边界: 空列表与单元素
# --------------------------------------------------------------------------- #
def test_empty_list_returns_empty():
    assert step_4_dynamic_topk([]) == []


def test_single_element_returns_single():
    docs = _docs([0.8])

    result = step_4_dynamic_topk(docs)

    assert _scores(result) == [0.8]


# --------------------------------------------------------------------------- #
# 边界: 当前得分为 0 时不触发除零错误
# --------------------------------------------------------------------------- #
def test_zero_current_score_no_division_by_zero():
    docs = _docs([0.0, 0.0])

    result = step_4_dynamic_topk(docs)

    assert len(result) == 2
