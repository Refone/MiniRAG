from typing import Any

MAX_STR_LEN = 20  # 字符串值最大显示长度
MAX_CONTAINER = 3  # list / dict 最多显示前 N 个
MAX_DEPTH = 5  # 最大嵌套深度
INDENT = 2  # 每层缩进
MAX_LINE_LEN = 100  # 单行最大宽度
FLOAT_PRECISION = 4  # float 保留位数


def _brief_value_str(s: str) -> str:
    """字符串值：截断 + repr"""
    if len(s) <= MAX_STR_LEN:
        return repr(s)
    return repr(s[: MAX_STR_LEN - 3] + "...")


def _brief_key_str(s: str) -> str:
    """dict 键：不截断，原样 repr"""
    return repr(s)


def _brief_scalar(obj: Any) -> str:
    if obj is None:
        return "None"
    if isinstance(obj, bool):
        return str(obj)
    if isinstance(obj, float):
        return repr(round(obj, FLOAT_PRECISION))
    if isinstance(obj, str):
        return _brief_value_str(obj)
    return repr(obj)


def brief(obj: Any, _indent: int = 0, _depth: int = 0, _seen=None) -> str:
    """把任意对象转成可打印的简短字符串。"""
    if _seen is None:
        _seen = set()

    # ---------- 标量 ----------
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return _brief_scalar(obj)

    # ---------- 深度限制 ----------
    if _depth >= MAX_DEPTH:
        return f"{type(obj).__name__}(...)"

    # ---------- 循环引用 ----------
    obj_id = id(obj)
    if obj_id in _seen:
        return "<circular>"

    if isinstance(obj, list):
        _seen.add(obj_id)
        try:
            return _brief_seq(obj, _indent, _depth, _seen)
        finally:
            _seen.discard(obj_id)

    if isinstance(obj, dict):
        _seen.add(obj_id)
        try:
            return _brief_map(obj, _indent, _depth, _seen)
        finally:
            _seen.discard(obj_id)

    # 其他对象兜底
    return _brief_value_str(repr(obj))


def _brief_seq(lst: list, indent: int, depth: int, _seen) -> str:
    if not lst:
        return "[]"

    n = len(lst)
    if n <= MAX_CONTAINER:
        items = [brief(x, indent + 1, depth + 1, _seen) for x in lst]
    else:
        items = [brief(x, indent + 1, depth + 1, _seen) for x in lst[:MAX_CONTAINER]]
        items.append(f"... (共 {n} 项)")

    return _assemble(items, indent, "[", "]")


def _brief_map(d: dict, indent: int, depth: int, _seen) -> str:
    if not d:
        return "{}"

    n = len(d)
    keys = list(d.keys())
    truncated = n > MAX_CONTAINER
    if truncated:
        keys = keys[:MAX_CONTAINER]

    items = []
    for k in keys:
        # 键不截断；非 str 键按值处理
        k_str = (
            _brief_key_str(k)
            if isinstance(k, str)
            else brief(k, indent + 1, depth + 1, _seen)
        )
        v_str = brief(d[k], indent + 1, depth + 1, _seen)
        items.append(f"{k_str}: {v_str}")

    if truncated:
        items.append(f"... (共 {n} 项)")

    return _assemble(items, indent, "{", "}")


def _assemble(items: list, indent: int, open_b: str, close_b: str) -> str:
    """单行放得下就单行，否则按 INDENT 缩进多行。"""
    single = open_b + ", ".join(items) + close_b

    if "\n" not in single and len(single) + indent * INDENT <= MAX_LINE_LEN:
        return single

    inner_pad = " " * ((indent + 1) * INDENT)
    outer_pad = " " * (indent * INDENT)
    body = inner_pad + (",\n" + inner_pad).join(items)
    return open_b + "\n" + body + "\n" + outer_pad + close_b
