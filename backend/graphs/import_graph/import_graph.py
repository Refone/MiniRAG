from typing import Annotated, TypedDict

from langgraph.config import get_config
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.types import Send

from common.events import EVENT_BUS, TASK_MANAGER, SSEEvent
from common.events.tracing import trace_node
from common.schema.token_usage import TokenUsage, sum_token_usage
from graphs.import_graph.import_graph_state import (
    FileType,
    ImportGraphState,
    _keep_latest,
    create_state,
)
from graphs.import_graph.nodes import (
    node_document_embedding,
    node_document_split,
    node_entry,
    node_md_fork,
    node_md_img,
    node_pdf_to_md,
    node_process_md_zip,
    node_process_standalone_md,
)


# --------------------------------------------------------------------------- #
# md 后续处理子图 (node_md_img -> document_split -> document_embedding)
#
# 独立编译为子图, 作为父图的一个节点 "node_md_tail" 使用:
# - md 压缩包扇出时, 每个 md 分支 Send 到本子图, 分支内拥有独立的 state
#   (LangGraph 的 Send 分支不隔离状态, 多步分支必须借子图隔离);
# - PDF / 独文件 md 流程也复用同一段子图, 三条链路行为一致。
# --------------------------------------------------------------------------- #
class MdTailOutput(TypedDict):
    """
    md_tail 子图的输出 schema: 只把结果字段写回父图。

    若不限制输出, 子图会把完整状态 (task_id / file_title 等) 写回父图通道,
    md 压缩包多分支并发完成时会在非 reducer 字段上触发 InvalidUpdateError。
    (item_name 已随 node_item_name_vect 的合并移除)

    token_meter 必须显式回写: 子图内的节点只返回本节点增量, 通道累计值
    (sum_token_usage reducer) 就是本分支的计量增量, 回写后父图对多分支
    增量继续折叠累加。
    """

    markdown_file_path: Annotated[str, _keep_latest]
    chunks_json_path: Annotated[str, _keep_latest]
    token_meter: Annotated[TokenUsage, sum_token_usage]


md_tail_workflow = StateGraph(ImportGraphState, output_schema=MdTailOutput)
md_tail_workflow.add_node(node_md_img)
md_tail_workflow.add_node(node_document_split)
md_tail_workflow.add_node(node_document_embedding)
md_tail_workflow.set_entry_point("node_md_img")
md_tail_workflow.add_edge("node_md_img", "node_document_split")
md_tail_workflow.add_edge("node_document_split", "node_document_embedding")
md_tail_workflow.add_edge("node_document_embedding", END)
md_tail_graph = md_tail_workflow.compile()


# --------------------------------------------------------------------------- #
# 分支包装节点: 调用 md_tail 子图, 并统一收口子任务的 complete / failed。
# 收口后从 task_manager 取快照, 经 event_bus 推一帧 child-progress
# (组合点在调用侧, task_manager 本身不推送)。
#
# 为什么不直接把编译好的子图挂成节点:
# - 子图正常返回后需要知道「是哪个 child」才能置 complete;
# - 子图异常冒泡前需要置 failed (失败节点由 trace_node 记入 failed_list);
# - 只回写 MdTailOutput 的两个结果字段, 继续避免父图通道并发写冲突;
# - PDF / 独文件 md 的 child_task_id 为空, 本节点对它们透明。
# --------------------------------------------------------------------------- #
@trace_node(desc="处理 Markdown 尾巴", task_trace=False)
def node_md_tail_branch(state: ImportGraphState):
    child_id = state.get("child_task_id") or ""
    parent_id = state.get("task_id", "")
    try:
        # 透传当前 LangGraph config, 保留 callbacks / tracing / recursion limit
        result = md_tail_graph.invoke(state, get_config())
    except Exception as e:
        if child_id:
            snapshot = TASK_MANAGER.fail_child(child_id, str(e))
            if snapshot is not None:
                EVENT_BUS.push(parent_id, SSEEvent.CHILD_PROGRESS, snapshot)
        raise

    if child_id:
        snapshot = TASK_MANAGER.complete_child(child_id)
        if snapshot is not None:
            EVENT_BUS.push(parent_id, SSEEvent.CHILD_PROGRESS, snapshot)

    return {
        "markdown_file_path": result.get("markdown_file_path", ""),
        "chunks_json_path": result.get("chunks_json_path", ""),
        # 子图通道累计的本分支计量增量, 写回父图由 reducer 折叠
        "token_meter": result.get("token_meter") or {},
    }


# --------------------------------------------------------------------------- #
# 父图: 入口识别 -> 按类型分叉 -> (ZIP 先 fork) -> md_tail 分支 -> 结束
# --------------------------------------------------------------------------- #
workflow = StateGraph(ImportGraphState)

# 注册节点:
workflow.add_node(node_entry)
workflow.add_node(node_pdf_to_md)
workflow.add_node(node_process_standalone_md)
workflow.add_node(node_process_md_zip)
workflow.add_node(node_md_fork)
workflow.add_node("node_md_tail", node_md_tail_branch)


def file_type_router(state: ImportGraphState):
    file_type = state.get("origin_file_type", FileType.UNKNOWN)
    if file_type == FileType.MARKDOWN:
        return "node_process_standalone_md"
    elif file_type == FileType.PDF:
        return "node_pdf_to_md"
    elif file_type == FileType.MARKDOWN_ZIP:
        return "node_process_md_zip"
    else:
        return END


def zip_fanout_router(state: ImportGraphState):
    """
    md 压缩包扇出路由: node_md_fork 已物化 md_children, 这里为每个 md 开一条
    并行分支 (Send 到 node_md_tail 包装节点), 各自携带独立的:
    - child_task_id: 进度命名空间 (不改变业务 task_id)
    - file_title:    md 文件名 (业务唯一键)
    - markdown_file_path: 该 md 的绝对路径

    说明: 各分支结束时只把两个结果字段写回父图 (见 MdTailOutput),
    并发写同一字段由 state 中 _keep_latest reducer 折叠, 最终父图取值是
    "最后完成分支"的值; 各 md 的真实产出在 Milvus / 磁盘, 不受影响。
    """
    sends = [
        Send(
            "node_md_tail",
            create_state(
                task_id=state.get("task_id", ""),
                child_task_id=child["child_task_id"],
                origin_file_path=state.get("origin_file_path", ""),
                origin_file_type=state.get("origin_file_type", ""),
                markdown_file_path=child["markdown_file_path"],
                file_title=child["title"],
                # 注意: 子分支不继承父状态的 token_meter (create_state 默认
                # 从 0 起算), 各分支返回本分支增量, 回归父图时由 reducer
                # 折叠累加; 若继承累计值会重复计量
            ),
        )
        for child in state.get("md_children", [])
    ]
    if not sends:
        return END
    return sends


# 构建工作流
workflow.set_entry_point("node_entry")
workflow.add_conditional_edges(
    "node_entry",
    file_type_router,
    path_map={
        "node_pdf_to_md": "node_pdf_to_md",
        "node_process_standalone_md": "node_process_standalone_md",
        "node_process_md_zip": "node_process_md_zip",
        END: END,
    },
)
workflow.add_edge("node_pdf_to_md", "node_md_tail")
workflow.add_edge("node_process_standalone_md", "node_md_tail")
# md 压缩包: 解压校验 -> fork 子任务 -> 按 md 文件数动态扇出 (每个 md 一条分支)
workflow.add_edge("node_process_md_zip", "node_md_fork")
workflow.add_conditional_edges(
    "node_md_fork",
    zip_fanout_router,
    path_map={END: END},
)
workflow.add_edge("node_md_tail", END)

import_graph = workflow.compile()

if __name__ == "__main__":
    from rich import print as rprint

    from common.config.path_config import fixture_path
    from common.events import TASK_MANAGER
    from common.logging import logger
    from graphs.import_graph.import_graph_state import create_state

    print(import_graph.get_graph().draw_ascii())

    task_id = "import-pdf-test"
    # origin_file_path = fixture_path("hak180产品安全手册.pdf")
    origin_file_path = fixture_path("万用表RS-12的使用.pdf")

    TASK_MANAGER.clear(task_id)
    initial_state = create_state(
        task_id=task_id,
        origin_file_path=str(origin_file_path),
    )

    end_state = import_graph.invoke(initial_state)

    logger.complete()

    rprint(TASK_MANAGER.get_nodes(task_id)[0])
    rprint(end_state)
