"""运行时目录（依赖 `ENV_CONFIG`，所以不在 `common.utils`）。

`common.utils.paths` 只算静态路径；这里的目录来自 `.env`（`OUTPUT_DIR_*`），
两者按 tier 分开：paths 是 T0，本模块是 T1。
"""

from pathlib import Path

from common.config.env_config import ENV_CONFIG


def runtime_tmp_dir() -> Path:
    """运行时临时目录 (默认 var/tmp)。"""
    return Path(ENV_CONFIG.output_dir.tmp_dir)


def snapshot_path(name: str) -> str:
    """节点 __main__ 调试快照的默认落点 (var/tmp/<name>)。"""
    return str(runtime_tmp_dir() / name)
