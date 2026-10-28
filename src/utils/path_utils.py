import os
from pathlib import Path

def from_project_root(path: str | Path) -> Path:
    return get_project_root() / path

def get_path_dir(ps:int = 0)->Path:
    """
    pathlib.Path 提供了 parents 属性, 这是一个有序的路径上级目录迭代器, 直接通过索引取值就能快速获取「上 N 级目录」, 完美解决多层 .parent 繁琐的问题, 这也是官方推荐的简化写法！
    核心规则: parents[N] 索引对应「向上的层级数」
    parents[0] → 等价于 .parent (当前路径的上 1 级目录)
    parents[1] → 等价于 .parent.parent (当前路径的上 2 级目录)
    parents[2] → 等价于 .parent.parent.parent (当前路径的上 3 级目录)
    以此类推, parents[N] → 直接获取上 N+1 级目录, 索引越⼤, 层级越靠上
    :param ps:
    :return:
    """
    dir_path = Path(__file__).parents[ps]
    return dir_path

# 项目根目录的“地标”: 命中任意一项即认为是根目录
_PROJECT_MARKERS = ("pyproject.toml", "uv.lock", ".env")

def _iter_ancestors(start: Path):
    """从 start 开始逐级向上产出目录, 直到文件系统根目录 (含) 。"""
    current = start.resolve()
    while True:
        yield current
        parent = current.parent
        if parent == current:      # 到达根目录, 父目录等于自己
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

def get_src_root() -> Path:
    src = get_project_root() / "src"
    if not src.is_dir():
        raise FileNotFoundError(f"未找到 src 目录: {src}")
    return src

PROJECT_ROOT = get_project_root()
SRC_ROOT = get_src_root()

# 调试 / 测试样例输入 (各节点 __main__ 与将来 pytest 共用)
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"


def fixture_path(name: str) -> Path:
    """tests/fixtures/ 下的样例文件, 避免各处硬编码目录名。"""
    return FIXTURES_DIR / name


def runtime_tmp_dir() -> Path:
    """运行时临时目录 (默认 var/tmp)。

    延迟导入 env_config: 它在模块级 import 本模块的 PROJECT_ROOT,
    这里若在模块级反向 import 会形成循环。
    """
    from common.config.env_config import ENV_CONFIG

    return Path(ENV_CONFIG.output_dir.tmp_dir)


def snapshot_path(name: str) -> str:
    """节点 __main__ 调试快照的默认落点 (var/tmp/<name>)。"""
    return str(runtime_tmp_dir() / name)


if __name__ == "__main__":
    print(get_project_root())
    print(get_src_root())
    print(get_path_dir(0))
    print(get_path_dir(1))
    print(get_path_dir(2))