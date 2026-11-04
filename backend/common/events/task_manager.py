"""进程内任务状态（任务 / md 子任务的进度聚合）。

只保存与查询状态，**不 import / 不调用事件总线**：快照与 fork 载荷由本模块返回，
事件经 `EVENT_BUS` 推送是调用侧（tracing / service / graphs）的职责。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import NotRequired, TypedDict

from common.logging import logger

# 节点内进度的展示约束：单行、短文本，避免把业务大文本塞进 SSE
_DETAIL_TEXT_MAX_CHARS = 80
_DETAIL_METRICS_MAX_KEYS = 8
_DETAIL_METRIC_STR_MAX_CHARS = 64


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


class ProgressDetail(TypedDict):
    """节点内进度：快照的可选字段，由节点经 `report_progress` 写入。

    示例:
    {
        "node": "PDF 转 Markdown",
        "text": "24 页 · 解析中 12/24 页",
        "metrics": {"stage": "parsing", "done": 12, "total": 24},
    }
    """

    node: str
    text: str
    metrics: NotRequired[dict[str, str | int | float]]


def _normalize_detail(
    node: str,
    text: str,
    metrics: dict[str, str | int | float] | None,
) -> ProgressDetail:
    """裁剪文案、过滤指标：只保留单行短文本与标量键值。"""
    detail: ProgressDetail = {
        "node": node,
        "text": " ".join(str(text).split())[:_DETAIL_TEXT_MAX_CHARS],
    }
    if not metrics:
        return detail

    clean: dict[str, str | int | float] = {}
    for key, value in metrics.items():
        if len(clean) >= _DETAIL_METRICS_MAX_KEYS:
            break
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            clean[str(key)] = value
        elif isinstance(value, str):
            clean[str(key)] = value[:_DETAIL_METRIC_STR_MAX_CHARS]
    if clean:
        detail["metrics"] = clean
    return detail


@dataclass
class TaskEntry:
    """单个任务 / md 子任务的状态记录。

    示例:
    # 父任务：入口与解压已完成，等待各 md 分支收口
    TaskEntry(
        task_id="6f1c2b9e4a7d4c1e8f3a0b5d9c2e7f41",
        parent_id=None,
        status=TaskStatus.PROCESSING,
        running=[],
        done=["识别文档类别", "处理 Markdown 压缩包"],
        failed=[],
        error="",
        result={},
        created_at=1761820000.123456,
        updated_at=1761820042.789012,
    )

    # md 子任务：图片识别、切分成功，嵌入入库失败
    TaskEntry(
        task_id="6f1c2b9e4a7d4c1e8f3a0b5d9c2e7f41:md:0",
        parent_id="6f1c2b9e4a7d4c1e8f3a0b5d9c2e7f41",
        status=TaskStatus.FAILED,
        running=[],
        done=["Markdown 图片识别", "文档切分"],
        failed=["文档嵌入入库"],
        error="Milvus insert failed: connection reset",
        result={},
        created_at=1761820010.001234,
        updated_at=1761820035.678901,
    )

    """

    task_id: str
    parent_id: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    running: list[str] = field(default_factory=list)
    done: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    error: str = ""
    result: dict[str, str] = field(default_factory=dict)
    detail: ProgressDetail | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class TaskManager:
    """任务状态的唯一入口（单例 `TASK_MANAGER`）。

    只负责状态读写；需要推送进度时由调用侧取 `snapshot()` / `fork()` 的
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskEntry] = {}
        self._lock = threading.RLock()

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
        if entry.detail:
            # 拷贝一层，避免调用方改到进程内状态
            detail = dict(entry.detail)
            if "metrics" in detail:
                detail["metrics"] = dict(detail["metrics"])
            payload["detail"] = detail
        return payload

    def set_detail(
        self,
        task_id: str,
        node: str,
        text: str,
        metrics: dict[str, str | int | float] | None = None,
    ) -> None:
        """写入当前节点进度（裁剪后覆盖）。不推送，推送由调用侧决定。"""
        with self._lock:
            if self._parent_is_terminal(task_id):
                return
            entry = self._ensure(task_id)
            entry.detail = _normalize_detail(node, text, metrics)
            self._touch(entry)

    def add_running(self, task_id: str, node: str) -> None:
        """节点开始：加入 running（去重）。不推送，推送由调用侧决定。"""
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

    def add_done(self, task_id: str, node: str) -> None:
        """节点成功：加入 done（去重）并从 running 出队。不推送。"""
        with self._lock:
            if self._parent_is_terminal(task_id):
                return
            entry = self._ensure(task_id)
            if node not in entry.done:
                entry.done.append(node)
            if node in entry.running:
                entry.running.remove(node)
            if entry.detail is not None and entry.detail["node"] == node:
                entry.detail = None
            self._touch(entry)

    def add_failed(self, task_id: str, node: str, error: str = "") -> None:
        """节点失败：记 failed 并出队。

        不主动改状态：子任务由 `fail_child`、父任务由 service 统一收口，
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
            if entry.detail is not None and entry.detail["node"] == node:
                entry.detail = None
            if error:
                # 保留最深层节点异常，不让外层包装异常覆盖
                entry.error = entry.error or error
            self._touch(entry)

    def fork(self, parent_id: str, children: list[ChildSpec]) -> dict | None:
        """登记 md 子任务并返回 fork 事件载荷（发生在 Send 扇出之前）。

        只改状态、不推送：事件下发由调用侧经 `EVENT_BUS.push` 完成，
        载荷即本方法返回值；空清单返回 `None`（调用侧无需下发）。
        """
        if not children:
            return None

        with self._lock:
            for child in children:
                entry = self._ensure(child["child_task_id"])
                entry.parent_id = parent_id
                self._touch(entry)

        return {
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

    def complete_child(self, child_id: str) -> dict | None:
        """子任务成功收口：置 complete、清空 running，返回进度快照载荷。

        未注册 / 无父 / 已终态 / 父任务已终态时返回 `None`（调用侧据此不推送）。
        """
        with self._lock:
            entry = self._tasks.get(child_id)
            if entry is None or entry.parent_id is None:
                logger.warning("complete_child 收到未注册的子任务: {}", child_id)
                return None
            if entry.status in TERMINAL_STATUS:
                return None
            entry.status = TaskStatus.COMPLETE
            entry.running.clear()
            self._touch(entry)

        return self.snapshot(child_id)

    def fail_child(self, child_id: str, error: str = "") -> dict | None:
        """子任务失败收口：置 failed、清空 running，返回进度快照载荷。

        未注册 / 无父 / 已终态 / 父任务已终态时返回 `None`（调用侧据此不推送）。
        """
        with self._lock:
            entry = self._tasks.get(child_id)
            if entry is None or entry.parent_id is None:
                logger.warning("fail_child 收到未注册的子任务: {}", child_id)
                return None
            if entry.status in TERMINAL_STATUS:
                return None
            entry.status = TaskStatus.FAILED
            entry.running.clear()
            if error:
                entry.error = entry.error or error
            self._touch(entry)

        return self.snapshot(child_id)

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

    def parent_id(self, task_id: str) -> str | None:
        """父任务 id：普通任务 / 未登记任务返回 `None`。"""
        with self._lock:
            entry = self._tasks.get(task_id)
            return entry.parent_id if entry else None

    def snapshot(self, task_id: str) -> dict | None:
        """进度快照载荷：普通任务为 `{status, done_list, running_list, ...}`，
        子任务额外带 `child_id`。

        无条目或父任务已终态时返回 `None`，调用侧据此跳过推送。
        """
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry is None:
                return None
            parent_id = entry.parent_id
            if parent_id is not None:
                parent = self._tasks.get(parent_id)
                if parent is not None and parent.status in TERMINAL_STATUS:
                    return None
                payload = self._snapshot(entry)
                payload["child_id"] = task_id
            else:
                payload = self._snapshot(entry)
            return payload

    def clear(self, task_id: str) -> None:
        """清空任务及其全部子任务（幂等）。"""
        with self._lock:
            child_ids = [
                tid for tid, entry in self._tasks.items() if entry.parent_id == task_id
            ]
            for cid in child_ids:
                self._tasks.pop(cid, None)
            self._tasks.pop(task_id, None)

    def clear_all(self) -> None:
        """清空全部任务（测试隔离用；生产由 TTL 清扫）。"""
        with self._lock:
            self._tasks.clear()

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


TASK_MANAGER = TaskManager()
