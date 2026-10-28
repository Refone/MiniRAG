import re
from functools import partial
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

import requests

from common.config.env_config import ENV_CONFIG
from utils.logging_utils import logger
from utils.node_utils import step_log, trace_node
from graphs.import_graph.import_graph_state import ImportGraphState

# 在线图片地址以 http/https 开头
_HTTP_PREFIXES = ("http://", "https://")

# Markdown 图片语法: ![alt](url "title")
# 注意: 图片地址可能包含空格 (如 Obsidian/Notion 导出的文件名),
# 不能按 \s 截断; 地址后可跟 "title"/'title'。捕获组结构必须保持:
# 组1=前缀, 组2=url (_collect_online_image_urls / _replace_src 依赖)。
_MARKDOWN_IMAGE_RE = re.compile(
    r"(!\[[^\]]*\]\([ \t]*)([^)\n]*?)(?:[ \t]+(?:\"[^\"]*\"|'[^']*'))?[ \t]*\)"
)

# HTML 图片语法: <img src="url" ...>
_IMG_TAG_RE = re.compile(
    r"(<img\b[^>]*?\bsrc\s*=\s*[\"'])([^\"']+)([\"'][^>]*>)", re.IGNORECASE
)


@step_log(desc="验证与数据获取")
def step_1_validate_and_setup(state: ImportGraphState) -> tuple[Path, str]:
    origin_file = state.get("origin_file_path")
    if not origin_file:
        raise ValueError(f"原始文档路径为空: {origin_file!r}")

    file_title = state.get("file_title")
    if not state.get("file_title"):
        raise ValueError(f"文档标题为空: {state!r}")

    origin_md = Path(origin_file)
    return origin_md, file_title


@step_log(desc="构建 Markdown 目录")
def step_2_build_md_dir(origin_md: Path, file_title: str) -> Path:
    # 在 output/import 文件夹中创建 md 目录:
    # output/import/<file_title>/
    # ├── images/
    # └── <file_title>.md
    md_dir = Path(ENV_CONFIG.output_dir.import_tmp_dir) / file_title
    md_dir.mkdir(parents=True, exist_ok=True)
    images_dir = md_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # 把 origin_md 复制到 md_dir 下，并命名为 <file_title>.md
    target_md = md_dir / f"{file_title}.md"
    target_md.write_text(origin_md.read_text(), encoding="utf-8")
    return target_md


def _is_online_url(url: str) -> bool:
    """判断图片地址是否为在线地址 (http/https)。"""
    return url.lower().startswith(_HTTP_PREFIXES)


def _normalize_url(url: str) -> str:
    """去掉 Markdown 图片语法中可能包裹地址的尖括号, 如 <https://...>。"""
    if url.startswith("<") and url.endswith(">"):
        return url[1:-1]
    return url


def _collect_online_image_urls(md_text: str) -> list[str]:
    """按出现顺序收集 md 文本中所有去重后的在线图片地址。"""
    urls: list[str] = []
    seen: set[str] = set()
    for pattern in (_MARKDOWN_IMAGE_RE, _IMG_TAG_RE):
        for match in pattern.finditer(md_text):
            url = _normalize_url(match.group(2))
            if _is_online_url(url) and url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def _build_local_filename(url: str, index: int, used_names: set[str]) -> str:
    """根据 url 生成本地文件名, 并在冲突时追加序号以保证唯一。"""
    name = PurePosixPath(unquote(urlsplit(url).path)).name
    if not name:
        name = f"image_{index}"
    if name in used_names:
        stem = PurePosixPath(name).stem
        suffix = PurePosixPath(name).suffix
        name = f"{stem}_{index}{suffix}"
    used_names.add(name)
    return name


def _download_image(url: str, images_dir: Path, filename: str) -> None:
    """下载单张在线图片到 images_dir/filename, 网络失败时直接抛出异常。"""
    try:
        resp = requests.get(url)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise requests.RequestException(f"下载在线图片失败: {url}") from e

    (images_dir / filename).write_bytes(resp.content)
    logger.debug(f"下载在线图片成功: {url} -> {filename}")


def _download_online_images(urls: list[str], images_dir: Path) -> dict[str, str]:
    """下载所有在线图片, 返回 url -> md 内相对路径 的映射。"""
    url_to_local: dict[str, str] = {}
    used_names: set[str] = set()
    for index, url in enumerate(urls):
        filename = _build_local_filename(url, index, used_names)
        _download_image(url, images_dir, filename)
        url_to_local[url] = str(PurePosixPath("images") / filename)
    return url_to_local


def _replace_src(match: re.Match, url_to_local: dict[str, str]) -> str:
    """re.sub 回调: 把匹配到的 url 替换为本地相对路径 (不在映射中则原样返回)。"""
    url = _normalize_url(match.group(2))
    local = url_to_local.get(url)
    if local is None:
        return match.group(0)

    full = match.group(0)
    start = match.start(2) - match.start()
    end = match.end(2) - match.start()
    return full[:start] + local + full[end:]


def _replace_image_urls(md_text: str, url_to_local: dict[str, str]) -> str:
    """把 md 文本中的在线图片地址替换为本地相对路径。"""
    repl = partial(_replace_src, url_to_local=url_to_local)
    return _IMG_TAG_RE.sub(repl, _MARKDOWN_IMAGE_RE.sub(repl, md_text))


@step_log(desc="下载在线图片")
def step_3_download_online_images(md_path: Path) -> dict[str, str]:
    """
    下载 md 中引用的在线图片到本地 images/ 目录。

    支持两种图片语法:
        - Markdown: ![alt](url)
        - HTML:     <img src="url" ...>
    网络下载失败时直接抛出异常。

    返回: 在线图片 url -> md 内相对路径 的映射。
    """
    md_text = md_path.read_text(encoding="utf-8")
    images_dir = md_path.parent / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    urls = _collect_online_image_urls(md_text)
    return _download_online_images(urls, images_dir)


@step_log(desc="替换为本地图片地址")
def step_4_replace_image_urls(md_path: Path, url_to_local: dict[str, str]) -> None:
    """把 md 文本中的在线图片地址替换为本地相对路径, 并写回文件。"""
    md_text = md_path.read_text(encoding="utf-8")
    new_text = _replace_image_urls(md_text, url_to_local)
    md_path.write_text(new_text, encoding="utf-8")


@trace_node(desc="处理 Markdown 独文件", need_push=True)
def node_process_standalone_md(state: ImportGraphState) -> ImportGraphState:

    origin_md, file_title = step_1_validate_and_setup(state)
    logger.info(f"原始 Markdown 文件: {origin_md}, 文件标题: {file_title}")

    md_path = step_2_build_md_dir(origin_md, file_title)
    logger.info(f"Markdown 文件路径: {md_path}")

    url_to_local = step_3_download_online_images(md_path)
    logger.info(f"图片 URL 映射: {url_to_local}")

    step_4_replace_image_urls(md_path, url_to_local)
    logger.info(f"Downloaded {len(url_to_local)} images for markdown file: {md_path}")

    return {"markdown_file_path": str(md_path)}


if __name__ == "__main__":
    from rich import print as rprint
    from graphs.import_graph.import_graph_state import (
        ImportGraphState,
        create_state,
        save_state,
    )
    from utils.path_utils import fixture_path, snapshot_path

    start_state = create_state(
        task_id="test_task_start",
        file_title="hello-agent",
        origin_file_path=str(fixture_path("hello-agent.md")),
    )
    end_state = node_process_standalone_md(start_state)
    rprint(end_state)

    json_path = snapshot_path("import_02_process_standalone_md.json")
    save_state(end_state, json_path)
    logger.info(f"状态已保存: {json_path}")
