import json
import copy
from typing import Annotated, TypedDict



def _keep_latest(_old, new):
    """
    并发分支写同一个 key 时的合并函数: 保留最后一个值。

    LangGraph 默认的 LastValue 通道不允许同一步骤内多个分支并发写同一个 key
    (会抛 InvalidUpdateError)。给这类 key 挂上本 reducer 后通道退化为
    BinaryOperatorAggregate, 并发写入按顺序折叠, 最终保留最后写入的值。
    (md 压缩包扇出时, 每个 md 分支都会写 markdown_file_path 等字段)
    """
    return new


class FileType:
    PDF = "pdf"
    MARKDOWN = "markdown"
    MARKDOWN_ZIP = "markdown-zip"
    UNKNOWN = "<unknown>"


class MdChild(TypedDict):
    """md 压缩包分叉出的单个子任务描述 (node_md_fork 产出)。"""

    child_task_id: str
    # md 文件名 (不含后缀); _check_unique_stems 已保证唯一, 可直接作为 file_title
    title: str
    # 相对解压根目录的 POSIX 路径, 仅用于展示 / 消歧
    path: str
    # 绝对路径, 仅供分支 state 使用; 不进入 SSE 载荷
    markdown_file_path: str
    index: int


class ImportGraphState(TypedDict):
    """
    导入图状态

    Tips:
    考虑到 Graph State 可能需要做 持久化 和 跨平台,
    故最好使用原生数据结构, 以便正常序列化。
    例如路径保持 str, 而非 Path,
    """

    # 任务 ID (父任务 / 上传任务; 子任务分支仍沿用父 task_id 做业务写入)
    task_id: str

    # 子任务进度 ID; 父任务 / PDF / 独文件 md 为空字符串。
    # 注意: 必须声明在 state 中, 否则 Send/子图会丢弃该字段。
    child_task_id: str

    # md 压缩包分叉清单 (仅父任务保留; node_md_fork 产出)
    md_children: list[MdChild]

    # 原始文件路径, 不确定文件格式
    origin_file_path: str

    # 文件类型
    origin_file_type: str

    # (转换后的) markdown 文件路径
    # 带 _keep_latest reducer: md 压缩包扇出时多个分支并发写此字段
    markdown_file_path: Annotated[str, _keep_latest]

    # (md 压缩包解压校验后得到的) 全部 markdown 文件路径列表 (node_process_md_zip 产出)
    markdown_file_paths: list[str]

    # 文件名 (不含后缀)
    file_title: str

    # 文档切分后的 JSON 文件路径 (node_document_split 产出)
    # 带 _keep_latest reducer: md 压缩包扇出时多个分支并发写此字段
    chunks_json_path: Annotated[str, _keep_latest]


_DEFAULT_STATE: ImportGraphState = {
    "task_id": "",
    "child_task_id": "",
    "md_children": [],
    "origin_file_path": "",
    "markdown_file_path": "",
    "markdown_file_paths": [],
    "origin_file_type": "",
    "file_title": "",
    "chunks_json_path": "",
}


def file_type_from_filename(filename: str) -> str:
    """
    根据文件名推断文件类型
    """
    if filename.endswith(".pdf"):
        return FileType.PDF
    elif filename.endswith(".md"):
        return FileType.MARKDOWN
    elif filename.endswith(".markdown"):
        return FileType.MARKDOWN
    elif filename.endswith(".zip"):
        return FileType.MARKDOWN_ZIP
    else:
        return FileType.UNKNOWN


def create_state(**state_dict) -> ImportGraphState:
    """
    根据传入字典，创建一个新的导入节点状态
    """

    state = copy.deepcopy(_DEFAULT_STATE)
    state.update(state_dict)
    return state


def get_default_state() -> ImportGraphState:
    """
    获取默认的导入节点状态
    """

    return copy.deepcopy(_DEFAULT_STATE)


def save_state(state: ImportGraphState, file_path: str) -> None:
    """
    将当前状态保存到指定文件路径
    """

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=4)


def load_state(file_path: str) -> ImportGraphState:
    """
    从指定文件路径加载状态
    """

    with open(file_path, "r", encoding="utf-8") as f:
        state = json.load(f)
    return state


if __name__ == "__main__":
    from rich import print as rprint
    from utils.path_utils import fixture_path, snapshot_path

    state = create_state(
        task_id="test-task-001",
        origin_file_path=str(fixture_path("万用表RS-12的使用.pdf")),
    )

    rprint(state)
    save_state(state, snapshot_path("state_test.json"))
