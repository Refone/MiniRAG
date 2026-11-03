import pytest

from common.events import TASK_MANAGER, TaskStatus

pytestmark = pytest.mark.unit


def test_task__fork_and_child_lifecycle__terminal_and_cleanup():
    """Given 父任务与子任务 When 子任务收口/父任务终态 Then 快照与清理符合契约。"""
    parent_id, child_id = "parent", "parent:md:0"
    TASK_MANAGER.set_status(parent_id, TaskStatus.PROCESSING)

    payload = TASK_MANAGER.fork(
        parent_id,
        [
            {
                "child_task_id": child_id,
                "title": "a",
                "path": "a.md",
                "index": 0,
            }
        ],
    )
    assert payload == {
        "parent_task_id": parent_id,
        "total": 1,
        "children": [{"child_id": child_id, "title": "a", "path": "a.md", "index": 0}],
    }
    assert TASK_MANAGER.fork(parent_id, []) is None

    TASK_MANAGER.add_running(child_id, "图片识别")
    snapshot = TASK_MANAGER.snapshot(child_id)
    assert snapshot is not None
    assert snapshot["status"] == TaskStatus.PROCESSING.value
    assert snapshot["child_id"] == child_id
    assert snapshot["running_list"] == ["图片识别"]

    completed = TASK_MANAGER.complete_child(child_id)
    assert completed is not None
    assert completed["status"] == TaskStatus.COMPLETE.value
    assert completed["running_list"] == []

    TASK_MANAGER.set_status(parent_id, TaskStatus.COMPLETE)
    assert TASK_MANAGER.snapshot(child_id) is None, "父任务终态后子任务不再推送"

    TASK_MANAGER.clear(parent_id)
    assert TASK_MANAGER.snapshot(parent_id) is None
    assert TASK_MANAGER.snapshot(child_id) is None


def test_task__invalid_status__raises_and_clear_all_resets():
    """Given 非法状态 When set_status Then ValueError；clear_all 清空全部。"""
    TASK_MANAGER.set_status("t", TaskStatus.PROCESSING)
    with pytest.raises(ValueError):
        TASK_MANAGER.set_status("t", "not-a-status")

    TASK_MANAGER.clear_all()
    assert TASK_MANAGER.snapshot("t") is None
