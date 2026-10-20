"""单元测试: src/processor/import_processor/main_graph.py

被测对象:
    file_type_router    按文件类型路由: PDF / MARKDOWN / MARKDOWN_ZIP / UNKNOWN
    zip_fanout_router   md 压缩包扇出: 每个 md 一条 Send 分支
    import_processor    编译后的导入流程图

说明:
    - 路由与扇出函数是纯函数, 直接断言返回值。
    - 端到端用例把 tail 节点的 step 函数 monkeypatch 掉, 不依赖外部服务,
      验证「压缩包内每个 md 都独立走完一遍后续流程」。
"""

from __future__ import annotations

import importlib
import zipfile
from collections import Counter
from pathlib import Path

import pytest
from langgraph.types import Send

from processor.import_processor.main_graph import (
    file_type_router,
    import_processor,
    zip_fanout_router,
)
from processor.import_processor.state import FileType, create_state

# 注意: 不能用 `import ...nodes.node_xxx as ...`, 包 __init__ 把同名函数重导出了,
# 会拿到函数而非模块; 用 importlib 直接从 sys.modules 取模块对象。
node_md_img = importlib.import_module("processor.import_processor.nodes.node_md_img")
node_split = importlib.import_module("processor.import_processor.nodes.node_document_split")
node_item = importlib.import_module("processor.import_processor.nodes.node_item_name_vect")
node_chunks = importlib.import_module("processor.import_processor.nodes.node_chunks_vect")
node_zip = importlib.import_module("processor.import_processor.nodes.node_process_md_zip")


def _state(**kwargs) -> dict:
    return create_state(task_id="t", **kwargs)


# --------------------------------------------------------------------------- #
# file_type_router: 路由
# --------------------------------------------------------------------------- #
def test_router_missing_type_falls_back_to_end():
    assert file_type_router(_state()) == "__end__"


@pytest.mark.parametrize(
    ("file_type", "expected"),
    [
        (FileType.MARKDOWN, "node_process_standalone_md"),
        (FileType.PDF, "node_pdf_to_md"),
        (FileType.MARKDOWN_ZIP, "node_process_md_zip"),
        (FileType.UNKNOWN, "__end__"),
    ],
)
def test_router_by_file_type(file_type: str, expected: str):
    assert file_type_router(_state(origin_file_type=file_type)) == expected


# --------------------------------------------------------------------------- #
# zip_fanout_router: 扇出
# --------------------------------------------------------------------------- #
def test_fanout_router_sends_one_branch_per_md():
    state = _state(
        origin_file_path="/a/notes.zip",
        origin_file_type=FileType.MARKDOWN_ZIP,
        markdown_file_paths=["/import/notes/01-基础.md", "/import/notes/02-进阶.md"],
    )

    sends = zip_fanout_router(state)

    assert len(sends) == 2
    assert all(isinstance(send, Send) and send.node == "node_md_tail" for send in sends)
    assert [send.arg["file_title"] for send in sends] == ["01-基础", "02-进阶"]
    assert [send.arg["markdown_file_path"] for send in sends] == state["markdown_file_paths"]
    # 分支状态携带任务上下文 (装饰器 / 日志依赖 task_id)
    assert all(send.arg["task_id"] == "t" for send in sends)


def test_fanout_router_empty_list_returns_end():
    assert zip_fanout_router(_state(markdown_file_paths=[])) == "__end__"


# --------------------------------------------------------------------------- #
# import_processor: 图结构
# --------------------------------------------------------------------------- #
def test_graph_registers_expected_nodes():
    graph = import_processor.get_graph()
    # tail 四节点封装在 node_md_tail 子图内, 父图只注册入口与分叉节点
    assert {
        "node_entry",
        "node_pdf_to_md",
        "node_process_standalone_md",
        "node_process_md_zip",
        "node_md_tail",
    } <= set(graph.nodes)


# --------------------------------------------------------------------------- #
# 端到端: 压缩包内每个 md 各走一遍后续流程 (tail 节点全部 mock, 不打外部服务)
# --------------------------------------------------------------------------- #
def _make_two_md_zip(tmp_path: Path) -> Path:
    zip_path = tmp_path / "notes.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("01-基础.md", "# 01")
        zf.writestr("02-进阶.md", "# 02")
    return zip_path


def test_zip_fanout_runs_each_md_through_full_tail(monkeypatch, tmp_path: Path):
    zip_path = _make_two_md_zip(tmp_path)
    monkeypatch.setattr(node_zip.ENV_CONFIG.mineru, "unzip_dir", str(tmp_path / "import"))

    # 记录每个分支实际处理的 file_title (md_img 与 split 两个节点各记录一次)
    processed: list[str] = []

    def fake_load(state):
        title = state["file_title"]
        processed.append(title)
        return Path(state["markdown_file_path"]), "", title

    # node_md_img
    monkeypatch.setattr(node_md_img, "step_1_validate_and_load_data", fake_load)
    monkeypatch.setattr(node_md_img, "step_2_scan_images", lambda *a, **k: [])
    monkeypatch.setattr(node_md_img, "step_3_image_summary", lambda *a, **k: {})
    monkeypatch.setattr(node_md_img, "step_4_upload_images_get_url", lambda *a, **k: {})
    monkeypatch.setattr(node_md_img, "step_5_md_content_image_replace", lambda c, s, u: c)
    monkeypatch.setattr(node_md_img, "step_6_new_content_to_disk", lambda p, c: p)

    # node_document_split
    monkeypatch.setattr(node_split, "step_1_validate_and_get_data", fake_load)
    monkeypatch.setattr(node_split, "step_2_split_markdown", lambda c: [])
    monkeypatch.setattr(
        node_split,
        "step_3_backup_chunks_json",
        lambda md, title, chunks: md.parent / f"{title}_chunks.json",
    )

    # node_item_name_vect
    monkeypatch.setattr(node_item, "step_1_validate_and_get_data", lambda s: ("", s["file_title"]))
    monkeypatch.setattr(
        node_item, "step_2_call_llm_return_item_name", lambda c, t: f"item-{t}"
    )
    monkeypatch.setattr(node_item, "step_3_insert_item_name", lambda *a, **k: None)

    # node_chunks_vect
    monkeypatch.setattr(
        node_chunks,
        "step_1_validate_and_get_data",
        lambda s: (s["file_title"], s["item_name"], []),
    )
    monkeypatch.setattr(node_chunks, "step_2_vect_chunks", lambda chunks: [])
    monkeypatch.setattr(node_chunks, "step_3_chunk_upsert_milvus", lambda *a, **k: None)

    initial = create_state(task_id="fanout-e2e", origin_file_path=str(zip_path))
    final = import_processor.invoke(initial)

    # 每个 md 分支独立走完 tail 链路: md_img 与 split 的 step_1 各记录一次自己的
    # file_title (分支隔离由 node_md_tail 子图保证, 不会被父图 file_title 污染)
    assert Counter(processed) == Counter({"01-基础": 2, "02-进阶": 2})
    # 分支不写 file_title, 父图保留压缩包标题
    assert final["file_title"] == "notes"
    # 分支并发写的字段有 _keep_latest reducer, 最终取其中一个分支的值 (不报错即可)
    assert final["markdown_file_path"]
    assert final["item_name"] in {"item-01-基础", "item-02-进阶"}
