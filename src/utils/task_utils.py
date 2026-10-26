from collections import defaultdict
from enum import StrEnum
import threading
from typing import Dict, List

from utils.logging_utils import logger
from utils.sse_utils import SSEEvent, sse_push

"""
任务管理器: 维护任务级 / 子任务级进度字典

    dict name            |   key          |   value
--------------------------------------------------------------
_tasks_running_nodes     | trace_id      | 节点列表  (["node_entry", ...])
_tasks_done_nodes        | trace_id      | 节点列表
_tasks_failed_nodes      | trace_id      | 节点列表
_tasks_error             | trace_id      | 最近一次失败信息
_tasks_status            | trace_id      | 状态字符串 ("pending" | "processing" ...)
_tasks_result            | task_id       | 任务结果   ({ "result": "ok" })
_child_parent            | child_task_id | 父 task_id (仅 md 压缩包分叉后的子任务)

`trace_id` 对普通任务等于 `task_id`/`session_id`; 对 md 压缩包分叉出来的
子任务等于 `child_task_id`。父子通过 `_child_parent` 关联: 子任务进度仍从
父任务的 SSE 队列推送, 但事件类型为 `child-progress` 且携带 `child_id`。

使用 defaultdict, 防止 id 第一次 `_tasks_running_nodes['<id>'].append('...')`
时列表未初始化导致 append 直接崩溃。

并发: LangGraph 的 Send 分支在多个线程里执行, 因此所有共享字典的读改写
统一由 `_lock` 保护; SSE 入队放在锁外, 避免持锁调用队列。

局限 (TODO, 见 U7):
    这些字典是**进程内**全局状态: 没有淘汰策略, 且多 uvicorn worker
    部署时每个进程各持一份, 任务状态查询与 SSE 推送会跨进程不一致。
    当前按「单 worker」使用; 若要多 worker 部署, 需改为 Redis 等外部存储,
    或把任务状态收敛到单一进程 (例如独立的任务服务)。
"""
_tasks_running_nodes: Dict[str, List[str]] = defaultdict(list)
_tasks_done_nodes: Dict[str, List[str]] = defaultdict(list)
_tasks_failed_nodes: Dict[str, List[str]] = defaultdict(list)
_tasks_error: Dict[str, str] = {}
_tasks_status: Dict[str, str] = {}
_tasks_result: Dict[str, Dict[str, str]] = defaultdict(dict)

# child_task_id -> parent task_id; 只有 ZIP 分叉出来的 md 子任务会登记
_child_parent: Dict[str, str] = {}

_lock = threading.RLock()


class TaskStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


# 合法任务状态集合, 供 set_task_status 做校验
_TASK_STATUS_VALUES = frozenset(status.value for status in TaskStatus)

# 终态集合: 父任务进入终态后, 迟到的子任务进度不再推送
# (P2 引入 cancelled 后在此追加)
_TERMINAL_STATUS_VALUES = frozenset(
    {TaskStatus.COMPLETE.value, TaskStatus.FAILED.value}
)


# API 一览 (一个 API 一行):
#   add_running_node       : 向「运行中」节点列表追加节点(去重), 可选推送 SSE
#   add_done_node          : 向「已完成」列表追加(去重)并从「运行中」出队, 可选推送 SSE
#   add_failed_node        : 记录失败节点(不推送, 由 wrapper/service 统一收口)
#   fork_task              : 注册 md 子任务并推送 fork 事件
#   complete_child         : 子任务成功收口(幂等)
#   fail_child             : 子任务失败收口(幂等)
#   set_task_result        : 写入任务的某个结果字段
#   get_task_result        : 读取任务的某个结果字段, 不存在时返回默认值
#   set_task_status        : 设置任务状态(必须是 TaskStatus 合法值)
#   get_task_status        : 读取任务状态, 未设置时返回空字符串
#   set_task_error         : 设置任务失败信息(供快照推送)
#   get_task_done_nodes    : 读取任务「已完成」节点列表
#   get_task_running_nodes : 读取任务「运行中」节点列表
#   get_task_failed_nodes  : 读取任务「失败」节点列表
#   task_push_sse          : 推送任务/子任务快照给 SSE 模块
#   clear_task             : 清空任务及其全部子任务数据(幂等)


def _parent_of(task_id: str) -> str | None:
    return _child_parent.get(task_id)


def _is_terminal(task_id: str) -> bool:
    return _tasks_status.get(task_id) in _TERMINAL_STATUS_VALUES


def _parent_is_terminal(task_id: str) -> bool:
    """child 的父任务是否已终态; 普通任务返回 False。"""
    parent = _child_parent.get(task_id)
    return bool(parent) and _is_terminal(parent)


def _snapshot(task_id: str) -> dict:
    """在锁内构造进度快照。"""
    payload = {
        "status": _tasks_status.get(task_id, ""),
        "done_list": list(_tasks_done_nodes.get(task_id, [])),
        "running_list": list(_tasks_running_nodes.get(task_id, [])),
    }
    failed = _tasks_failed_nodes.get(task_id)
    if failed:
        payload["failed_list"] = list(failed)
    error = _tasks_error.get(task_id)
    if error:
        payload["error"] = error
    return payload


def add_running_node(task_id: str, node_name: str, need_push: bool = False) -> None:
    """将节点加入该任务的「运行中」列表(去重), 可选触发 SSE 推送。

    Args:
        task_id: 任务/子任务 ID。
        node_name: 节点名称。
        need_push: 是否在本次调用后触发 SSE 推送, 默认 False。
    """
    with _lock:
        if _parent_is_terminal(task_id):
            return

        running = _tasks_running_nodes[task_id]
        if node_name not in running:
            running.append(node_name)

        # 子任务第一次出现 running 节点时自动从 pending 迁移到 processing
        if (
            task_id in _child_parent
            and _tasks_status.get(task_id) == TaskStatus.PENDING.value
        ):
            _tasks_status[task_id] = TaskStatus.PROCESSING.value

    if need_push:
        task_push_sse(task_id)


def add_done_node(task_id: str, node_name: str, need_push: bool = False) -> None:
    """将节点加入该任务的「已完成」列表(去重), 并从「运行中」列表出队。

    Args:
        task_id: 任务/子任务 ID。
        node_name: 节点名称。
        need_push: 是否在本次调用后触发 SSE 推送, 默认 False。
    """
    with _lock:
        if _parent_is_terminal(task_id):
            return

        done = _tasks_done_nodes[task_id]
        if node_name not in done:
            done.append(node_name)

        # 用 get 而不是下标: 避免给从未跑过的 task 凭空建出条目
        running = _tasks_running_nodes.get(task_id)
        if running and node_name in running:
            running.remove(node_name)

    if need_push:
        task_push_sse(task_id)


def add_failed_node(task_id: str, node_name: str, error: str = "") -> None:
    """记录失败节点并从「运行中」出队。

    不主动修改任务状态、不推送 SSE: 子任务由 `fail_child`, 父任务由
    `import_service` 统一收口, 避免一次失败推两帧(先 processing 后 failed)。
    """
    with _lock:
        if _parent_is_terminal(task_id):
            return

        failed = _tasks_failed_nodes[task_id]
        if node_name not in failed:
            failed.append(node_name)

        running = _tasks_running_nodes.get(task_id)
        if running and node_name in running:
            running.remove(node_name)

        if error:
            # 保留最深层节点异常, 不让外层包装异常覆盖
            _tasks_error.setdefault(task_id, error)


def fork_task(parent_task_id: str, children: list[dict]) -> None:
    """注册 md 子任务并下发 fork 事件。

    SSE 推送失败只记日志, 不阻断图执行。fork 一定发生在 `Send` 扇出之前,
    因此前端会先收到 fork, 再收到 child-progress。
    """
    with _lock:
        for child in children:
            child_id = child["child_task_id"]
            _child_parent[child_id] = parent_task_id
            _tasks_status.setdefault(child_id, TaskStatus.PENDING.value)
            _tasks_running_nodes.setdefault(child_id, [])
            _tasks_done_nodes.setdefault(child_id, [])
            _tasks_failed_nodes.setdefault(child_id, [])

        payload = {
            "parent_task_id": parent_task_id,
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
        sse_push(
            sse_id=parent_task_id,
            event=SSEEvent.FORK,
            data=payload,
        )
    except Exception:
        logger.warning(
            "fork 事件推送失败: parent_task_id={}", parent_task_id, exc_info=True
        )


def complete_child(child_id: str) -> None:
    """子任务成功收口: 置 complete、清空 running、推送一次 child-progress。"""
    with _lock:
        if child_id not in _child_parent:
            logger.warning("complete_child 收到未注册的子任务: {}", child_id)
            return
        if _is_terminal(child_id):
            return
        _tasks_status[child_id] = TaskStatus.COMPLETE.value
        _tasks_running_nodes.get(child_id, []).clear()

    task_push_sse(child_id)


def fail_child(child_id: str, error: str = "") -> None:
    """子任务失败收口: 置 failed、清空 running、推送一次 child-progress。"""
    with _lock:
        if child_id not in _child_parent:
            logger.warning("fail_child 收到未注册的子任务: {}", child_id)
            return
        if _is_terminal(child_id):
            return
        _tasks_status[child_id] = TaskStatus.FAILED.value
        _tasks_running_nodes.get(child_id, []).clear()
        if error:
            _tasks_error.setdefault(child_id, error)

    task_push_sse(child_id)


def set_task_result(task_id: str, key: str, value: str) -> None:
    """写入任务的某个结果字段, 同名 key 会被覆盖。"""
    with _lock:
        _tasks_result[task_id][key] = value


def get_task_result(task_id: str, key: str, default: str = "") -> str:
    """读取任务的某个结果字段, 不存在时返回 default(默认空字符串, 无副作用)。"""
    with _lock:
        return _tasks_result.get(task_id, {}).get(key, default)


def get_task_results(task_id: str) -> Dict[str, str]:
    """读取任务的全部结果字段的副本, 不存在时返回空字典(无副作用)。

    返回副本而不是内部 dict: 调用方 (API 拼装响应) 顺手修改时不会污染全局状态。
    """
    with _lock:
        return dict(_tasks_result.get(task_id, {}))


def get_task_status(task_id: str) -> str:
    """读取任务状态, 任务不存在或未设置时返回空字符串。"""
    with _lock:
        return _tasks_status.get(task_id, "")


def set_task_status(task_id: str, status: str) -> None:
    """设置任务状态, status 必须是 TaskStatus 中的合法值, 否则抛 ValueError。"""
    if status not in _TASK_STATUS_VALUES:
        raise ValueError(
            f"非法任务状态: {status!r}, 合法值: {sorted(_TASK_STATUS_VALUES)}"
        )
    with _lock:
        _tasks_status[task_id] = status


def set_task_error(task_id: str, error: str) -> None:
    """设置任务失败信息, 供后续 progress 快照携带; 空字符串忽略。"""
    if not error:
        return
    with _lock:
        _tasks_error.setdefault(task_id, error)


def get_task_done_nodes(task_id: str) -> List[str]:
    """读取任务「已完成」节点列表的副本, 不存在时返回空列表(无副作用)。

    返回副本而不是内部 list: 调用方 (API / SSE 拼装) 顺手 append 时不会污染全局状态。
    """
    with _lock:
        return list(_tasks_done_nodes.get(task_id, []))


def get_task_running_nodes(task_id: str) -> List[str]:
    """读取任务「运行中」节点列表的副本, 不存在时返回空列表(无副作用)。

    返回副本而不是内部 list, 理由同 get_task_done_nodes。
    """
    with _lock:
        return list(_tasks_running_nodes.get(task_id, []))


def get_task_failed_nodes(task_id: str) -> List[str]:
    """读取任务「失败」节点列表的副本, 不存在时返回空列表(无副作用)。"""
    with _lock:
        return list(_tasks_failed_nodes.get(task_id, []))


def task_push_sse(task_id: str) -> None:
    """推送任务快照。

    - 普通任务: `progress`, SSE key 为 task_id/session_id。
    - md 子任务: `child-progress`, SSE key 为父 task_id, 载荷带 child_id。
    - 父任务已终态时, 迟到的子任务推送直接丢弃。
    """
    with _lock:
        parent = _parent_of(task_id)
        if parent and _is_terminal(parent):
            return

        payload = _snapshot(task_id)
        if parent:
            payload["child_id"] = task_id
        sse_id = parent or task_id
        event = SSEEvent.CHILD_PROGRESS if parent else SSEEvent.PROGRESS

    sse_push(sse_id=sse_id, event=event, data=payload)


def clear_task(task_id: str) -> None:
    """清空指定任务及其全部子任务的数据(幂等), 不存在时不报错。"""
    with _lock:
        child_ids = [
            child_id
            for child_id, parent_id in _child_parent.items()
            if parent_id == task_id
        ]
        for child_id in child_ids:
            _child_parent.pop(child_id, None)
            _tasks_running_nodes.pop(child_id, None)
            _tasks_done_nodes.pop(child_id, None)
            _tasks_failed_nodes.pop(child_id, None)
            _tasks_status.pop(child_id, None)
            _tasks_error.pop(child_id, None)

        _tasks_running_nodes.pop(task_id, None)
        _tasks_done_nodes.pop(task_id, None)
        _tasks_failed_nodes.pop(task_id, None)
        _tasks_status.pop(task_id, None)
        _tasks_error.pop(task_id, None)
        _tasks_result.pop(task_id, None)
