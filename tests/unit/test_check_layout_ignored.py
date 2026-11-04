import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def test_check_layout__ignored_dir_absent__passes(tmp_path):
    """Given 不入库目录在 checkout 中不存在 When 跑目录契约 Then 仍判为已忽略。"""
    if shutil.which("git") is None:
        pytest.skip("git 不可用")

    repo = tmp_path
    (repo / ".gitignore").write_text("var/\n", encoding="utf-8")
    (repo / "README.md").write_text(
        "# fixture\n\n## 目录约定\n\n"
        "| 路径 | 入库 | 定位 |\n"
        "| --- | --- | --- |\n"
        "| `var/` | ❌ | 运行时产物 |\n",
        encoding="utf-8",
    )
    (repo / "tools").mkdir()
    shutil.copy(ROOT / "tools" / "check_layout.py", repo / "tools" / "check_layout.py")

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    result = subprocess.run(
        [sys.executable, str(repo / "tools" / "check_layout.py")],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
