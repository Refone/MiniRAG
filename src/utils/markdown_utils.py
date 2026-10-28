import re

from common.config.app_config import APP_CONFIG

# 一个或多个空行（允许行内只有空格/制表符）
_BLANK_LINE_RE = re.compile(r"\n[ \t]*\n")
_IMG_MD_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
# HTML <img> 标签（属性名不区分大小写）
_IMG_HTML_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
# <img> 标签中的 src 属性值（可带可不带引号，不跨标签边界）
_IMG_HTML_SRC_RE = re.compile(r"(?<=\s)src\s*=\s*[\"']?([^\"'>\s]*)", re.IGNORECASE)
_MEANINGLESS_CHARS_RE = re.compile(r"[\s\[\]()（）【】]+")


def _remove_image_marks(segment: str) -> str:
    """去掉段落中的图片标记（![]() 与 <img> 标签）。"""
    segment = _IMG_MD_RE.sub("", segment)
    return _IMG_HTML_TAG_RE.sub("", segment)


def _is_image_only(segment: str) -> bool:
    """段落去掉图片标记后若没有其它字符，则视为纯图片段落。"""
    stripped = _remove_image_marks(segment)
    stripped = _MEANINGLESS_CHARS_RE.sub("", stripped)
    return stripped == ""


def _clean_segment(segment: str) -> str:
    """去掉段落中的图片标记，并清理多余空白。"""
    return _remove_image_marks(segment).strip()


def extract_surrounding_context(
    md_content: str,
    start: int,
    end: int,
    max_chars: int = APP_CONFIG.md_image_surrounding_context_max_chars,
) -> tuple[str, str]:
    """
    提取图片标记 ![alt](url) 的前一段和后一段文本。

    规则：
    - 纯图片段落会被跳过，继续往前/往后找。
    - 混合段落（文本 + 图片）保留文本，去掉图片标记。
    - 截断时，前一段保留尾部，后一段保留头部。

    Returns:
        (prev_text, next_text)：前一段、后一段，可能为空字符串
    """
    before = md_content[:start].rstrip()
    after = md_content[end:].lstrip()

    # 前一段：从后往前找第一个有文本的段落
    prev_text = ""
    for part in reversed(_BLANK_LINE_RE.split(before)):
        part = part.strip()
        if not part or _is_image_only(part):
            continue
        cleaned = _clean_segment(part)
        if not cleaned:
            continue
        prev_text = cleaned[-max_chars:]
        break

    # 后一段：从前往后找第一个有文本的段落
    next_text = ""
    for part in _BLANK_LINE_RE.split(after):
        part = part.strip()
        if not part or _is_image_only(part):
            continue
        cleaned = _clean_segment(part)
        if not cleaned:
            continue
        next_text = cleaned[:max_chars]
        break

    return prev_text, next_text


def find_image_position(md_content: str, image_name: str) -> tuple[int, int] | None:
    """
    在 Markdown 中找到图片描述符 ![...](...) 或 <img ...> 标签的起止位置

    Args:
        md_content: Markdown 文本
        image_name: 图片文件名
    Returns:
        (start, end): 图片描述符的起止位置, 如果没找到, 返回 None
    """
    # 1. Markdown 内联语法 ![alt](url)
    md_rep = re.compile(r"\!\[.*?\]\(.*?" + re.escape(image_name) + r".*\)")
    search_match = md_rep.search(md_content)
    if search_match:
        return search_match.start(), search_match.end()

    # 2. HTML 标签语法 <img src="...">
    for tag_match in _IMG_HTML_TAG_RE.finditer(md_content):
        for src_match in _IMG_HTML_SRC_RE.finditer(tag_match.group(0)):
            if image_name in src_match.group(1):
                return tag_match.start(), tag_match.end()

    return None
