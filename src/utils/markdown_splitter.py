
import copy
import re
from typing import TypedDict

from chunkana import ChunkConfig, chunk_markdown
from langchain_text_splitters import RecursiveCharacterTextSplitter

class Chunk(TypedDict):
    content: str
    level: int
    title_stack: list[str | None]

_TITLE_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_CODE_RE = re.compile(r'^[ \t]{0,3}(`{3,}|~{3,})')

# 行内 Markdown 语法（标题会同时进入 title_stack / 前端卡片头 / 向量化文本，
# 原始语法标记会让 UI 直接显示 **、` 等符号，需在此剥掉）
_INLINE_IMG_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")  # 图片 -> 保留 alt 文本
_INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")  # 链接 -> 保留文字
_INLINE_CODE_RE = re.compile(r"`+([^`]*)`+")  # 行内代码 -> 保留内容
_INLINE_STRONG_RE = re.compile(
    r"(?<![A-Za-z0-9])(\*\*|__)(?=\S)(.+?)(?<=\S)\1(?![A-Za-z0-9])"
)  # **加粗** / __加粗__（CJK 紧邻时仍生效，不误伤 snake_case 标识符）
_INLINE_EM_RE = re.compile(
    r"(?<![A-Za-z0-9])(\*|_)(?=\S)(.+?)(?<=\S)\1(?![A-Za-z0-9])"
)  # *斜体* / _斜体_
_INLINE_DEL_RE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")  # ~~删除线~~
_INLINE_HTML_RE = re.compile(r"<[^>]+>")  # 行内 HTML 标签


def strip_inline_markdown(text: str) -> str:
    """去掉标题文本中的行内 Markdown 语法，只保留纯文本。

    例如 ``**省略指向 `END` 的边**`` -> ``省略指向 END 的边``。
    只影响 title_stack 的展示与向量化，不改动原文 content。
    """
    text = _INLINE_IMG_RE.sub(r"\1", text)
    text = _INLINE_LINK_RE.sub(r"\1", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    text = _INLINE_STRONG_RE.sub(r"\2", text)
    text = _INLINE_EM_RE.sub(r"\2", text)
    text = _INLINE_DEL_RE.sub(r"\1", text)
    text = _INLINE_HTML_RE.sub("", text)
    return text.strip()

def markdown_split_by_title(
    md_content:str,
    ) -> list[Chunk]:
    chunk_list = []

    md_lines = md_content.splitlines()  # 将内容按行分割
    current_title:list[str | None] = []
    current_level = 0
    current_content_lines:list[str] = []
    is_code = False

    for line_num, line in enumerate(md_lines):
        # 跳过空行
        if not line.strip():
            # 为不破坏 md 结构，仍然把空行加入 current_content_lines
            current_content_lines.append(line)
            continue

        # 代码行不分块，整块吞下
        if _CODE_RE.match(line):
            is_code = not is_code
            current_content_lines.append(line)
            continue

        if is_code:
            current_content_lines.append(line)
            continue

        # 判断当前行是正文还是标题
        title_match = _TITLE_RE.match(line)
        if title_match:
        # 当前行是标题
            if current_content_lines:
                # 之前 content 中有内容，这是一个新块的开始
                # 处理之前的 block
                last_content = "\n".join(current_content_lines).strip()
                last_level = current_level
                last_chunk = Chunk(
                    content=last_content,
                    level=last_level,
                    title_stack=copy.deepcopy(current_title),
                )
                if last_content:  # 只有当内容不为空时才加入 chunk_list
                    chunk_list.append(last_chunk)
            # 重置当前的状态
            current_level = len(title_match.group(1))
            current_content_lines.clear()
            # current_content_lines.append(line)  # 把标题本身也加入到当前内容中
            heading_text = strip_inline_markdown(title_match.group(2))
            # title_stack 按下标对齐标题层级: 下标 i 对应第 i+1 级标题。
            # 缺失的层级用 None 占位，同级标题替换而不是追加，深于当前层级的旧标题要裁掉。
            while len(current_title) < current_level:
                current_title.append(None)
            current_title[current_level - 1] = heading_text
            del current_title[current_level:]
            continue

        else:
        # 当前行是正文
            current_content_lines.append(line)

    if current_content_lines:
        last_content = "\n".join(current_content_lines).strip()
        last_level = current_level
        last_chunk = Chunk(
            content=last_content,
            level=last_level,
            title_stack=copy.deepcopy(current_title),
        )
        if last_content:  # 只有当内容不为空时才加入 chunk_list
            chunk_list.append(last_chunk)

    return chunk_list

def _split_oversized_chunks(
    chunk_list: list[Chunk],
    max_chunk_size: int,
    min_chunk_size: int,
    overlap_size: int) -> list[Chunk]:

    result_chunks: list[Chunk] = []

    for chunk in chunk_list:
        if len(chunk["content"]) > max_chunk_size:
        # 块过长，需要拆分
            config = ChunkConfig(
                max_chunk_size=max_chunk_size,
                min_chunk_size=min_chunk_size,
                overlap_size=overlap_size,
            )

            list_chunks = chunk_markdown(chunk["content"], config)

            for c in list_chunks:
                result_chunks.append(Chunk(
                    content=c.content,
                    level=chunk["level"],
                    title_stack=copy.deepcopy(chunk["title_stack"]),
                ))
        else:
            result_chunks.append(chunk)

    return result_chunks

def split_markdown(md_content: str,
                   max_chunk_size: int,
                   min_chunk_size: int,
                   overlap_size: int,
                   ) -> list[Chunk]:
    # 1. 首先按照标题层级切分
    chunk_list = markdown_split_by_title(md_content)

    # 2. 超长块继续切分, 同时保持 chunk 顺序不变
    chunk_list = _split_oversized_chunks(chunk_list, max_chunk_size, min_chunk_size, overlap_size)

    return chunk_list

if __name__ == "__main__":
    import json

    from rich import print as rprint

    from utils.path_utils import fixture_path, runtime_tmp_dir
    md_content = ""
    md_path = fixture_path("hello-agent.md")
    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    chunk_list = split_markdown(
        md_content,
        max_chunk_size=800,
        min_chunk_size=80,
        overlap_size=50,
        )

    for chunk in chunk_list:
        rprint(chunk)

    tmp_dir = runtime_tmp_dir()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    output_path = tmp_dir / "chunks.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunk_list, f, ensure_ascii=False, indent=2)
    rprint(f"[green]已写入 {len(chunk_list)} 个 chunk 到 {output_path}[/green]")