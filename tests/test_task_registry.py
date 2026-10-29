"""进程内任务状态机（TaskRegistry）。

这些用例钉住的是**行为契约**，与实现无关：
- 节点在 running / done / failed 之间怎么迁移；
- 子任务的 pending → processing → complete/failed 收口；
- 父任务终态后，迟到的子任务进度必须被丢弃；
- clear / sweep 的幂等与回收。
"""

import pytest

from common.events import TASK_REGISTRY, TaskStatus

PARENT = "test-parent"
CHILD = "test-child"


def setup_function() -> None:
    TASK_REGISTRY.clear(PARENT)


def teardown_function() -> None:
    TASK_REGISTRY.clear(PARENT)


def _fork_one_child() -> None:
    TASK_REGISTRY.fork(
        PARENT,
        [
            {
                "child_task_id": CHILD,
                "title": "a",
                "path": "a.md",
                "index": 0,
            }
        ],
    )


def test_running_then_done_moves_node():
    TASK_REGISTRY.add_running(PARENT, "node_a")
    done, running, _ = TASK_REGISTRY.get_nodes(PARENT)
    assert running == ["node_a"]

    TASK_REGISTRY.add_done(PARENT, "node_a")
    done, running, _ = TASK_REGISTRY.get_nodes(PARENT)
    assert done == ["node_a"]
    assert running == []


def test_running_node_is_deduped():
    for _ in range(3):
        TASK_REGISTRY.add_running(PARENT, "node_a")

    _, running, _ = TASK_REGISTRY.get_nodes(PARENT)
    assert running == ["node_a"]


def test_failed_node_leaves_running_list():
    TASK_REGISTRY.add_running(PARENT, "node_x")
    TASK_REGISTRY.add_failed(PARENT, "node_x", "boom")

    _, running, failed = TASK_REGISTRY.get_nodes(PARENT)
    assert failed == ["node_x"]
    assert running == []


def test_status_validation():
    with pytest.raises(ValueError):
        TASK_REGISTRY.set_status(PARENT, "not-a-status")

    TASK_REGISTRY.set_status(PARENT, TaskStatus.PROCESSING)
    assert TASK_REGISTRY.get_status(PARENT) == "processing"

    # 字符串入参也接受（API / service 侧沿用枚举值）
    TASK_REGISTRY.set_status(PARENT, TaskStatus.COMPLETE.value)
    assert TASK_REGISTRY.get_status(PARENT) == "complete"


def test_unknown_task_returns_empty_defaults():
    assert TASK_REGISTRY.get_status("never-created") == ""
    assert TASK_REGISTRY.get_nodes("never-created") == ([], [], [])


def test_fork_then_child_lifecycle():
    _fork_one_child()
    assert TASK_REGISTRY.get_status(CHILD) == TaskStatus.PENDING.value

    # 子任务第一次出现 running 节点时自动 pending → processing
    TASK_REGISTRY.add_running(CHILD, "node_md_img")
    assert TASK_REGISTRY.get_status(CHILD) == TaskStatus.PROCESSING.value

    TASK_REGISTRY.complete_child(CHILD)
    assert TASK_REGISTRY.get_status(CHILD) == TaskStatus.COMPLETE.value
    _, running, _ = TASK_REGISTRY.get_nodes(CHILD)
    assert running == []


def test_fail_child_marks_terminal():
    _fork_one_child()

    TASK_REGISTRY.fail_child(CHILD, "图片解析失败")

    assert TASK_REGISTRY.get_status(CHILD) == TaskStatus.FAILED.value


def test_complete_child_is_idempotent():
    _fork_one_child()

    TASK_REGISTRY.complete_child(CHILD)
    TASK_REGISTRY.complete_child(CHILD)

    assert TASK_REGISTRY.get_status(CHILD) == TaskStatus.COMPLETE.value


def test_terminal_parent_ignores_late_child_progress():
    _fork_one_child()
    TASK_REGISTRY.set_status(PARENT, TaskStatus.FAILED)

    TASK_REGISTRY.add_done(CHILD, "node_md_img")

    # 父任务已终态：迟到的子任务进度不再记录（避免前端卡在"处理中"）
    done, _, _ = TASK_REGISTRY.get_nodes(CHILD)
    assert done == []


def test_clear_removes_children_and_is_idempotent():
    _fork_one_child()
    TASK_REGISTRY.add_running(CHILD, "node_md_img")

    TASK_REGISTRY.clear(PARENT)

    assert TASK_REGISTRY.get_status(PARENT) == ""
    assert TASK_REGISTRY.get_status(CHILD) == ""

    TASK_REGISTRY.clear(PARENT)  # 再清一次不应报错


def test_sweep_drops_idle_tasks():
    TASK_REGISTRY.set_status("sweep-me", TaskStatus.PROCESSING)

    assert TASK_REGISTRY.sweep(0) >= 1
    assert TASK_REGISTRY.get_status("sweep-me") == ""
