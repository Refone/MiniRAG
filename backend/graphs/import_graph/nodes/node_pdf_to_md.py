from pathlib import Path

from pypdf import PdfReader

from common import client
from common.events.tracing import report_progress, step_log, trace_node
from common.logging import logger
from graphs.import_graph.import_graph_state import ImportGraphState

# PDF 文件头魔数 (前 5 字节)
_PDF_MAGIC = b"%PDF-"


def pdf_page_cnt(pdf_path: Path) -> int:
    """获取 PDF 的页数"""
    with pdf_path.open("rb") as f:
        reader = PdfReader(f)
        return len(reader.pages)


@step_log("校验 PDF 文件")
def step_1_validate_and_setup(state: ImportGraphState) -> tuple[Path, int, str]:
    """校验原始文件是真实存在的 PDF, 并从 state 取回文件标题（由 node_entry 写入）。"""
    origin = state.get("origin_file_path")
    if not origin:
        raise ValueError(f"origin_file_path 为空: {origin!r}")

    pdf_path = Path(origin)
    if not pdf_path.is_file():
        raise ValueError(f"文件不存在或不是文件: {pdf_path}")

    with pdf_path.open("rb") as f:
        if f.read(len(_PDF_MAGIC)) != _PDF_MAGIC:
            raise ValueError(f"文件不是 PDF 格式: {pdf_path}")

    file_title = state.get("file_title")
    if not file_title:
        raise ValueError(f"file_title 为空: {state!r}")

    logger.info(f"PDF 校验通过: {pdf_path}")
    return pdf_path, pdf_page_cnt(pdf_path), file_title


@trace_node(desc="PDF 转 Markdown", need_push=True)
def node_pdf_to_md(state: ImportGraphState) -> ImportGraphState:
    """校验 PDF → MinerU 转换下载 → 写回 markdown_file_path。"""
    pdf_path, page_cnt, file_title = step_1_validate_and_setup(state)
    md_path = client.mineru_pdf_to_md(
        pdf_path,
        page_cnt,
        file_title,
        on_progress=report_progress,
    )
    state["markdown_file_path"] = str(md_path)
    return state


if __name__ == "__main__":
    from rich import print as rprint

    from common.config.path_config import snapshot_path
    from graphs.import_graph.import_graph_state import load_state, save_state

    prev_state = load_state(snapshot_path("import_01_entry.json"))
    next_state = node_pdf_to_md(prev_state)
    rprint(next_state)

    new_state_json = snapshot_path("import_02_pdf_to_md.json")

    save_state(next_state, new_state_json)
    logger.info("PDF to Markdown 处理完成")
    logger.info(f"状态保存路径: {new_state_json}")
    logger.info(f"文件输出路径: {next_state['markdown_file_path']}")
