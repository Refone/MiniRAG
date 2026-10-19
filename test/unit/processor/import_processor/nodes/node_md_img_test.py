"""单元测试: src/processor/import_processor/nodes/node_md_img.py

被测对象:
    _rewrite_img_tag                 <img> 标签改写 (src/width/height/alt)
    step_5_md_content_image_replace  替换 Markdown 中的图片标记并写入尺寸

说明:
    被测函数均为纯函数, 不依赖 MinIO / VLM。
    尺寸已知时写入 Markdown title 属性 ("宽x高") 或 <img> 的 width/height 属性,
    供查询侧 node_answer_output.step_4_collect_images 过滤 icon 小图;
    尺寸未知 (<=0) 时不写尺寸信息, 查询侧兜底保留。
"""

from __future__ import annotations

import html
import importlib

from processor.import_processor.nodes.node_md_img import (
    _rewrite_img_tag,
    step_5_md_content_image_replace,
)

# 注意: 不能用 `from processor.import_processor.nodes import node_md_img as mod` ——
# 包 __init__ 里 `from .node_md_img import node_md_img` 会用同名函数覆盖子模块属性。
mod = importlib.import_module("processor.import_processor.nodes.node_md_img")

SUMMARY_A = "接口接线图"
SUMMARY_B = "页面 <布局> & 图示"
URL_A = "http://minio/x/a.png"
URL_B = "http://minio/x/b.png"


# --------------------------------------------------------------------------- #
# _rewrite_img_tag
# --------------------------------------------------------------------------- #
def test_rewrite_img_tag_with_size_overrides_old_attrs():
    tag = '<img src="images/a.png" width="10" height="10" alt="旧描述">'

    result = _rewrite_img_tag(tag, SUMMARY_A, URL_A, 800, 600)

    assert f'src="{URL_A}"' in result
    assert 'width="800"' in result
    assert 'height="600"' in result
    assert f'alt="{SUMMARY_A}"' in result
    assert 'width="10"' not in result
    assert "旧描述" not in result


def test_rewrite_img_tag_unknown_size_writes_no_size_attrs():
    tag = '<img src="images/b.png" width="10" height="10">'

    result = _rewrite_img_tag(tag, SUMMARY_B, URL_B, 0, 0)

    assert f'src="{URL_B}"' in result
    assert "width=" not in result
    assert "height=" not in result
    # alt 文本中的特殊字符应被转义
    assert f'alt="{html.escape(SUMMARY_B, quote=True)}"' in result


def test_rewrite_img_tag_self_closing():
    tag = '<img src="images/a.png"/>'

    result = _rewrite_img_tag(tag, SUMMARY_A, URL_A, 200, 100)

    assert result.endswith("/>")
    assert 'width="200"' in result
    assert 'height="100"' in result


def test_rewrite_img_tag_single_quoted_src():
    tag = "<img src='images/a.png'>"

    result = _rewrite_img_tag(tag, SUMMARY_A, URL_A, 32, 32)

    assert f'src="{URL_A}"' in result
    assert 'width="32"' in result


# --------------------------------------------------------------------------- #
# step_5_md_content_image_replace
# --------------------------------------------------------------------------- #
def test_replace_markdown_syntax_with_size_title():
    md = "正文 ![x](images/a.png) 结尾"

    result = step_5_md_content_image_replace(
        md,
        {"a.png": SUMMARY_A},
        {"a.png": URL_A},
        {"a.png": (800, 600)},
    )

    assert result == f'正文 ![{SUMMARY_A}]({URL_A} "800x600") 结尾'


def test_replace_markdown_syntax_unknown_size_no_title():
    md = "正文 ![x](images/a.png) 结尾"

    result = step_5_md_content_image_replace(
        md,
        {"a.png": SUMMARY_A},
        {"a.png": URL_A},
        {"a.png": (0, 0)},
    )

    assert result == f"正文 ![{SUMMARY_A}]({URL_A}) 结尾"


def test_replace_img_tag_with_size_attrs():
    md = '正文 <img src="images/b.png" width="1" height="1"> 结尾'

    result = step_5_md_content_image_replace(
        md,
        {"b.png": SUMMARY_B},
        {"b.png": URL_B},
        {"b.png": (1200, 800)},
    )

    assert (
        f'width="1200" height="800" alt="{html.escape(SUMMARY_B, quote=True)}"'
        in result
    )
    assert f'src="{URL_B}"' in result
    assert 'width="1"' not in result


def test_replace_keeps_unrelated_content():
    md = "# 标题\n无图片的段落\n"

    result = step_5_md_content_image_replace(
        md,
        {"a.png": SUMMARY_A},
        {"a.png": URL_A},
        {"a.png": (800, 600)},
    )

    assert result == md


def test_replace_missing_url_skips_image():
    md = "正文 ![x](images/a.png) 结尾"

    result = step_5_md_content_image_replace(
        md,
        {"a.png": SUMMARY_A},
        {},  # 上传失败, 无 URL
        {"a.png": (800, 600)},
    )

    # 无 URL 时不替换, 保留原样
    assert result == md
