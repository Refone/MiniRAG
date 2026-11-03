"""节点内进度（ProgressDetail）的单元测试。

覆盖: 写入 / 快照透出 / 文案裁剪 / 指标过滤 / 终态清理 / 上报推帧。
"""

import pytest

from common.events import EVENT_BUS, TASK_MANAGER, SSEEvent, TaskStatus
from common.events.tracing import report_progress, trace_node

pytestmark = pytest.mark.unit


def test_set_detail_appears_in_snapshot() -> None:
    TASK_MANAGER.clear("detail-basic")
    TASK_MANAGER.set_status("detail-basic", TaskStatus.PROCESSING)

    TASK_MANAGER.set_detail(
        "detail-basic",
        node="PDF 转 Markdown",
        text="24 页 · 解析中 12/24 页",
        metrics={"stage": "parsing", "done": 12, "total": 24},
    )

    snapshot = TASK_MANAGER.snapshot("detail-basic")
    assert snapshot is not None
    assert snapshot["detail"]["node"] == "PDF 转 Markdown"
    assert snapshot["detail"]["text"] == "24 页 · 解析中 12/24 页"
    assert snapshot["detail"]["metrics"]["done"] == 12
    TASK_MANAGER.clear("detail-basic")


def test_detail_text_and_metrics_are_sanitized() -> None:
    TASK_MANAGER.clear("detail-clean")
    TASK_MANAGER.set_status("detail-clean", TaskStatus.PROCESSING)

    TASK_MANAGER.set_detail(
        "detail-clean",
        node="测试节点",
        text="第一行\n第二行 " + "长" * 200,
        metrics={
            "long_text": "x" * 200,  # 字符串截断到 64
            "flag": True,  # 非标量, 丢弃
            **{f"k{i}": i for i in range(12)},
        },
    )

    detail = TASK_MANAGER.snapshot("detail-clean")["detail"]
    assert "\n" not in detail["text"]
    assert len(detail["text"]) <= 80
    assert len(detail["metrics"]) <= 8
    assert "flag" not in detail["metrics"]
    assert detail["metrics"]["long_text"] == "x" * 64
    TASK_MANAGER.clear("detail-clean")


def test_add_done_clears_only_matching_node_detail() -> None:
    TASK_MANAGER.clear("detail-done")
    TASK_MANAGER.set_status("detail-done", TaskStatus.PROCESSING)
    TASK_MANAGER.set_detail("detail-done", node="PDF 转 Markdown", text="解析中")

    TASK_MANAGER.add_done("detail-done", "识别文档类别")
    assert "detail" in TASK_MANAGER.snapshot("detail-done")

    TASK_MANAGER.add_done("detail-done", "PDF 转 Markdown")
    assert "detail" not in TASK_MANAGER.snapshot("detail-done")
    TASK_MANAGER.clear("detail-done")


def test_add_failed_clears_detail() -> None:
    TASK_MANAGER.clear("detail-failed")
    TASK_MANAGER.set_status("detail-failed", TaskStatus.PROCESSING)
    TASK_MANAGER.set_detail("detail-failed", node="文档嵌入入库", text="向量化 1/3 批")

    TASK_MANAGER.add_failed("detail-failed", "文档嵌入入库", "network error")

    snapshot = TASK_MANAGER.snapshot("detail-failed")
    assert "detail" not in snapshot
    assert snapshot["failed_list"] == ["文档嵌入入库"]
    assert snapshot["error"] == "network error"
    TASK_MANAGER.clear("detail-failed")


def test_child_snapshot_carries_detail() -> None:
    TASK_MANAGER.clear("detail-parent")
    TASK_MANAGER.fork(
        "detail-parent",
        [
            {
                "child_task_id": "detail-parent:md:0",
                "title": "a",
                "path": "a.md",
                "index": 0,
            }
        ],
    )
    TASK_MANAGER.set_detail(
        "detail-parent:md:0", node="Markdown 图片识别", text="生成摘要 5/12"
    )

    snapshot = TASK_MANAGER.snapshot("detail-parent:md:0")
    assert snapshot is not None
    assert snapshot["child_id"] == "detail-parent:md:0"
    assert snapshot["detail"]["text"] == "生成摘要 5/12"
    TASK_MANAGER.clear("detail-parent")


def test_report_progress_pushes_frame_inside_node() -> None:
    EVENT_BUS.create("detail-push")
    TASK_MANAGER.clear("detail-push")
    TASK_MANAGER.set_status("detail-push", TaskStatus.PROCESSING)

    @trace_node(desc="进度节点")
    def _node(state: dict) -> dict:
        report_progress("解析中 1/2 页", {"stage": "parsing", "done": 1, "total": 2})
        return state

    _node({"task_id": "detail-push"})

    frames = [
        data
        for event, data in EVENT_BUS.take("detail-push")
        if event == SSEEvent.PROGRESS
    ]
    assert len(frames) == 1
    assert frames[0]["detail"]["text"] == "解析中 1/2 页"
    assert frames[0]["detail"]["metrics"]["total"] == 2

    EVENT_BUS.remove("detail-push")
    TASK_MANAGER.clear("detail-push")


def test_report_progress_without_context_is_noop() -> None:
    report_progress("不应落盘")
    assert TASK_MANAGER.snapshot("detail-noop") is None
