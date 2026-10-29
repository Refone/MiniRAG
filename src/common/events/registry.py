"""进程内任务状态（任务 / md 子任务的进度聚合）。

替代原先的 7 张模块级 dict：

| 旧 | 新 |
| --- | --- |
| `_tasks_running_nodes` / `_tasks_done_nodes` / `_tasks_failed_nodes` | `TaskEntry.running / done / failed` |
| `_tasks_status` / `_tasks_error` / `_tasks_result` | `TaskEntry.status / error / result` |
| `_child_parent` | `TaskEntry.parent_id` |

约束与现状一致：

- `trace_id` 对普通任务等于 `task_id`/`session_id`；对 md 压缩包子任务等于
  `child_task_id`，其进度仍从**父任务**的通道推送，事件类型为 `child-progress`
  且载荷带 `child_id`。
- LangGraph 的 Send 分支在多线程执行 → 所有读改写由 `_lock` 保护；
  事件推送放在锁外，避免持锁调总线。
- 父任务进入终态后，迟到的子任务进度不再推送（`P2 引入 cancelled 后在此追加`）。

局限：进程内状态，多 uvicorn worker 各持一份；当前按「单 worker」使用
（README 已写明，`startup_checks` 会告警）。要横向扩展需换成 Redis 等外部存储，
接口保持不变即可替换。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypedDict

from common.events.bus import EVENT_BUS, SSEEvent
from common.logging import logger


class TaskStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


VALID_STATUS = frozenset(TaskStatus)
TERMINAL_STATUS = frozenset({TaskStatus.COMPLETE, TaskStatus.FAILED})


class ChildSpec(TypedDict):
    """`fork()` 的子任务描述（与 graphs 的 MdChild 解耦）。"""

    child_task_id: str
    title: str
    path: str
    index: int


@dataclass
class TaskEntry:
    task_id: str
    parent_id: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    running: list[str] = field(default_factory=list)
    done: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    error: str = ""
    result: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class TaskRegistry:
    """任务状态机的唯一入口（单例 `TASK_REGISTRY`）。"""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskEntry] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------- 内部工具
    def _ensure(self, task_id: str) -> TaskEntry:
        entry = self._tasks.get(task_id)
        if entry is None:
            entry = TaskEntry(task_id=task_id)
            self._tasks[task_id] = entry
        return entry

    @staticmethod
    def _touch(entry: TaskEntry) -> None:
        entry.updated_at = time.time()

    def _parent_is_terminal(self, task_id: str) -> bool:
        entry = self._tasks.get(task_id)
        if entry is None or entry.parent_id is None:
            return False
        parent = self._tasks.get(entry.parent_id)
        return parent is not None and parent.status in TERMINAL_STATUS

    @staticmethod
    def _snapshot(entry: TaskEntry) -> dict:
        payload = {
            "status": entry.status.value,
            "done_list": list(entry.done),
            "running_list": list(entry.running),
        }
        if entry.failed:
            payload["failed_list"] = list(entry.failed)
        if entry.error:
            payload["error"] = entry.error
        return payload

    # --------------------------------------------------------------- 节点进度
    def add_running(self, task_id: str, node: str, *, publish: bool = False) -> None:
        """节点开始：加入 running（去重），可选推送一次快照。"""
        with self._lock:
            if self._parent_is_terminal(task_id):
                return
            entry = self._ensure(task_id)
            if node not in entry.running:
                entry.running.append(node)
            # 子任务第一次出现 running 节点时自动 pending → processing
            if entry.parent_id is not None and entry.status is TaskStatus.PENDING:
                entry.status = TaskStatus.PROCESSING
            self._touch(entry)

        if publish:
            self.publish(task_id)

    def add_done(self, task_id: str, node: str, *, publish: bool = False) -> None:
        """节点成功：加入 done（去重）并从 running 出队。"""
        with self._lock:
            if self._parent_is_terminal(task_id):
                return
            entry = self._ensure(task_id)
            if node not in entry.done:
                entry.done.append(node)
            if node in entry.running:
                entry.running.remove(node)
            self._touch(entry)

        if publish:
            self.publish(task_id)

    def add_failed(self, task_id: str, node: str, error: str = "") -> None:
        """节点失败：记 failed 并出队。

        不主动改状态、不推送：子任务由 `fail_child`、父任务由 service 统一收口，
        避免一次失败推两帧（先 processing 后 failed）。
        """
        with self._lock:
            if self._parent_is_terminal(task_id):
                return
            entry = self._ensure(task_id)
            if node not in entry.failed:
                entry.failed.append(node)
            if node in entry.running:
                entry.running.remove(node)
            if error:
                # 保留最深层节点异常，不让外层包装异常覆盖
                entry.error = entry.error or error
            self._touch(entry)

    # ------------------------------------------------------------------ 子任务
    def fork(self, parent_id: str, children: list[ChildSpec]) -> None:
        """登记 md 子任务并下发 fork 事件（发生在 Send 扇出之前）。"""
        with self._lock:
            for child in children:
                entry = self._ensure(child["child_task_id"])
                entry.parent_id = parent_id
                self._touch(entry)

            payload = {
                "parent_task_id": parent_id,
                "total": len(children),
                "children": [
                    {
                        "child_id": c["child_task_id"],
                        "title": c["title"],
                        "path": c.get("path", ""),
                        "index": c["index"],
                    }
                    for c in children
                ],
            }

        try:
            EVENT_BUS.push(parent_id, SSEEvent.FORK, payload)
        except Exception:
            logger.warning("fork 事件推送失败: parent_id={}", parent_id, exc_info=True)

    def complete_child(self, child_id: str) -> None:
        """子任务成功收口：置 complete、清空 running、推送一次 child-progress。"""
        with self._lock:
            entry = self._tasks.get(child_id)
            if entry is None or entry.parent_id is None:
                logger.warning("complete_child 收到未注册的子任务: {}", child_id)
                return
            if entry.status in TERMINAL_STATUS:
                return
            entry.status = TaskStatus.COMPLETE
            entry.running.clear()
            self._touch(entry)

        self.publish(child_id)

    def fail_child(self, child_id: str, error: str = "") -> None:
        """子任务失败收口：置 failed、清空 running、推送一次 child-progress。"""
        with self._lock:
            entry = self._tasks.get(child_id)
            if entry is None or entry.parent_id is None:
                logger.warning("fail_child 收到未注册的子任务: {}", child_id)
                return
            if entry.status in TERMINAL_STATUS:
                return
            entry.status = TaskStatus.FAILED
            entry.running.clear()
            if error:
                entry.error = entry.error or error
            self._touch(entry)

        self.publish(child_id)

    # ------------------------------------------------------------------ 状态
    def set_status(self, task_id: str, status: TaskStatus | str) -> None:
        """设置任务状态；非法值抛 ValueError（沿用原校验）。"""
        value = status if isinstance(status, TaskStatus) else TaskStatus(str(status))
        with self._lock:
            entry = self._ensure(task_id)
            entry.status = value
            self._touch(entry)

    def get_status(self, task_id: str) -> str:
        """读取任务状态，未设置时返回空字符串。"""
        with self._lock:
            entry = self._tasks.get(task_id)
            return entry.status.value if entry else ""

    def set_error(self, task_id: str, error: str) -> None:
        """设置失败信息（空字符串忽略），供后续快照携带。"""
        if not error:
            return
        with self._lock:
            entry = self._ensure(task_id)
            entry.error = entry.error or error
            self._touch(entry)

    def set_result(self, task_id: str, key: str, value: str) -> None:
        """写入任务结果字段，同名覆盖。"""
        with self._lock:
            entry = self._ensure(task_id)
            entry.result[key] = value
            self._touch(entry)

    def get_nodes(self, task_id: str) -> tuple[list[str], list[str], list[str]]:
        """返回 (done, running, failed) 的副本。"""
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry is None:
                return [], [], []
            return list(entry.done), list(entry.running), list(entry.failed)

    # ------------------------------------------------------------------ 推送
    def publish(self, task_id: str) -> None:
        """推送任务快照。

        - 普通任务：`progress`，通道 = task_id / session_id；
        - md 子任务：`child-progress`，通道 = 父 task_id，载荷带 `child_id`；
        - 父任务已终态时，迟到的子任务推送直接丢弃。
        """
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry is None:
                return
            parent_id = entry.parent_id
            if parent_id is not None:
                parent = self._tasks.get(parent_id)
                if parent is not None and parent.status in TERMINAL_STATUS:
                    return
                payload = self._snapshot(entry)
                payload["child_id"] = task_id
                channel_id = parent_id
                event = SSEEvent.CHILD_PROGRESS
            else:
                payload = self._snapshot(entry)
                channel_id = task_id
                event = SSEEvent.PROGRESS

        EVENT_BUS.push(channel_id, event, payload)

    # ---------------------------------------------------------------- 生命周期
    def clear(self, task_id: str) -> None:
        """清空任务及其全部子任务（幂等）。"""
        with self._lock:
            child_ids = [
                tid for tid, entry in self._tasks.items() if entry.parent_id == task_id
            ]
            for cid in child_ids:
                self._tasks.pop(cid, None)
            self._tasks.pop(task_id, None)

    def sweep(self, ttl_seconds: float) -> int:
        """清掉 `ttl_seconds` 内无状态更新的任务，返回清理数量。"""
        cutoff = time.time() - ttl_seconds
        with self._lock:
            stale = [
                tid for tid, entry in self._tasks.items() if entry.updated_at < cutoff
            ]
            for tid in stale:
                self._tasks.pop(tid, None)
        return len(stale)


TASK_REGISTRY = TaskRegistry()
