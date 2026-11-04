from pathlib import Path

from common.config.path_config import IMPORT_TMP_DIR
from common.events import EVENT_BUS, TASK_MANAGER, SSEEvent
from common.events.tracing import trace_node
from common.logging import logger
from graphs.import_graph.import_graph_state import ImportGraphState, MdChild


@trace_node(desc="拆分 md 子任务", task_trace=False)
def node_md_fork(state: ImportGraphState) -> ImportGraphState:
    """解压校验后、扇出前，把 md 列表物化为子任务并经 EVENT_BUS 下发 fork 事件。

    时机 (不可提前 / 不可延后):
    - `node_process_md_zip` 已完成解压、图片完整性校验、路径越界检查与
      `_check_unique_stems`，此时 markdown_file_paths 是最终事实；
    - 尚未开始任何 tail 节点，前端收到 fork 后可以稳定创建全部子卡。

    设计:
    - 父 task_id 保持不变 (Milvus / MinIO / 清场语义不动)；
    - 每个 md 分配 `f"{task_id}:md:{index}"`，只作为进度命名空间；
    - 只读 markdown_file_paths，不修改任何业务字段；
    - fork 推送失败不阻断图执行 (SSE 队列可能已被客户端断开清理)；
    - 幂等：节点被重试时不重复注册 / 重复下发。
    """
    if state.get("md_children"):
        return state

    task_id = state.get("task_id", "")
    md_dir = (IMPORT_TMP_DIR / state.get("file_title", "")).resolve()

    children: list[MdChild] = []
    for index, md_path_str in enumerate(state.get("markdown_file_paths", [])):
        md_path = Path(md_path_str)
        try:
            relative_path = md_path.resolve().relative_to(md_dir).as_posix()
        except ValueError:
            # 防御: 理论上 md 一定在解压根目录下; 异常时退回文件名, 不阻断链路
            relative_path = md_path.name
            logger.warning(
                "md 路径不在解压根目录下: task_id={}, path={}",
                task_id,
                md_path,
            )

        children.append(
            {
                "child_task_id": f"{task_id}:md:{index}",
                "title": md_path.stem,
                "path": relative_path,
                "markdown_file_path": str(md_path),
                "index": index,
            }
        )

    if children:
        # 组合点: 先登记子任务并取 fork 载荷 (task_manager), 再推帧 (event_bus)
        fork_payload = TASK_MANAGER.fork(task_id, children)
        if fork_payload is not None:
            try:
                EVENT_BUS.push(task_id, SSEEvent.FORK, fork_payload)
            except Exception:
                logger.warning(
                    "fork 事件推送失败: parent_id={}", task_id, exc_info=True
                )
        logger.info("md 任务分叉: task_id={}, count={}", task_id, len(children))

    # 放在 fork 之后: 注册与推送成功才落 state, 节点重试时不会跳过 fork
    state["md_children"] = children
    return state
