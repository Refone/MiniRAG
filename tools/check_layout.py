#!/usr/bin/env python3
"""校验顶层目录布局与 LAYOUT 约定是否一致。

目录契约写在下面的 LAYOUT 常量里, 不依赖任何文档: 代码是契约的唯一来源。
本脚本检查三件事:

1. 标为入库的路径必须真实存在;
2. 标为不入库的路径必须被 .gitignore 命中 (不能误入库);
3. git 索引中出现的每个顶层目录 (隐藏目录除外) 都必须登记在 LAYOUT,
   不能有「黑户」目录。工作区里未跟踪 / 被 ignore 的本地目录不算,
   否则本地临时文件会挡住与它无关的提交。

新增 / 删除 / 重命名顶层目录时改 LAYOUT 即可; 目录树的可读版本见
docs/architecture.md, 那里只是说明, 不参与校验。

用法: python tools/check_layout.py
退出码: 0 = 一致, 1 = 有漂移 (输出具体差异)
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 顶层路径 -> (是否入库, 定位)
LAYOUT: dict[str, tuple[bool, str]] = {
    "backend": (True, "后端源码, 以 backend/ 为 sys.path 根"),
    "frontend": (True, "前端工程 (Vite + React)"),
    "docker": (True, "编排与镜像定义"),
    "docker/volumes": (False, "容器 bind mount 数据"),
    "docs": (True, "文档与需求笔记"),
    "assets": (True, "文档配图: 架构图 / 流程动图 / 演示 GIF"),
    "tests": (True, "pytest 用例 + 样例输入"),
    "tools": (True, "非生产代码: 维护脚本与独立工具"),
    "evals": (True, "RAG 评估问题集、脚本与报告"),
    "var": (False, "运行时产物, 可随时删"),
}


def git_indexed(path: str) -> bool:
    """路径下是否有已入库或已暂存的文件 (只看 git index)。"""
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--", path],
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())
    except FileNotFoundError:  # 没有 git 时退回全量检查
        return True


def git_ignored(path: str) -> bool:
    """路径是否被 .gitignore 命中 (不要求路径存在)。

    同时试 `path` 与 `path/`：CI 全新 checkout 没有 `var/`、`docker/volumes/`
    这类空目录，而带尾斜杠的 ignore 规则只匹配目录；补一次 `path/` 才能
    在目录不存在时仍判定为已忽略。
    """
    candidates = (path,) if path.endswith("/") else (path, f"{path}/")
    try:
        for candidate in candidates:
            result = subprocess.run(
                ["git", "-C", str(ROOT), "check-ignore", "-q", candidate],
                capture_output=True,
            )
            if result.returncode == 0:
                return True
        return False
    except FileNotFoundError:  # 没有 git 就跳过该维度
        return True


def main() -> int:
    errors: list[str] = []

    for path, (tracked, _label) in sorted(LAYOUT.items()):
        full = ROOT / path
        if tracked and not full.exists():
            errors.append(f"[缺目录] LAYOUT 标为入库, 但不存在: {path}/")
        if not tracked and not git_ignored(path):
            errors.append(
                f"[漏 ignore] LAYOUT 标为不入库, 但 .gitignore 没命中: {path}/"
            )

    top_dirs = sorted(
        p.name
        for p in ROOT.iterdir()
        if p.is_dir() and not p.name.startswith(".") and git_indexed(p.name)
    )
    for name in top_dirs:
        if not any(entry == name or entry.startswith(f"{name}/") for entry in LAYOUT):
            errors.append(f"[未登记] 顶层目录未出现在 LAYOUT: {name}/")

    if errors:
        print("目录契约不一致:")
        for err in errors:
            print(f"  - {err}")
        print("\n请同步修改 tools/check_layout.py 的 LAYOUT, 或修正磁盘布局。")
        return 1

    print(f"目录契约一致: {len(LAYOUT)} 条约定, {len(top_dirs)} 个顶层目录 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
