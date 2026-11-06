import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def load_checker():
    """按文件路径加载 tools/check_layout.py, 便于替换 ROOT / LAYOUT。"""
    spec = importlib.util.spec_from_file_location(
        "check_layout", ROOT / "tools" / "check_layout.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def init_git(repo: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)


def test_check_layout__ignored_dir_absent__passes(tmp_path, monkeypatch):
    """Given 不入库目录在 checkout 中不存在 When 跑目录契约 Then 仍判为已忽略。"""
    if shutil.which("git") is None:
        pytest.skip("git 不可用")

    (tmp_path / ".gitignore").write_text("var/\n", encoding="utf-8")
    init_git(tmp_path)

    checker = load_checker()
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker, "LAYOUT", {"var": (False, "运行时产物")})

    assert checker.main() == 0


def test_check_layout__unregistered_top_dir__fails(tmp_path, monkeypatch, capsys):
    """Given 顶层目录已入库但没登记 When 跑目录契约 Then 报未登记并退出 1。"""
    if shutil.which("git") is None:
        pytest.skip("git 不可用")

    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "logo.svg").write_text("<svg/>", encoding="utf-8")
    init_git(tmp_path)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)

    checker = load_checker()
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker, "LAYOUT", {"backend": (True, "后端源码")})

    assert checker.main() == 1
    assert "[未登记] 顶层目录未出现在 LAYOUT: assets/" in capsys.readouterr().out


def test_check_layout__missing_tracked_dir__fails(tmp_path, monkeypatch, capsys):
    """Given 登记为入库的目录不存在 When 跑目录契约 Then 报缺目录并退出 1。"""
    checker = load_checker()
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker, "LAYOUT", {"backend": (True, "后端源码")})

    assert checker.main() == 1
    assert "[缺目录] LAYOUT 标为入库, 但不存在: backend/" in capsys.readouterr().out
