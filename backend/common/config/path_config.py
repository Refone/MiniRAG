import os
from pathlib import Path

__all__ = [
    "PROJECT_ROOT",
    "FIXTURES_DIR",
    "IMPORT_TMP_DIR",
    "UPLOAD_TMP_DIR",
    "LOG_DIR",
    "TMP_DIR",
    "fixture_path",
    "runtime_tmp_dir",
    "snapshot_path",
]


# --------------------------------------------------------------------------- #
# 项目根定位
# --------------------------------------------------------------------------- #
# 项目根目录的“地标”：命中任意一项即认为该目录是项目根
_PROJECT_MARKERS = ("pyproject.toml", "uv.lock", ".env")


def get_project_root() -> Path:
    """定位项目根目录。

    1. 环境变量 `PROJECT_ROOT` 优先（生产 / 容器 / CI 显式指定）；
    2. 否则从本文件位置向上找含项目标记的目录；
    3. 都没有则抛 `FileNotFoundError`。
    """
    env_root = os.getenv("PROJECT_ROOT")
    if env_root:
        candidate = Path(env_root).resolve()
        if candidate.is_dir():
            return candidate

    directory = Path(__file__).parent.resolve()
    while True:
        if any((directory / marker).exists() for marker in _PROJECT_MARKERS):
            return directory
        parent = directory.parent
        if parent == directory:
            break
        directory = parent

    raise FileNotFoundError(
        f"未找到项目根目录（需包含 {_PROJECT_MARKERS} 之一），"
        "且未设置环境变量 PROJECT_ROOT"
    )


# --------------------------------------------------------------------------- #
# 路径常量（导入时静态计算）
# --------------------------------------------------------------------------- #
PROJECT_ROOT = get_project_root()

# 调试 / 测试样例输入（各节点 __main__ 与 pytest 共用）
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"

# var/ 下的运行时目录
VAR_DIR = PROJECT_ROOT / "var"
IMPORT_TMP_DIR = VAR_DIR / "import"
UPLOAD_TMP_DIR = VAR_DIR / "uploads"
LOG_DIR = VAR_DIR / "logs"
TMP_DIR = VAR_DIR / "tmp"


# --------------------------------------------------------------------------- #
# 路径函数
# --------------------------------------------------------------------------- #
def fixture_path(name: str) -> Path:
    """`tests/fixtures/` 下的样例文件，避免各处硬编码目录名。"""
    return FIXTURES_DIR / name


def runtime_tmp_dir() -> Path:
    """运行时临时目录（`var/tmp`），节点 `__main__` 调试产物落点。"""
    return TMP_DIR


def snapshot_path(name: str) -> str:
    """节点 `__main__` 调试快照的默认落点：`var/tmp/<name>`。"""
    return str(runtime_tmp_dir() / name)
