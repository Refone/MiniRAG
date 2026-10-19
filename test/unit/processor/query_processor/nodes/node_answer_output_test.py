"""单元测试: src/processor/query_processor/nodes/node_answer_output.py

被测对象:
    step_4_collect_images    从重排序结果收集展示图片 (含 icon 小图尺寸过滤)

说明:
    - RERANKER 用假实现替换, 不触网; 假实现对所有描述返回满分并记录入参。
    - icon 判定规则: 宽高均低于 APP_CONFIG.image_min_width / image_min_height
      (默认 80x80) 的图片丢弃; 尺寸未知 (无 title / width / height, 或解析失败)
      时兜底保留。
    - 尺寸信息由导入流程写入 Markdown (见 node_md_img_test.py)。
"""

from __future__ import annotations

import importlib

import pytest

from processor.query_processor.state import DataFrom, RerankResult

# 注意: 不能用 `from processor.query_processor.nodes import node_answer_output as mod` ——
# 包 __init__ 里 `from .node_answer_output import node_answer_output` 会用同名函数覆盖
# 子模块属性, 导致 monkeypatch 无法替换模块内的 RERANKER。
mod = importlib.import_module("processor.query_processor.nodes.node_answer_output")

QUERY = "产品的接口定义"


class FakeReranker:
    """假 rerank: 所有描述都返回满分, 并记录收到的文档列表。"""

    def __init__(self):
        self.calls: list[tuple[str, list[str]]] = []

    def rerank(self, query: str, documents: list[str]) -> list[dict]:
        self.calls.append((query, list(documents)))
        return [{"index": i, "relevance_score": 1.0} for i in range(len(documents))]


class FailingReranker(FakeReranker):
    """rerank 抛异常, 触发切片分数兜底路径。"""

    def rerank(self, query: str, documents: list[str]) -> list[dict]:
        self.calls.append((query, list(documents)))
        raise RuntimeError("rerank 服务不可用")


@pytest.fixture
def reranker(monkeypatch: pytest.MonkeyPatch) -> FakeReranker:
    fake = FakeReranker()
    monkeypatch.setattr(mod, "RERANKER", fake)
    return fake


def _docs(*documents: str, score: float = 0.9) -> list[RerankResult]:
    return [
        {"document": doc, "data_from": DataFrom.MILVUS, "score": score}
        for doc in documents
    ]


# --------------------------------------------------------------------------- #
# Markdown 语法: title 属性携带 "宽x高"
# --------------------------------------------------------------------------- #
def test_markdown_icon_filtered(reranker: FakeReranker):
    result = mod.step_4_collect_images(
        _docs('![小图标](http://x/a.png "64x64")'), QUERY
    )

    assert result == []
    # icon 在尺寸过滤阶段剔除, 不参与图片级 rerank
    assert reranker.calls == []


def test_markdown_normal_size_kept(reranker: FakeReranker):
    result = mod.step_4_collect_images(
        _docs('![接口图](http://x/b.png "800x600")'), QUERY
    )

    assert result == ["http://x/b.png"]


def test_markdown_unknown_size_kept_as_fallback(reranker: FakeReranker):
    # 无 title: 历史数据或切片截断, 兜底保留
    result = mod.step_4_collect_images(_docs("![老数据](http://x/c.png)"), QUERY)

    assert result == ["http://x/c.png"]


def test_markdown_single_quoted_title(reranker: FakeReranker):
    result = mod.step_4_collect_images(
        _docs("![小图标](http://x/d.png '64x64')"), QUERY
    )

    assert result == []


def test_markdown_banner_not_treated_as_icon(reranker: FakeReranker):
    # 横幅: 宽达标, 高不达标, 不满足"宽高均低于阈值"的 icon 判定
    result = mod.step_4_collect_images(
        _docs('![横幅](http://x/e.png "1000x30")'), QUERY
    )

    assert result == ["http://x/e.png"]


# --------------------------------------------------------------------------- #
# HTML 语法: width / height 属性
# --------------------------------------------------------------------------- #
def test_img_tag_icon_filtered(reranker: FakeReranker):
    result = mod.step_4_collect_images(
        _docs('<img src="http://x/f.png" width="64" height="64" alt="图标">'),
        QUERY,
    )

    assert result == []
    assert reranker.calls == []


def test_img_tag_normal_size_kept(reranker: FakeReranker):
    result = mod.step_4_collect_images(
        _docs('<img src="http://x/g.png" width="800" height="600" alt="大图">'),
        QUERY,
    )

    assert result == ["http://x/g.png"]


def test_img_tag_without_size_kept(reranker: FakeReranker):
    result = mod.step_4_collect_images(
        _docs('<img src="http://x/h.png" alt="无尺寸">'), QUERY
    )

    assert result == ["http://x/h.png"]


# --------------------------------------------------------------------------- #
# 混合场景与去重
# --------------------------------------------------------------------------- #
def test_mixed_drops_icon_keeps_normal(reranker: FakeReranker):
    result = mod.step_4_collect_images(
        _docs(
            '<img src="http://x/i.png" width="800" height="600" alt="正常图"> '
            '![图标](http://x/j.png "32x32")'
        ),
        QUERY,
    )

    assert result == ["http://x/i.png"]
    # 只剩正常图参与图片级 rerank
    assert reranker.calls == [(QUERY, ["正常图"])]


def test_dedup_merge_completes_size_then_filters(reranker: FakeReranker):
    # 同一 URL 出现在两个切片: 高分段无 title, 低分段携带 icon 尺寸
    # -> 去重时补全尺寸 -> 按 icon 过滤
    result = mod.step_4_collect_images(
        [
            {"document": "![图](http://x/k.png)", "data_from": DataFrom.MILVUS, "score": 0.9},
            {"document": '![图](http://x/k.png "48x48")', "data_from": DataFrom.MILVUS, "score": 0.8},
        ],
        QUERY,
    )

    assert result == []
    assert reranker.calls == []


# --------------------------------------------------------------------------- #
# 粗筛 / 兜底路径
# --------------------------------------------------------------------------- #
def test_web_results_ignored(reranker: FakeReranker):
    result = mod.step_4_collect_images(
        [{"document": "![图](http://x/l.png)", "data_from": DataFrom.WEB, "score": 0.99}],
        QUERY,
    )

    assert result == []


def test_low_chunk_score_filtered(reranker: FakeReranker):
    result = mod.step_4_collect_images(
        _docs('![大图](http://x/m.png "800x600")', score=0.3), QUERY
    )

    assert result == []


def test_rerank_failure_falls_back_to_chunk_score(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(mod, "RERANKER", FailingReranker())

    # 切片分数 0.9 >= image_min_rerank_score(0.7), 兜底保留
    result = mod.step_4_collect_images(
        _docs('![图](http://x/n.png "800x600")', score=0.9), QUERY
    )

    assert result == ["http://x/n.png"]


def test_empty_rerank_results_returns_empty(reranker: FakeReranker):
    assert mod.step_4_collect_images([], QUERY) == []


def test_all_icons_returns_empty(reranker: FakeReranker):
    result = mod.step_4_collect_images(
        _docs('![a](http://x/o.png "16x16") ![b](http://x/p.png "64x64")'), QUERY
    )

    assert result == []
