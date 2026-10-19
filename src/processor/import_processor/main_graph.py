from langgraph.constants import END
from langgraph.graph import StateGraph
from processor.import_processor.state import FileType, ImportNodeState
from processor.import_processor.nodes import *

workflow = StateGraph(ImportNodeState)

# 注册节点:
workflow.add_node(node_entry)
workflow.add_node(node_pdf_to_md)
workflow.add_node(node_md_img)
workflow.add_node(node_process_standalone_md)
workflow.add_node(node_document_split)
workflow.add_node(node_item_name_vect)
workflow.add_node(node_chunks_vect)


def file_type_router(state: ImportNodeState):
    file_type = state.get("origin_file_type", FileType.UNKNOWN)
    if file_type == FileType.MARKDOWN:
        return "node_process_standalone_md"
    elif file_type == FileType.PDF:
        return "node_pdf_to_md"
    else:
        return END


# 构建工作流
workflow.set_entry_point("node_entry")
workflow.add_conditional_edges(
    "node_entry",
    file_type_router,
    path_map={
        "node_pdf_to_md": "node_pdf_to_md",
        "node_process_standalone_md": "node_process_standalone_md",
        "node_md_img": "node_md_img",
        END: END,
    },
)
workflow.add_edge("node_process_standalone_md", "node_md_img")
workflow.add_edge("node_pdf_to_md", "node_md_img")
workflow.add_edge("node_md_img", "node_document_split")
workflow.add_edge("node_document_split", "node_item_name_vect")
workflow.add_edge("node_item_name_vect", "node_chunks_vect")
workflow.add_edge("node_chunks_vect", END)

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
