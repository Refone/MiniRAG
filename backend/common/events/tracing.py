"""节点/步骤装饰器: `trace_node` / `node_log` / `step_log`。

- `trace_node`: 节点级统一装饰器, 同时提供「日志 + 任务追踪」。
- `node_log`  : 节点日志装饰器, 节点函数签名 `func(state, ...)`。
- `step_log`  : 步骤日志装饰器, 普通函数签名 `func(*args, **kwargs)`。

`trace_node` 内部复用 `node_log` 完成日志包装。三者统一收口在本模块,
与底层日志基础设施 (`common.logging`) 解耦。
"""

import time
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable

from common.events import TASK_MANAGER
from common.events.event_bus import EVENT_BUS, SSEEvent
from common.logging import logger


def node_log(desc: str | None = None):

    def _task_id(state) -> str:
        return state.get("task_id", "-")

    def deco(func):
        # 绑定被装饰函数的真实身份, 不再依赖栈定位
        _log = logger.bind(
            _file=func.__code__.co_filename.split("/")[-1].split("\\")[-1],
            _function=func.__name__,
            _line=func.__code__.co_firstlineno + 1,
        )

        description = desc or func.__name__

        @wraps(func)
        def wrapper(state, *args, **kwargs):  # 明确装饰函数要有一个 state 参数
            task_id = _task_id(state)
            start_ts = time.time()
            _log.info(f"节点开始 [{description}] <task_id = {task_id}>")
            try:
                result = func(state, *args, **kwargs)
                cost_ms = int((time.time() - start_ts) * 1000)
                _log.info(
                    f"节点完成 [{description}] <task_id = {task_id}>, 耗时={cost_ms}ms"
                )
                return result
            except Exception:
                _log.opt(exception=True).error(
                    f"节点异常 [{description}] <task_id = {task_id}>"
                )
                raise

        return wrapper

    return deco


def step_log(desc: str | None = None):
    def deco(func):
        # 绑定被装饰函数的真实身份, 不再依赖栈定位
        _log = logger.bind(
            _file=func.__code__.co_filename.split("/")[-1].split("\\")[-1],
            _function=func.__name__,
            _line=func.__code__.co_firstlineno + 1,
        )

        description = desc or func.__name__

        @wraps(func)
        def wrapper(*args, **kwargs):
            start_ts = time.time()
            _log.info(f"步骤开始 [{description}]")
            try:
                result = func(*args, **kwargs)
                cost_ms = int((time.time() - start_ts) * 1000)
                _log.info(f"步骤完成 [{description}], 耗时={cost_ms}ms")
                return result
            except Exception:
                _log.opt(exception=True).error(f"步骤异常 [{description}]")
                raise

        return wrapper

    return deco


def _trace_id(state) -> str:
    """进度命名空间: ZIP 子任务优先 child_task_id, 其余沿用 task_id/session_id。"""
    return (
        state.get("child_task_id")
        or state.get("task_id")
        or state.get("session_id")
        or "-"
    )


def _publish_progress(trace_id: str) -> None:
    """进度推送的组合点：先从 `TASK_MANAGER` 取信息，再经 `EVENT_BUS` 推送。

    - 普通任务：`progress`，通道 = trace_id；
    - md 子任务：`child-progress`，通道 = 父 task_id；
    - 无条目 / 父任务已终态：不推（`snapshot()` 返回 None）。
    """
    snapshot = TASK_MANAGER.snapshot(trace_id)
    if snapshot is None:
        return
    parent_id = TASK_MANAGER.parent_id(trace_id)
    if parent_id is None:
        EVENT_BUS.push(trace_id, SSEEvent.PROGRESS, snapshot)
    else:
        EVENT_BUS.push(parent_id, SSEEvent.CHILD_PROGRESS, snapshot)


_current_node: ContextVar[tuple[str, str] | None] = ContextVar(
    "current_node", default=None
)


def report_progress(
    text: str,
    metrics: dict[str, str | int | float] | None = None,
) -> None:
    """节点内进度上报：写入任务状态并立刻推一帧快照。

    仅在 `trace_node` 执行上下文内有效；线程池 worker / 脚本直调时静默跳过
    （ContextVar 不跨线程传播，worker 应把结果带回主线程后再上报）。
    """
    context = _current_node.get()
    if context is None:
        return
    trace_id, node_name = context
    try:
        TASK_MANAGER.set_detail(trace_id, node=node_name, text=text, metrics=metrics)
        _publish_progress(trace_id)
    except Exception:
        logger.opt(exception=True).debug(
            "节点进度上报失败: trace_id={}, node={}", trace_id, node_name
        )


def _task_trace(node_name: str, *, need_push: bool = False) -> Callable[..., Any]:
    """任务追踪包装: 开始时记 running, 成功结束时记 done, 失败时记 failed。

    - 有 `child_task_id` 时记录到子任务命名空间, 与父任务 done/running 隔离;
    - 失败节点不再误记为 done, 失败/错误信息由 add_failed 记录;
    - 失败快照不在这里推送, 交给子任务包装节点 / import_service 统一收口。

    need_push=True 时, 在 add_running / add_done 之后经 `_publish_progress`
    推一帧快照: 状态查询（task_manager）与事件推送（event_bus）在本装饰器
    组合, task_manager 本身不负责推送。
    """

    def deco(func):
        @wraps(func)
        def wrapper(state, *args, **kwargs):
            trace_id = _trace_id(state)
            token = _current_node.set((trace_id, node_name))
            try:
                TASK_MANAGER.add_running(trace_id, node_name)
                if need_push:
                    _publish_progress(trace_id)
                try:
                    result = func(state, *args, **kwargs)
                except Exception as e:
                    TASK_MANAGER.add_failed(trace_id, node_name, str(e))
                    raise
                TASK_MANAGER.add_done(trace_id, node_name)
                if need_push:
                    _publish_progress(trace_id)
                return result
            finally:
                _current_node.reset(token)

        return wrapper

    return deco


def trace_node(
    desc: str | None = None,
    *,
    log_trace: bool = True,
    task_trace: bool = True,
    need_push: bool = False,
) -> Callable[..., Any]:
    """节点统一装饰器。

    参数:
        desc       节点功能描述 / 显示名, 用于日志、SSE 推送与前端展示;
                   默认取被修饰函数的函数名 `func.__name__`。
        log_trace  是否记录执行日志 (复用 `node_log`), 默认 True。
        task_trace 是否记录任务追踪; 为 True 时在节点开始时自动调用
                   `TASK_MANAGER.add_running`, 成功结束时调用 `TASK_MANAGER.add_done`, 失败时
                   调用 `TASK_MANAGER.add_failed` (不推送, 由上层收口), 默认 True。
        need_push  任务状态变化后是否立刻推送 SSE 快照 (在 `add_running` /
                   `add_done` 之后取快照并经 `EVENT_BUS` 推送), 默认 False。
                   仅在 `task_trace=True` 时有效; 需要实时进度的节点自行开启,
                   其余节点保持默认, 避免无谓推送。

    任务追踪以函数名 `func.__name__` 作为节点标识, 与 LangGraph 节点名一致。
    """

    def deco(func):
        description = desc or func.__name__

        # 内层 -> 外层: 日志 -> 任务追踪
        if log_trace:
            func = node_log(desc=description)(func)
        if task_trace:
            func = _task_trace(description, need_push=need_push)(func)

        return func

    return deco


if __name__ == "__main__":
    from typing import TypedDict

    class NodeState(TypedDict):
        task_id: int
        a: int

    # node_log: 节点日志
    @node_log("node_test")
    def node_test(state: NodeState):
        logger.info("processing...")
        state["a"] = state["a"] + 1
        return state

    start_state: NodeState = {"a": 0, "task_id": 12345}
    end_state = node_test(state=start_state)
    logger.info(end_state["a"])

    # step_log: 步骤日志
    @step_log("test step")
    def step_test(a: int, b: int):
        return a + b

    logger.info(step_test(2, 3))

    # trace_node: 日志 + 任务追踪
    from common.events import TASK_MANAGER

    @trace_node(desc="演示节点")
    def demo_node(state: dict):
        return state

    TASK_MANAGER.clear("demo")
    demo_node({"task_id": "demo"})
    done, running, _ = TASK_MANAGER.get_nodes("demo")
    logger.info(f"running={running} done={done}")
