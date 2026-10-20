from pathlib import Path
from typing import TypedDict, Annotated

from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.types import Send
from processor.import_processor.state import (
    FileType,
    ImportGraphState,
    _keep_latest,
    create_state,
)
from processor.import_processor.nodes import *

# --------------------------------------------------------------------------- #
# md 后续处理子图 (node_md_img -> document_split -> item_name -> chunks)
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
    """

    markdown_file_path: Annotated[str, _keep_latest]
    chunks_json_path: Annotated[str, _keep_latest]
    item_name: Annotated[str, _keep_latest]


md_tail_workflow = StateGraph(ImportGraphState, output_schema=MdTailOutput)
md_tail_workflow.add_node(node_md_img)
md_tail_workflow.add_node(node_document_split)
md_tail_workflow.add_node(node_item_name_vect)
md_tail_workflow.add_node(node_chunks_vect)
md_tail_workflow.set_entry_point("node_md_img")
md_tail_workflow.add_edge("node_md_img", "node_document_split")
md_tail_workflow.add_edge("node_document_split", "node_item_name_vect")
md_tail_workflow.add_edge("node_item_name_vect", "node_chunks_vect")
md_tail_workflow.add_edge("node_chunks_vect", END)
md_tail_processor = md_tail_workflow.compile()

# --------------------------------------------------------------------------- #
# 父图: 入口识别 -> 按类型分叉 -> md_tail 子图 -> 结束
# --------------------------------------------------------------------------- #
workflow = StateGraph(ImportGraphState)

# 注册节点:
workflow.add_node(node_entry)
workflow.add_node(node_pdf_to_md)
workflow.add_node(node_process_standalone_md)
workflow.add_node(node_process_md_zip)
workflow.add_node("node_md_tail", md_tail_processor)


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
    md 压缩包扇出路由: 解压校验后得到的每个 md 文件各开一条并行分支
    (Send 到 node_md_tail 子图), 各自携带独立的 file_title (md 文件名)
    与 markdown_file_path, 完整走一遍后续流程 (LangGraph 官方 map-reduce 模式)。

    说明: 各分支结束时只把 3 个结果字段写回父图 (见 MdTailOutput),
    并发写同一字段由 state 中 _keep_latest reducer 折叠, 最终父图取值是
    "最后完成分支"的值; 各 md 的真实产出在 Milvus / 磁盘, 不受影响。
    """
    sends = [
        Send(
            "node_md_tail",
            create_state(
                task_id=state.get("task_id", ""),
                origin_file_path=state.get("origin_file_path", ""),
                origin_file_type=state.get("origin_file_type", ""),
                markdown_file_path=md_path,
                file_title=Path(md_path).stem,
            ),
        )
        for md_path in state.get("markdown_file_paths", [])
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
# md 压缩包: 解压校验后按 md 文件数动态扇出 (每个 md 一条分支)
workflow.add_conditional_edges(
    "node_process_md_zip",
    zip_fanout_router,
    path_map={END: END},
)
workflow.add_edge("node_md_tail", END)

import_processor = workflow.compile()

if __name__ == "__main__":
    from utils import task_utils
    from processor.import_processor.state import create_state
    from utils.logging_utils import logger
    from utils.path_utils import PROJECT_ROOT
    from rich import print as rprint

    print(import_processor.get_graph().draw_ascii())

    task_id = "import-pdf-test"
    # origin_file_path = PROJECT_ROOT / "asset/hak180产品安全手册.pdf"
    origin_file_path = PROJECT_ROOT / "asset/万用表RS-12的使用.pdf"

    task_utils.clear_task(task_id)
    initial_state = create_state(
        task_id=task_id,
        origin_file_path=str(origin_file_path),
    )

    end_state = import_processor.invoke(initial_state)

    logger.complete()

    rprint(task_utils.get_task_done_nodes(task_id))
    rprint(end_state)
