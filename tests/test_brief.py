"""日志/调试用的简短格式化（brief / brief_list / brief_dict）。

阶段 3 会把 `brief_utils.brief` 与 `logging_utils.brief_list/brief_dict`
合并进同一个模块，本文件是"合并前后输出一致"的验证。
"""

from common.utils.brief import brief, brief_dict, brief_list


def test_brief_scalar_uses_repr():
    assert brief("short") == "'short'"
    assert brief(3.14159) == "3.1416"  # FLOAT_PRECISION = 4
    assert brief(None) == "None"
    assert brief(True) == "True"


def test_brief_truncates_long_string():
    # MAX_STR_LEN = 20：保留前 17 个字符 + "..."
    assert brief("x" * 30) == "'" + "x" * 17 + "...'"


def test_brief_list_truncation():
    assert brief_list([1, 2]) == "[1, 2]"
    assert brief_list([]) == "[]"
    assert brief_list(list(range(10))) == "[0, 1, 2, ..., 7, 8, 9]"


def test_brief_dict_truncation():
    assert brief_dict({}) == "{}"
    assert brief_dict({"a": 1}) == "{'a': 1}"

    full = brief_dict({str(i): i for i in range(10)})
    assert full.startswith("{0: 0, 1: 1, 2: 2, ...")
    assert full.endswith("7: 7, 8: 8, 9: 9}")


def test_brief_nested_container():
    out = brief({"k": [1, 2, 3]})

    assert "k" in out
    assert "1" in out
