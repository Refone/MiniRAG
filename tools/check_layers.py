#!/usr/bin/env python3
"""校验分层依赖（AGENTS.md「代码结构规则」的可执行版本）。

两类规则：

1. 顶层 4 层：`api → service → graphs → common`，只允许向下依赖；
   只有 `api/` 允许 import fastapi / starlette。
2. `common` 内部 5 个 tier：只允许依赖更低 tier；同 tier 的不同子包
   之间禁止互相依赖（同一子包内部自由）。

跳过 `if __name__ == "__main__":` 与 `if TYPE_CHECKING:` 块（脚本 / 类型专用）。

用法:
    python tools/check_layers.py          # 校验，违规时退出码 1
    python tools/check_layers.py --list   # 打印每个模块的层级归属
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

LAYERS = ("api", "service", "graphs", "common")

# 顶层依赖白名单：key 可 import 的层
ALLOWED = {
    "api": {"api", "service", "graphs", "common"},
    "service": {"service", "graphs", "common"},
    "graphs": {"graphs", "common"},
    "common": {"common"},
}

# 只有这些层可以 import Web 框架
WEB_ALLOWED_LAYERS = {"api"}
WEB_MODULES = {"fastapi", "starlette"}

# common 内部 tier（键为 src/common/<key>... 的第一段）
COMMON_TIERS = {
    "utils": 0,
    "prompt": 0,
    "config": 1,
    "logging": 2,
    "model": 2,
    "client": 3,
    "events": 3,
    "store": 4,
}
COMMON_PACKAGE_TIER = -1  # src/common/__init__.py


def module_info(path: Path) -> tuple[str, list[str]]:
    """返回 (模块名, 层级路径两部分)，例如 common/utils/brief.py -> ("common.utils.brief", ...)."""
    rel = path.relative_to(SRC).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts), parts


def layer_of(parts: list[str]) -> str | None:
    return parts[0] if parts and parts[0] in LAYERS else None


def common_key(parts: list[str]) -> str | None:
    """`common` 下第一段名字（子包或模块），`common/__init__.py` 返回 None。"""
    if len(parts) < 2:
        return None
    return parts[1]


def common_tier(parts: list[str]) -> int:
    key = common_key(parts)
    if key is None:
        return COMMON_PACKAGE_TIER
    return COMMON_TIERS.get(key, 99)  # 未登记 -> 99，会触发违规提示


def iter_imports(tree: ast.Module) -> list[tuple[int, str]]:
    """收集需校验的 import（跳过 __main__ / TYPE_CHECKING 块）。"""

    def walk(body: list[ast.stmt]):
        for node in body:
            if isinstance(node, ast.If) and _is_exempt_block(node):
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    yield node.lineno, alias.name
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # 相对 import 不在本规则范围
                    continue
                yield node.lineno, node.module or ""
            elif isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                # 不应有顶层函数再 import 项目模块的写法，但函数体内的
                # 延迟 import 也计入依赖（它仍是运行时依赖）
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Import):
                        for alias in sub.names:
                            yield sub.lineno, alias.name
                    elif isinstance(sub, ast.ImportFrom) and not sub.level:
                        yield sub.lineno, sub.module or ""
            elif isinstance(node, (ast.For, ast.While, ast.With, ast.Try)):
                yield from walk(node.body)

    yield from walk(tree.body)


def _is_exempt_block(node: ast.If) -> bool:
    src = ast.unparse(node.test)
    return "__name__" in src or "TYPE_CHECKING" in src


def check() -> list[str]:
    errors: list[str] = []
    if not SRC.is_dir():
        return [f"找不到源码目录: {SRC}"]

    for path in sorted(SRC.rglob("*.py")):
        mod, parts = module_info(path)
        layer = layer_of(parts)
        if layer is None:
            continue
        rel = path.relative_to(ROOT)

        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # pragma: no cover - 语法错误交给 ruff/pytest
            errors.append(f"{rel}: 无法解析 ({exc})")
            continue

        for lineno, imported in iter_imports(tree):
            top = imported.split(".")[0]

            # 1) Web 框架白名单
            if top in WEB_MODULES and layer not in WEB_ALLOWED_LAYERS:
                errors.append(
                    f"{rel}:{lineno}: {layer}/ 不允许 import {top}"
                    f"（仅 {'/'.join(sorted(WEB_ALLOWED_LAYERS))}/ 可用）"
                )
                continue

            # 2) 顶层 4 层方向
            if top in LAYERS:
                if top not in ALLOWED[layer]:
                    errors.append(
                        f"{rel}:{lineno}: {layer}/ 不允许 import {top}/"
                        f"（允许: {', '.join(sorted(ALLOWED[layer]))}）"
                    )
                    continue

                # 3) common 内部 tier（含包内同层判断）
                if top == "common" and layer == "common":
                    target_parts = imported.split(".")
                    src_tier = common_tier(parts)
                    dst_tier = common_tier(target_parts)
                    if dst_tier == 99:
                        errors.append(
                            f"{rel}:{lineno}: common.{common_key(target_parts)} "
                            f"未在 COMMON_TIERS 登记 tier"
                        )
                    elif dst_tier >= src_tier and dst_tier != COMMON_PACKAGE_TIER:
                        same_subpackage = common_key(parts) == common_key(target_parts)
                        if not same_subpackage:
                            errors.append(
                                f"{rel}:{lineno}: common tier 违规 "
                                f"T{src_tier} -> T{dst_tier}（{imported}）"
                                f"：只允许依赖更低 tier，同 tier 仅限同子包"
                            )

    return errors


def main(argv: list[str]) -> int:
    if "--list" in argv:
        rows = []
        for path in sorted(SRC.rglob("*.py")):
            mod, parts = module_info(path)
            layer = layer_of(parts)
            if layer is None:
                continue
            tier = f"T{common_tier(parts)}" if layer == "common" else "-"
            rows.append(f"{tier:>3}  {mod}")
        print("\n".join(rows))
        return 0

    errors = check()
    if errors:
        print(f"分层校验失败（{len(errors)} 处）：")
        for err in errors:
            print(f"  - {err}")
        print("\n规则见 AGENTS.md「代码结构规则」。")
        return 1

    print("分层校验通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
