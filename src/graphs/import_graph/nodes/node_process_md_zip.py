import shutil
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

from common.config.env_config import ENV_CONFIG
from graphs.import_graph.import_graph_state import ImportGraphState
from utils.logging_utils import logger
from utils.node_utils import step_log, trace_node

# 复用 node_process_standalone_md 的图片处理工具 (图片语法正则 / 在线图片下载 /
# 地址改写), 保证「独文件 md」与「压缩包 md」两条路径行为一致。
from graphs.import_graph.nodes.node_process_standalone_md import (
    _IMG_TAG_RE,
    _MARKDOWN_IMAGE_RE,
    _build_local_filename,
    _download_image,
    _is_online_url,
    _normalize_url,
    _replace_image_urls,
)

# macOS 打包产生的垃圾目录 / 元数据文件前缀
_MACOSX_DIR = "__MACOSX"
_JUNK_FILE_PREFIX = "._"

# 支持的 md 后缀 (与 state.file_type_from_filename 保持一致)
_MD_SUFFIXES = (".md", ".markdown")

# data: 开头的地址是内嵌数据, 不是文件也不是网络图片
_DATA_PREFIX = "data:"


@step_log(desc="验证与数据获取")
def step_1_validate_and_get_data(state: ImportGraphState) -> tuple[Path, str]:
    """校验原始文件是真实存在的 zip 压缩包, 并取回文件标题。"""
    zip_file_str = state.get("origin_file_path")
    if not zip_file_str:
        raise ValueError(f"原始文档路径为空: {zip_file_str!r}")
    zip_file = Path(zip_file_str)

    if not zip_file.is_file():
        raise FileNotFoundError(f"md 压缩包不存在: {zip_file}")
    if not zipfile.is_zipfile(zip_file):
        raise ValueError(f"文件不是有效的 zip 压缩包: {zip_file}")

    file_title = state.get("file_title")
    if not file_title:
        raise ValueError(f"文档标题为空: {state!r}")

    return zip_file, file_title


@step_log(desc="解压 md 压缩包")
def step_2_unzip_md_zip(zip_file: Path, file_title: str) -> Path:
    """
    使用 shutil 解压 zip 文件到 output/import/<file_title>/ 文件夹。

    解压后目录结构取决于压缩包本身, 常见两种:
        单 md:  output/import/<file_title>/<xxx>.md + images/
        多 md:  output/import/<file_title>/<文件夹>/<xxx>.md ...

    同名文件夹已存在时先清空 (重复导入覆盖原则), 并清理 macOS 打包垃圾。
    返回解压根目录。
    """
    md_dir = Path(ENV_CONFIG.output_dir.import_tmp_dir) / file_title
    if md_dir.exists():
        shutil.rmtree(md_dir)
    md_dir.mkdir(parents=True, exist_ok=True)

    shutil.unpack_archive(zip_file, extract_dir=md_dir)

    _cleanup_macos_junk(md_dir)
    _check_no_path_escape(zip_file, md_dir)

    logger.debug(f"解压完成: {md_dir}")
    return md_dir


def _cleanup_macos_junk(md_dir: Path) -> None:
    """删除 macOS 打包产生的 __MACOSX 目录与 ._* 元数据文件。"""
    macosx_dir = md_dir / _MACOSX_DIR
    if macosx_dir.is_dir():
        shutil.rmtree(macosx_dir)

    for junk in md_dir.rglob(f"{_JUNK_FILE_PREFIX}*"):
        if junk.is_file() or junk.is_symlink():
            junk.unlink(missing_ok=True)


def _check_no_path_escape(zip_file: Path, md_dir: Path) -> None:
    """防 zip-slip: 压缩包条目 (含符号链接解析后) 不允许逃出解压根目录。

    两层检查:
    1. 解压前按条目名预检 (条目名带 ../ 时文件会写到目录外, 事后遍历发现不了)
    2. 解压后检查实际落盘结果 (符号链接按解析目标判断)
    """
    root = md_dir.resolve()
    with zipfile.ZipFile(zip_file) as zf:
        for member in zf.infolist():
            # 兼容 Windows 打包时的反斜杠路径写法
            target = (md_dir / member.filename.replace("\\", "/")).resolve()
            if not target.is_relative_to(root):
                raise RuntimeError(f"压缩包含越界路径, 已拒绝处理: {member.filename}")

    for path in md_dir.rglob("*"):
        if not path.resolve().is_relative_to(root):
            raise RuntimeError(f"压缩包含越界路径, 已拒绝处理: {path}")


def _find_md_files(md_dir: Path) -> list[Path]:
    """递归找出解压结果中的全部 md 文件, 排除 macOS 垃圾, 按相对路径排序。"""
    md_paths: list[Path] = []
    for path in md_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _MD_SUFFIXES:
            continue
        rel_parts = path.relative_to(md_dir).parts
        if _MACOSX_DIR in rel_parts:
            continue
        if any(part.startswith(_JUNK_FILE_PREFIX) for part in rel_parts):
            continue
        md_paths.append(path)
    return sorted(md_paths, key=lambda p: str(p.relative_to(md_dir)))


def _normalize_single_md(
    md_paths: list[Path], md_dir: Path, file_title: str
) -> list[Path]:
    """
    单个 md 且位于解压根目录时, 重命名为 <file_title>.md, 与独文件 md 的产物
    命名规范保持一致。嵌套目录中的单 md 保持原样 (避免破坏相对图片引用)。
    """
    if len(md_paths) != 1:
        return md_paths

    md_path = md_paths[0]
    if md_path.parent != md_dir:
        return md_paths

    target = md_dir / f"{file_title}.md"
    if md_path == target:
        return md_paths

    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    md_path.rename(target)
    logger.debug(f"单 md 压缩包: 重命名 {md_path.name} -> {target.name}")
    return [target]


def _check_unique_stems(md_paths: list[Path]) -> None:
    """
    多 md 时文件名 (不含后缀) 必须唯一: 后续流程以 md 文件名作为 file_title,
    是 Milvus / MinIO 的唯一键, 重名会互相覆盖。
    """
    stems = [path.stem for path in md_paths]
    duplicates = sorted({stem for stem in stems if stems.count(stem) > 1})
    if duplicates:
        raise RuntimeError(
            f"压缩包内存在同名 md 文件: {duplicates}, "
            f"file_title 会作为唯一键导致数据互相覆盖, 请改名后重新上传"
        )


def _collect_all_image_refs(md_text: str) -> list[str]:
    """按出现顺序收集 md 中所有图片引用 (在线 + 本地), 去重, 忽略 data: 内嵌。"""
    refs: list[str] = []
    seen: set[str] = set()
    for pattern in (_MARKDOWN_IMAGE_RE, _IMG_TAG_RE):
        for match in pattern.finditer(md_text):
            ref = _normalize_url(match.group(2))
            if ref.lower().startswith(_DATA_PREFIX):
                continue
            if ref not in seen:
                seen.add(ref)
                refs.append(ref)
    return refs


def _resolve_local_ref(md_path: Path, ref: str) -> Path:
    """把 md 内的本地图片引用解析为绝对路径 (不保证文件存在)。"""
    cleaned = unquote(ref.split("?", 1)[0].split("#", 1)[0]).replace("\\", "/")
    rel = Path(cleaned)
    if rel.is_absolute():
        return rel
    return (md_path.parent / rel).resolve()


def _check_and_repair_md_images(md_path: Path) -> None:
    """
    校验单个 md 的图片引用完整性, 并把所有图片归拢到 <md 所在目录>/images/ 下:

    - 本地图片: 引用的文件必须存在于解压结果中; 不在 md 旁 images/ 时,
      拷贝到 images/ 并把引用改写为 images/<name> (使每个 md 自包含)。
    - 在线图片: 下载到 images/, 引用改写为 images/<name>。
    - 本地引用缺失: 抛出异常, 提示用户检查压缩包完整性。
    """
    md_text = md_path.read_text(encoding="utf-8")
    refs = _collect_all_image_refs(md_text)
    if not refs:
        return

    images_dir = md_path.parent / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    # macOS 上 /var -> /private/var 等符号链接会让未 resolve 的路径比较失效,
    # 统一按 resolve 后的路径判断 src 是否已位于 md 旁的 images/ 中
    images_dir_resolved = images_dir.resolve()

    ref_to_local: dict[str, str] = {}
    used_names: set[str] = set()
    missing: list[str] = []

    for index, ref in enumerate(refs):
        if _is_online_url(ref):
            name = _build_local_filename(ref, index, used_names)
            _download_image(ref, images_dir, name)
            ref_to_local[ref] = str(PurePosixPath("images") / name)
            continue

        src = _resolve_local_ref(md_path, ref)
        if not src.is_file():
            missing.append(ref)
            continue
        # 已按约定位于 md 旁的 images/ 且引用是 POSIX 风格时, 保持原样;
        # Windows 风格反斜杠引用 (images\xxx.png) 也统一改写为 images/xxx.png
        if src.parent == images_dir_resolved and "\\" not in ref:
            continue

        name = _build_local_filename(src.name, index, used_names)
        if src.parent != images_dir_resolved:
            shutil.copy2(src, images_dir / name)
        ref_to_local[ref] = str(PurePosixPath("images") / name)

    if missing:
        raise RuntimeError(
            f"md 文件引用的本地图片缺失, 请检查压缩包完整性\n"
            f"md 文件: {md_path}\n缺失图片: {missing}"
        )

    if ref_to_local:
        new_text = _replace_image_urls(md_text, ref_to_local)
        md_path.write_text(new_text, encoding="utf-8")
        logger.debug(f"已改写 {len(ref_to_local)} 处图片引用: {md_path}")


def _remove_redundant_images(md_paths: list[Path]) -> None:
    """
    删除各 images/ 目录中未被任何 md 引用的冗余图片文件。

    同一个 images/ 目录可能被多个 md 共享, 以全部 md 引用名字的并集为准。
    """
    referenced_by_dir: dict[Path, set[str]] = {}
    for md_path in md_paths:
        images_dir = md_path.parent / "images"
        if not images_dir.is_dir():
            continue
        referenced = referenced_by_dir.setdefault(images_dir, set())
        md_text = md_path.read_text(encoding="utf-8")
        for ref in _collect_all_image_refs(md_text):
            if _is_online_url(ref) or ref.lower().startswith(_DATA_PREFIX):
                continue
            name = PurePosixPath(
                unquote(ref.split("?", 1)[0].split("#", 1)[0]).replace("\\", "/")
            ).name
            referenced.add(name)

    for images_dir, referenced in referenced_by_dir.items():
        for image in images_dir.rglob("*"):
            if image.is_file() and image.name not in referenced:
                image.unlink(missing_ok=True)
                logger.debug(f"删除未引用的冗余图片: {image}")


def _remove_redundant_files(md_dir: Path, md_paths: list[Path]) -> None:
    """
    删除解压目录中的冗余文件: 仅保留 md 文件与各 md 旁的 images/ 目录,
    其余文件 (如压缩包内附带的 txt / pdf 等) 一并清理, 并回收空目录。
    """
    keep_images_dirs = {(md.parent / "images").resolve() for md in md_paths}
    md_path_set = set(md_paths)

    # 先文件后目录 (reverse 排序近似深度序), 空目录用 rmdir 回收
    for path in sorted(md_dir.rglob("*"), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass  # 非空目录, 保留
            continue
        if path in md_path_set:
            continue
        if any(
            path.resolve().is_relative_to(dir_path) for dir_path in keep_images_dirs
        ):
            continue
        path.unlink(missing_ok=True)
        logger.debug(f"删除冗余文件: {path}")


@step_log(desc="校验 md 内容与图片完整性")
def step_3_check_md_content(md_dir: Path, file_title: str) -> list[Path]:
    """
    检查 output/import/<file_title>/ 文件夹内的 md 文件并保证内容完整:

    1. 扫描所有 md 文件, 一个都没有则抛异常
    2. 单个 md 时按命名规范重命名
    3. 多个 md 时校验文件名唯一 (file_title 是唯一键)
    4. 逐个 md 校验图片引用: 本地图片必须存在, 在线图片下载到本地
    5. 删除 images/ 内未引用的冗余图片与目录内其余冗余文件

    最终返回全部 markdown 文件路径列表。
    """
    md_paths = _find_md_files(md_dir)
    if not md_paths:
        raise RuntimeError(
            f"压缩包解压后未找到任何 md 文件, 请检查压缩包完整性: {md_dir}"
        )

    md_paths = _normalize_single_md(md_paths, md_dir, file_title)
    _check_unique_stems(md_paths)

    for md_path in md_paths:
        _check_and_repair_md_images(md_path)

    _remove_redundant_images(md_paths)
    _remove_redundant_files(md_dir, md_paths)

    return md_paths


@trace_node(desc="处理 Markdown 压缩包", need_push=True)
def node_process_md_zip(state: ImportGraphState) -> ImportGraphState:
    """
    串联三步:
    1. 校验 zip 与标题
    2. 解压到 output/import/<file_title>/
    3. 校验 md 文件与图片完整性

    产出:
    - markdown_file_paths: 全部 md 文件路径 (供后续流程对每个 md 分别处理)
    - markdown_file_path : 仅单个 md 时回填, 与既有状态字段兼容
    """
    zip_file, file_title = step_1_validate_and_get_data(state)
    logger.info(f"原始 md 压缩包: {zip_file}, 文件标题: {file_title}")

    md_dir = step_2_unzip_md_zip(zip_file, file_title)
    logger.info(f"解压目录: {md_dir}")

    md_paths = step_3_check_md_content(md_dir, file_title)
    logger.info(f"校验完成, 共 {len(md_paths)} 个 md 文件")

    state["markdown_file_paths"] = [str(path) for path in md_paths]
    if len(md_paths) == 1:
        state["markdown_file_path"] = str(md_paths[0])

    return state


if __name__ == "__main__":
    from rich import print as rprint
    from graphs.import_graph.import_graph_state import create_state, save_state
    from utils.path_utils import PROJECT_ROOT

    start_state = create_state(
        task_id="test_task_start",
        origin_file_path=str(PROJECT_ROOT / "asset/LangGraph 学习笔记.zip"),
    )
    end_state = node_process_md_zip(start_state)
    rprint(end_state)

    json_path = PROJECT_ROOT / "output/tmp/import_02_process_md_zip.json"
    save_state(end_state, str(json_path))
    logger.info(f"状态已保存: {json_path}")
