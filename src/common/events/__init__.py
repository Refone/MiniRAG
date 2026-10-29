"""进程内任务状态与事件分发（tier 3）。

- `registry`：任务 / 子任务状态机（`TASK_REGISTRY`）
- `bus`：SSE 事件通道（`EVENT_BUS`，不依赖 fastapi）
- `tracing`：节点装饰器 `trace_node` / `node_log` / `step_log`

三者互相依赖（tracing → registry → bus），故同处一个子包：子包内部自由引用，
对外只从这里取单例与枚举。
"""

from .bus import EVENT_BUS, SSEEvent
from .registry import TASK_REGISTRY, TaskStatus

__all__ = ["EVENT_BUS", "SSEEvent", "TASK_REGISTRY", "TaskStatus"]
