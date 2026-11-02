#!/usr/bin/env python3
"""校验 README「目录约定」表与 git 入库布局 / .gitignore 是否一致。

README 是目录契约: 结构树和约定表写的是什么, 入库布局就得是什么。
本脚本检查三件事:

1. 表里标 ✅ 的路径必须真实存在;
2. 表里标 ❌ 的路径必须被 .gitignore 命中 (不能误入库);
3. git 索引中出现的每个顶层目录 (隐藏目录除外) 都必须出现在表里,
   不能有「黑户」目录。工作区里未跟踪 / 被 ignore 的本地目录不算,
   否则本地临时文件会挡住与它无关的提交。

用法: python tools/check_layout.py
退出码: 0 = 一致, 1 = 有漂移 (输出具体差异)
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
SECTION = "## 目录约定"

# | `src/` | ✅ | 后端源码 ... |
ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(✅|❌)\s*\|")


def parse_table(text: str) -> dict[str, bool]:
    """解析约定表 -> {路径: 是否入库}。"""
    rows: dict[str, bool] = {}
    in_section = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_section = line.strip() == SECTION
            continue
        if in_section:
            m = ROW.match(line.strip())
            if m:
                rows[m.group(1).rstrip("/")] = m.group(2) == "✅"
    return rows


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
    """路径是否被 .gitignore 命中 (不要求路径存在)。"""
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "-q", path],
            capture_output=True,
        )
        return result.returncode == 0
    except FileNotFoundError:  # 没有 git 就跳过该维度
        return True


def main() -> int:
    if not README.is_file():
        print(f"[FAIL] 找不到 {README}")
        return 1

    table = parse_table(README.read_text(encoding="utf-8"))
    if not table:
        print(f"[FAIL] README 里没解析到「{SECTION}」表格 (表头/格式变了?)")
        return 1

    errors: list[str] = []

    for path, tracked in sorted(table.items()):
        full = ROOT / path
        if tracked and not full.exists():
            errors.append(f"[缺目录] 约定表标为入库, 但不存在: {path}/")
        if not tracked and not git_ignored(path):
            errors.append(
                f"[漏 ignore] 约定表标为不入库, 但 .gitignore 没命中: {path}/"
            )

    top_dirs = sorted(
        p.name
        for p in ROOT.iterdir()
        if p.is_dir() and not p.name.startswith(".") and git_indexed(p.name)
    )
    for name in top_dirs:
        if not any(entry == name or entry.startswith(f"{name}/") for entry in table):
            errors.append(f"[未登记] 顶层目录未出现在约定表: {name}/")

    if errors:
        print("目录契约不一致:")
        for err in errors:
            print(f"  - {err}")
        print(f"\n请同步修改 README 的结构树与「{SECTION}」表, 或修正磁盘布局。")
        return 1

    print(f"目录契约一致: {len(table)} 条约定, {len(top_dirs)} 个顶层目录 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
