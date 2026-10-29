"""进程内任务状态与事件分发（tier 3）。

- `task_manager`：任务 / 子任务状态机（`TASK_MANAGER`）——只保存/查询状态，不推送事件；
- `event_bus`：SSE 事件通道（`EVENT_BUS`，不依赖 fastapi）——只负责传输；
- `tracing`：节点装饰器 `trace_node` / `node_log` / `step_log`。

task_manager 与 event_bus 互不依赖（状态与推送解耦），事件推送由调用侧组合：
先从 `TASK_MANAGER` 取快照 / 载荷，再经 `EVENT_BUS.push` 下发。
三者同处一个子包（tracing 依赖前两者），对外只从这里取单例与枚举。
"""

from .event_bus import EVENT_BUS, SSEEvent
from .task_manager import TASK_MANAGER, TaskStatus

__all__ = ["EVENT_BUS", "SSEEvent", "TASK_MANAGER", "TaskStatus"]
