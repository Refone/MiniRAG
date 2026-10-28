from pathlib import Path

from graphs.import_graph.import_graph_state import (
    FileType,
    ImportGraphState,
    file_type_from_filename,
)
from utils.logging_utils import logger
from utils.node_utils import trace_node


@trace_node(desc="识别文档类别", need_push=True)
def node_entry(state: ImportGraphState) -> ImportGraphState:
    """校验文档, 确认文件存在且类型受支持"""
    origin_file_path = Path(state["origin_file_path"])
    if not origin_file_path.exists():
        raise FileNotFoundError(f"文件不存在: {origin_file_path}, 流程终止")

    doc_type = file_type_from_filename(origin_file_path.name)
    if doc_type == FileType.UNKNOWN:
        raise ValueError(f"未知文件类型: {origin_file_path}, 流程终止")

    state["origin_file_type"] = doc_type
    state["file_title"] = origin_file_path.stem

    return state


if __name__ == "__main__":
    from rich import print as rprint

    from graphs.import_graph.import_graph_state import create_state, save_state
    from utils.path_utils import fixture_path, snapshot_path

    start1 = create_state(
        task_id="test_task_start",
        origin_file_path=str(fixture_path("hello-agent.md")),
    )
    end1 = node_entry(start1)
    rprint(end1)

    try:
        start2 = create_state(
            task_id="test_task_start",
            origin_file_path=str(fixture_path("test.txt")),
        )
        end2 = node_entry(start2)
        rprint(end2)
    except Exception as e:
        logger.error(f"流程执行出错: {e}")

    start_state = create_state(
        task_id="test_task_start",
        origin_file_path=str(fixture_path("万用表RS-12的使用.pdf")),
    )
    end_state = node_entry(start_state)
    rprint(end_state)

    save_state(end_state, snapshot_path("import_01_entry.json"))
    logger.info(f"状态已保存: {snapshot_path('import_01_entry.json')}")
