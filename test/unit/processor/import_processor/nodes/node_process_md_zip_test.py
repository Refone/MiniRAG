"""单元测试: src/processor/import_processor/nodes/node_process_md_zip.py

被测对象:
    step_1_validate_and_get_data   zip 文件与标题校验
    step_2_unzip_md_zip            解压 + macOS 垃圾清理 + zip-slip 防护
    step_3_check_md_content        md 扫描 / 图片校验 / 冗余清理
    node_process_md_zip            节点编排

说明:
    - 所有外部调用 (网络下载) 一律 mock, 不打真实网络。
    - 解压目录通过 monkeypatch ENV_CONFIG.mineru.unzip_dir 指到 tmp_path。
"""

from __future__ import annotations

import importlib
import zipfile
from pathlib import Path

import pytest

# 注意: 不能用 `import ...nodes.node_process_md_zip as ...`, 包 __init__ 把同名
# 函数重导出了, 会拿到函数而非模块; 用 importlib 直接从 sys.modules 取模块对象。
node_md_zip = importlib.import_module("processor.import_processor.nodes.node_process_md_zip")

from processor.import_processor.state import create_state


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _make_zip(tmp_path: Path, files: dict[str, str | bytes], name: str = "notes.zip") -> Path:
    """按文件名 -> 内容 构造一个 zip 文件, 返回其路径。"""
    zip_path = tmp_path / name
    with zipfile.ZipFile(zip_path, "w") as zf:
        for filename, content in files.items():
            if isinstance(content, str):
                content = content.encode("utf-8")
            zf.writestr(filename, content)
    return zip_path


def _configure_unzip_dir(monkeypatch, tmp_path: Path) -> Path:
    """把解压根目录指到 tmp_path/import, 并返回该路径。"""
    unzip_dir = tmp_path / "import"
    monkeypatch.setattr(node_md_zip.ENV_CONFIG.mineru, "unzip_dir", str(unzip_dir))
    return unzip_dir


def _fake_download(url: str, images_dir: Path, filename: str) -> None:
    """_download_image 替身: 直接把假图片字节写到目标位置。"""
    (images_dir / filename).write_bytes(b"fake-image-bytes")


# --------------------------------------------------------------------------- #
# step_1: 校验
# --------------------------------------------------------------------------- #
def test_step1_empty_path_raises():
    state = create_state(task_id="t", origin_file_path="")
    with pytest.raises(ValueError, match="原始文档路径为空"):
        node_md_zip.step_1_validate_and_get_data(state)


def test_step1_missing_file_raises(tmp_path: Path):
    state = create_state(task_id="t", origin_file_path=str(tmp_path / "no.zip"))
    with pytest.raises(FileNotFoundError, match="md 压缩包不存在"):
        node_md_zip.step_1_validate_and_get_data(state)


def test_step1_not_zip_raises(tmp_path: Path):
    path = tmp_path / "fake.zip"
    path.write_text("not a zip", encoding="utf-8")
    state = create_state(task_id="t", origin_file_path=str(path))
    with pytest.raises(ValueError, match="不是有效的 zip"):
        node_md_zip.step_1_validate_and_get_data(state)


def test_step1_missing_title_raises(tmp_path: Path):
    zip_path = _make_zip(tmp_path, {"a.md": "# a"})
    state = create_state(task_id="t", origin_file_path=str(zip_path), file_title="")
    with pytest.raises(ValueError, match="文档标题为空"):
        node_md_zip.step_1_validate_and_get_data(state)


def test_step1_valid_zip_ok(tmp_path: Path):
    zip_path = _make_zip(tmp_path, {"a.md": "# a"})
    state = create_state(task_id="t", origin_file_path=str(zip_path), file_title="notes")
    result = node_md_zip.step_1_validate_and_get_data(state)
    assert result == (zip_path, "notes")


# --------------------------------------------------------------------------- #
# step_2: 解压
# --------------------------------------------------------------------------- #
def test_step2_unzip_and_clean_macos_junk(monkeypatch, tmp_path: Path):
    unzip_dir = _configure_unzip_dir(monkeypatch, tmp_path)
    zip_path = _make_zip(
        tmp_path,
        {
            "notes.md": "# 正文",
            "images/a.png": b"png",
            "__MACOSX/notes.md": "junk",
            "._notes.md": "junk",
        },
    )

    md_dir = node_md_zip.step_2_unzip_md_zip(zip_path, "notes")

    assert md_dir == unzip_dir / "notes"
    assert (md_dir / "notes.md").is_file()
    assert not (md_dir / "__MACOSX").exists()
    assert not (md_dir / "._notes.md").exists()


def test_step2_reimport_overwrites(monkeypatch, tmp_path: Path):
    unzip_dir = _configure_unzip_dir(monkeypatch, tmp_path)
    md_dir = unzip_dir / "notes"
    md_dir.mkdir(parents=True)
    (md_dir / "old.md").write_text("# old", encoding="utf-8")
    zip_path = _make_zip(tmp_path, {"new.md": "# new"})

    node_md_zip.step_2_unzip_md_zip(zip_path, "notes")

    assert not (md_dir / "old.md").exists()
    assert (md_dir / "new.md").read_text(encoding="utf-8") == "# new"


def test_step2_zip_slip_rejected(monkeypatch, tmp_path: Path):
    _configure_unzip_dir(monkeypatch, tmp_path)
    zip_path = _make_zip(tmp_path, {"../evil.txt": "evil"})

    with pytest.raises(RuntimeError, match="越界路径"):
        node_md_zip.step_2_unzip_md_zip(zip_path, "notes")


# --------------------------------------------------------------------------- #
# step_3: 扫描 + 校验 + 冗余清理
# --------------------------------------------------------------------------- #
def test_step3_no_md_raises(monkeypatch, tmp_path: Path):
    unzip_dir = _configure_unzip_dir(monkeypatch, tmp_path)
    md_dir = unzip_dir / "notes"
    md_dir.mkdir(parents=True)
    (md_dir / "readme.txt").write_text("no md", encoding="utf-8")

    with pytest.raises(RuntimeError, match="未找到任何 md 文件"):
        node_md_zip.step_3_check_md_content(md_dir, "notes")


def test_step3_missing_local_image_raises(monkeypatch, tmp_path: Path):
    unzip_dir = _configure_unzip_dir(monkeypatch, tmp_path)
    md_dir = unzip_dir / "notes"
    md_dir.mkdir(parents=True)
    (md_dir / "notes.md").write_text("![](images/gone.png)", encoding="utf-8")

    with pytest.raises(RuntimeError, match="缺失") as exc_info:
        node_md_zip.step_3_check_md_content(md_dir, "notes")
    assert "images/gone.png" in str(exc_info.value)


def test_step3_online_image_downloaded_and_rewritten(monkeypatch, tmp_path: Path):
    unzip_dir = _configure_unzip_dir(monkeypatch, tmp_path)
    md_dir = unzip_dir / "notes"
    md_dir.mkdir(parents=True)
    (md_dir / "notes.md").write_text(
        "# t\n![a](https://example.com/pic.png)", encoding="utf-8"
    )
    monkeypatch.setattr(node_md_zip, "_download_image", _fake_download)

    result = node_md_zip.step_3_check_md_content(md_dir, "notes")

    assert result == [md_dir / "notes.md"]
    md_text = (md_dir / "notes.md").read_text(encoding="utf-8")
    assert "![a](images/pic.png)" in md_text
    assert (md_dir / "images" / "pic.png").read_bytes() == b"fake-image-bytes"


def test_step3_local_image_copied_next_to_md(monkeypatch, tmp_path: Path):
    """md 引用嵌套目录中的图片时, 拷贝到 md 旁 images/ 并改写引用。"""
    unzip_dir = _configure_unzip_dir(monkeypatch, tmp_path)
    md_dir = unzip_dir / "notes"
    (md_dir / "sub").mkdir(parents=True)
    (md_dir / "sub" / "notes.md").write_text("![](../assets/pic.png)", encoding="utf-8")
    (md_dir / "assets").mkdir()
    (md_dir / "assets" / "pic.png").write_bytes(b"real-png")

    result = node_md_zip.step_3_check_md_content(md_dir, "notes")

    assert result == [md_dir / "sub" / "notes.md"]
    assert "![](images/pic.png)" in (md_dir / "sub" / "notes.md").read_text(encoding="utf-8")
    assert (md_dir / "sub" / "images" / "pic.png").read_bytes() == b"real-png"


def test_step3_single_md_renamed(monkeypatch, tmp_path: Path):
    unzip_dir = _configure_unzip_dir(monkeypatch, tmp_path)
    md_dir = unzip_dir / "notes"
    md_dir.mkdir(parents=True)
    (md_dir / "full.md").write_text("# full", encoding="utf-8")

    result = node_md_zip.step_3_check_md_content(md_dir, "notes")

    assert result == [md_dir / "notes.md"]
    assert not (md_dir / "full.md").exists()


def test_step3_multi_md_sorted(monkeypatch, tmp_path: Path):
    unzip_dir = _configure_unzip_dir(monkeypatch, tmp_path)
    md_dir = unzip_dir / "notes"
    md_dir.mkdir(parents=True)
    (md_dir / "b.md").write_text("# b", encoding="utf-8")
    (md_dir / "a.md").write_text("# a", encoding="utf-8")

    result = node_md_zip.step_3_check_md_content(md_dir, "notes")

    assert result == [md_dir / "a.md", md_dir / "b.md"]


def test_step3_duplicate_stems_raise(monkeypatch, tmp_path: Path):
    unzip_dir = _configure_unzip_dir(monkeypatch, tmp_path)
    md_dir = unzip_dir / "notes"
    (md_dir / "x").mkdir(parents=True)
    (md_dir / "y").mkdir()
    (md_dir / "x" / "same.md").write_text("# x", encoding="utf-8")
    (md_dir / "y" / "same.md").write_text("# y", encoding="utf-8")

    with pytest.raises(RuntimeError, match="同名 md 文件"):
        node_md_zip.step_3_check_md_content(md_dir, "notes")


def test_step3_redundant_images_and_files_removed(monkeypatch, tmp_path: Path):
    unzip_dir = _configure_unzip_dir(monkeypatch, tmp_path)
    md_dir = unzip_dir / "notes"
    (md_dir / "images").mkdir(parents=True)
    (md_dir / "notes.md").write_text("![](images/used.png)", encoding="utf-8")
    (md_dir / "images" / "used.png").write_bytes(b"used")
    (md_dir / "images" / "unused.png").write_bytes(b"unused")
    (md_dir / "extra.txt").write_text("redundant", encoding="utf-8")

    result = node_md_zip.step_3_check_md_content(md_dir, "notes")

    assert result == [md_dir / "notes.md"]
    assert (md_dir / "images" / "used.png").is_file()
    assert not (md_dir / "images" / "unused.png").exists()
    assert not (md_dir / "extra.txt").exists()


# --------------------------------------------------------------------------- #
# node_process_md_zip: 编排
# --------------------------------------------------------------------------- #
def test_node_single_md_sets_both_path_fields(monkeypatch, tmp_path: Path):
    _configure_unzip_dir(monkeypatch, tmp_path)
    zip_path = _make_zip(tmp_path, {"full.md": "# 正文"})
    state = create_state(task_id="t", origin_file_path=str(zip_path), file_title="notes")

    result = node_md_zip.node_process_md_zip(state)

    assert result["markdown_file_path"].endswith("import/notes/notes.md")
    assert result["markdown_file_paths"] == [result["markdown_file_path"]]


def test_node_multi_md_sets_only_list(monkeypatch, tmp_path: Path):
    _configure_unzip_dir(monkeypatch, tmp_path)
    zip_path = _make_zip(tmp_path, {"01.md": "# 1", "02.md": "# 2"})
    state = create_state(task_id="t", origin_file_path=str(zip_path), file_title="notes")

    result = node_md_zip.node_process_md_zip(state)

    assert result["markdown_file_path"] == ""
    assert [Path(p).name for p in result["markdown_file_paths"]] == ["01.md", "02.md"]
