"""Markdown 切分：标题栈对齐、代码块保护、行内语法剥离。

这些用例是阶段 3（utils → common 大搬家）"行为不变"的机器验证：
搬移只该改 import 路径，断言必须原样通过。
"""

from common.utils.markdown_splitter import split_markdown, strip_inline_markdown


def test_title_stack_alignment(sample_markdown):
    chunks = split_markdown(sample_markdown, 1000, 200, 100)

    assert [c["level"] for c in chunks] == [2, 3]
    assert chunks[0]["title_stack"] == [None, "一级"]
    assert chunks[0]["content"] == "正文 A"
    assert chunks[1]["title_stack"] == [None, "一级", "二级"]
    assert chunks[1]["content"] == "正文 B"


def test_missing_level_uses_none_placeholder():
    chunks = split_markdown("### 三级\n正文\n", 1000, 200, 100)

    assert len(chunks) == 1
    assert chunks[0]["level"] == 3
    # 缺失的一、二级用 None 占位，下标与标题层级一一对应
    assert chunks[0]["title_stack"] == [None, None, "三级"]


def test_same_level_replaces_not_appends():
    md = "## A\n正文 1\n\n## B\n正文 2\n"
    chunks = split_markdown(md, 1000, 200, 100)

    assert [c["title_stack"] for c in chunks] == [[None, "A"], [None, "B"]]


def test_code_fence_is_not_split():
    md = "# 标题\n\n```\n# 不是标题\n```\n\n正文\n"
    chunks = split_markdown(md, 1000, 200, 100)

    assert len(chunks) == 1
    assert chunks[0]["level"] == 1
    assert chunks[0]["title_stack"] == ["标题"]
    assert "# 不是标题" in chunks[0]["content"]


def test_oversized_chunk_keeps_title_stack():
    # 空行分段的长正文才会被 chunkana 二次切分（纯无标点长串不会切）
    body = "\n\n".join(["这是一个用于测试切分的段落"] * 80)
    md = f"## 长节\n{body}\n"
    chunks = split_markdown(md, 1000, 200, 100)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk["level"] == 2
        assert chunk["title_stack"] == [None, "长节"]


def test_strip_inline_markdown():
    raw = "**加粗** 与 `code` 与 [链接](http://x) 与 ![图](y)"
    assert strip_inline_markdown(raw) == "加粗 与 code 与 链接 与 图"


def test_empty_content_yields_no_chunk():
    assert split_markdown("# 只有标题\n", 1000, 200, 100) == []
