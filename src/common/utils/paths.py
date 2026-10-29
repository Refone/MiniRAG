"""项目根目录与样例文件定位（零项目内依赖）。

`PROJECT_ROOT` 的定位策略：
1. 环境变量 `PROJECT_ROOT` 优先（生产 / 容器 / CI 显式指定）；
2. 否则从本文件位置向上找"项目标记"（pyproject.toml / uv.lock / .env）。

只放"纯路径计算"，不 import 任何项目内模块——需要 `ENV_CONFIG` 的路径函数
（`runtime_dir` / `snapshot_path`）在 `common.config.runtime_paths`。
"""

import os
from pathlib import Path

# 项目根目录的“地标”: 命中任意一项即认为是根目录
_PROJECT_MARKERS = ("pyproject.toml", "uv.lock", ".env")


def _iter_ancestors(start: Path):
    """从 start 开始逐级向上产出目录, 直到文件系统根目录 (含) 。"""
    current = start.resolve()
    while True:
        yield current
        parent = current.parent
        if parent == current:  # 到达根目录, 父目录等于自己
            return
        current = parent


def get_project_root() -> Path:
    # 1. 环境变量优先: 生产 / 容器 / CI 显式指定
    env_root = os.getenv("PROJECT_ROOT")
    if env_root:
        candidate = Path(env_root).resolve()
        if candidate.is_dir():
            return candidate

    # 2. 从本文件位置向上查找项目标记
    start = Path(__file__).resolve().parent
    for directory in _iter_ancestors(start):
        if any((directory / m).exists() for m in _PROJECT_MARKERS):
            return directory

    raise FileNotFoundError(
        f"未找到项目根目录 (需包含 {_PROJECT_MARKERS} 之一) , "
        "且未设置环境变量 PROJECT_ROOT"
    )


PROJECT_ROOT = get_project_root()

# 调试 / 测试样例输入 (各节点 __main__ 与 pytest 共用)
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"


def fixture_path(name: str) -> Path:
    """tests/fixtures/ 下的样例文件, 避免各处硬编码目录名。"""
    return FIXTURES_DIR / name


if __name__ == "__main__":
    print(get_project_root())
    print(PROJECT_ROOT)
    print(FIXTURES_DIR)
