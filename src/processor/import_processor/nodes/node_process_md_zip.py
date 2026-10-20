from common.config.env_config import ENV_CONFIG
from processor.import_processor.state import ImportGraphState
from pathlib import Path


def step_1_validate_and_get_data(state: ImportGraphState) -> tuple[Path, str]:
    zip_file_str = state.get("origin_file_path")
    if not zip_file_str:
        raise ValueError(f"原始文档路径为空: {zip_file_str!r}")
    zip_file = Path(zip_file_str)

    file_title = state.get("file_title")
    if not state.get("file_title"):
        raise ValueError(f"文档标题为空: {state!r}")

    return zip_file, file_title


def step_2_unzip_md_zip(zip_file: Path, file_title: str) -> Path:
    # TODO: 使用 shutil 解压 zip 文件, 到 output/import/<file_title>/ 文件夹

    # 在 output/import 文件夹中创建 md 目录:
    # output/import/<file_title>/
    # ├── images/
    # └── <file_title>.md
    pass


def step_3_check_md_content(target_md: Path) -> list[Path]:
    # TODO: 检查 output/import/<file_title>/ 文件夹内是否有 md 文件, 并且扫描 md 文件，
    # 如果里面有本地图片连接，检查output/import/<file_title>/ 文件夹内是否存在对应的图片文件
    # 如果里面有网络图片，下载到 output/import/<file_title>/images/ 文件夹
    # 最终确保 output/import/<file_title>/ 文件夹内的 md 文件和 images 文件夹内容完整
    # 如果不完整，在这一步抛出异常，提示用户检查文件完整性。
    # 最终返回 markdown 文件的路径
    pass


def node_process_md_zip(state: ImportGraphState) -> ImportGraphState:
    zip_file, file_title = step_1_validate_and_get_data(state)
    target_md = step_2_unzip_md_zip(zip_file, file_title)

    state["markdown_file_path"] = str(target_md)
    return state
