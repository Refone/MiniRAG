import shutil
import time
from pathlib import Path

import requests
from pypdf import PdfReader

from common.config.app_config import APP_CONFIG
from common.config.env_config import ENV_CONFIG
from common.config.path_config import IMPORT_TMP_DIR
from common.events.tracing import report_progress, step_log, trace_node
from common.logging import logger
from graphs.import_graph.import_graph_state import ImportGraphState

# PDF 文件头魔数 (前 5 字节)
_PDF_MAGIC = b"%PDF-"


def pdf_page_cnt(pdf_path: Path) -> int:
    """获取 PDF 的页数"""
    with pdf_path.open("rb") as f:
        reader = PdfReader(f)
        return len(reader.pages)


@step_log("校验 PDF 文件")
def step_1_validate_and_setup(state: ImportGraphState) -> tuple[Path, int, str]:
    """校验原始文件是真实存在的 PDF, 并从 state 取回文件标题（由 node_entry 写入）。"""
    origin = state.get("origin_file_path")
    if not origin:
        raise ValueError(f"origin_file_path 为空: {origin!r}")

    pdf_path = Path(origin)
    if not pdf_path.is_file():
        raise ValueError(f"文件不存在或不是文件: {pdf_path}")

    with pdf_path.open("rb") as f:
        if f.read(len(_PDF_MAGIC)) != _PDF_MAGIC:
            raise ValueError(f"文件不是 PDF 格式: {pdf_path}")

    file_title = state.get("file_title")
    if not file_title:
        raise ValueError(f"file_title 为空: {state!r}")

    logger.info(f"PDF 校验通过: {pdf_path}")
    return pdf_path, pdf_page_cnt(pdf_path), file_title


@step_log("上传 PDF, 轮询等待转换完成")
def step_2_upload_and_poll(pdf_path: Path, page_cnt: int) -> str:
    """
    上传 PDF 到 MinerU
    轮询转换结果
    获得转换后的 zip 地址, 并返回。

    四个 HTTP 请求:
        1. apply_xxx    上传申请
        2. upload_xxx   文件上传
        3. poll_xxx     轮询解析结果

        xxx_url:        请求 URL
        xxx_resp:       请求响应
        xxx_resp_data:  请求响应的 JSON 数据

    """

    # 检查 .env 中的相关配置
    if not ENV_CONFIG.mineru.base_url or not ENV_CONFIG.mineru.api_key:
        raise ValueError("MinerU 配置错误, 请检查 .env 是否正确配置 MINERU_ 相关参数")

    # 配置参考: https://mineru.net/apiManage/docs
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ENV_CONFIG.mineru.api_key}",
    }
    apply_url = f"{ENV_CONFIG.mineru.base_url}/file-urls/batch"
    payload = {
        "files": [{"name": pdf_path.name, "data_id": pdf_path.stem}],
        "model_version": "vlm",
        "is_ocr": True,
    }

    # 通知前端: 已进入上传阶段 (页数在入口已确定)
    report_progress(
        f"{page_cnt} 页 · 正在上传",
        {"stage": "uploading", "total": page_cnt},
    )

    # 1. 上传申请
    apply_resp = requests.post(
        apply_url,
        headers=headers,
        json=payload,
        timeout=APP_CONFIG.mineru_api_timeout,
    )
    if apply_resp.status_code != 200:
        raise requests.HTTPError(f"MinerU 上传文件失败: {apply_resp.text}")

    apply_resp_data = apply_resp.json()
    if apply_resp_data["code"] != 0:
        raise requests.RequestException(
            f"HTTP 请求成功, 但业务逻辑失败: {apply_resp_data['msg']}"
        )

    # 2. 文件上传
    upload_urls = apply_resp_data["data"]["file_urls"]
    batch_id = apply_resp_data["data"]["batch_id"]
    if not upload_urls or not batch_id:
        raise requests.RequestException(f"申请上传地址失败: {apply_resp_data['msg']}")

    upload_url = upload_urls[0]
    logger.debug(f"申请上传地址成功: batch_id={batch_id}, upload_url={upload_url}")

    # PUT 上传只返回状态码, 无 body
    with requests.Session() as session:
        # 纯净版的请求头,不随意携带代理的参数
        session.trust_env = False

        upload_resp = session.put(
            upload_url,
            data=pdf_path.read_bytes(),
            timeout=APP_CONFIG.mineru_transfer_timeout,
        )
        if upload_resp.status_code != 200:
            raise requests.RequestException(f"上传文件失败: {upload_resp.text}")

    # 3. 轮询解析结果
    poll_url = f"{ENV_CONFIG.mineru.base_url}/extract-results/batch/{batch_id}"
    logger.debug(f"上传文件成功, 轮询 url: {poll_url}")

    # 轮询间隔时间
    interval_time = APP_CONFIG.poll_interval
    # 最大等待时间
    max_wait_time = APP_CONFIG.per_page_max_wait_time * page_cnt + 30

    start = time.time()
    logger.debug(f"轮询间隔: {interval_time}s, 最大等待时间: {max_wait_time}s")

    last_page = 0
    report_progress(
        f"{page_cnt} 页 · 排队中 · 已等 0s",
        {"stage": "queued", "elapsed_ms": 0},
    )

    while True:
        time.sleep(interval_time)
        elapsed = time.time() - start

        if elapsed > max_wait_time:
            raise requests.Timeout("转换超时")

        try:
            poll_resp = requests.get(
                poll_url,
                headers=headers,
                timeout=APP_CONFIG.mineru_api_timeout,
            )
        except Exception:
            logger.debug(f"请求异常, {interval_time}s 后重试")
            continue

        if poll_resp.status_code != 200:
            logger.debug(f"请求失败, {interval_time}s 后重试")
            continue

        logger.debug(f"请求成功, 轮询返回: {poll_resp.text}")
        poll_resp_data = poll_resp.json()
        if poll_resp_data["code"] != 0:
            raise requests.RequestException(f"MinerU 解析失败: {poll_resp_data['msg']}")

        extract_result = poll_resp_data["data"]["extract_result"][0]
        state = extract_result["state"]
        elapsed_ms = int(elapsed * 1000)

        if state == "done":
            zip_url = extract_result["full_zip_url"]
            if not zip_url:
                raise requests.RequestException(
                    f"MinerU 解析完毕, zip 地址异常: {poll_resp_data['msg']}"
                )
            report_progress(
                f"{page_cnt} 页 · 转换完成 · 正在下载",
                {"stage": "downloading", "elapsed_ms": elapsed_ms},
            )
            logger.debug(f"MinerU 解析完毕, zip 地址: {zip_url}")
            return zip_url

        if state == "failed":
            raise requests.RequestException(f"MinerU 解析失败: {poll_resp_data['msg']}")

        # 仍在处理中: 有页进度就报页进度, 否则按排队阶段报已等待时长
        progress = extract_result.get("extract_progress") or {}
        total_pages = int(progress.get("total_pages") or 0)
        extracted_pages = int(progress.get("extracted_pages") or 0)

        if total_pages > 0:
            # MinerU 按批上报, 页数可能跳变, 这里钳制为单调递增
            last_page = max(last_page, min(extracted_pages, total_pages))
            report_progress(
                f"{page_cnt} 页 · 解析中 {last_page}/{total_pages} 页 · "
                f"已等 {int(elapsed)}s",
                {
                    "stage": "parsing",
                    "done": last_page,
                    "total": total_pages,
                    "elapsed_ms": elapsed_ms,
                },
            )
        else:
            if state == "pending":
                report_progress(
                    f"{page_cnt} 页 · 排队中 · 已等 {int(elapsed)}s",
                    {"stage": "queued", "elapsed_ms": elapsed_ms},
                )
            else:
                # running / converting 但服务端未给出页进度
                report_progress(
                    f"{page_cnt} 页 · 解析中 · 已等 {int(elapsed)}s",
                    {"stage": "parsing", "elapsed_ms": elapsed_ms},
                )

        logger.debug(f"解析未完成, {interval_time}s 后重试")


@step_log("下载并解压")
def step_3_download_and_unzip(zip_url: str, file_title: str) -> Path:
    """
    下载结果包并解压
    把 full.md 重命名为 <file_title>.md 后返回其路径。
    """

    # 导入阶段目录由 path_config 统一提供 (var/import)
    md_dir = IMPORT_TMP_DIR
    md_dir.mkdir(parents=True, exist_ok=True)

    download_response = requests.get(
        zip_url, timeout=APP_CONFIG.mineru_transfer_timeout
    )
    if download_response.status_code != 200:
        raise requests.RequestException(f"下载 zip 文件失败: {download_response.text}")

    # 设置压缩包下载路径和解压路径
    zip_path = md_dir / f"{file_title}.zip"
    extract_dir = md_dir / file_title

    zip_path.write_bytes(download_response.content)
    if extract_dir.is_dir():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    shutil.unpack_archive(zip_path, extract_dir)

    # 根据 MinerU 的约定, 解压后的 full.md 文件即为最终的 Markdown 文件
    full_md = extract_dir / "full.md"
    if not full_md.is_file():
        raise RuntimeError("zip 文件解压后, 没有找到 full.md 文件")

    # 重命名 full.md 为 <file_title>.md
    md_path = full_md.rename(full_md.with_name(f"{file_title}.md"))
    logger.debug(f"下载并解压成功, md 路径: {md_path}")

    return md_path


@trace_node(desc="PDF 转 Markdown", need_push=True)
def node_pdf_to_md(state: ImportGraphState) -> ImportGraphState:
    """
    串联三步
    1. 校验 PDF
    2. MinerU 转换
    3.下载解压
    """

    # 1. 校验 PDF 并准备环境
    pdf_path, page_cnt, file_title = step_1_validate_and_setup(state)

    # 2. MinerU 转换
    zip_url = step_2_upload_and_poll(pdf_path, page_cnt)

    # 3. 下载解压
    md_path = step_3_download_and_unzip(zip_url, file_title)

    state["markdown_file_path"] = str(md_path)

    return state


if __name__ == "__main__":
    from rich import print as rprint

    from common.config.path_config import snapshot_path
    from graphs.import_graph.import_graph_state import load_state, save_state

    prev_state = load_state(snapshot_path("import_01_entry.json"))
    next_state = node_pdf_to_md(prev_state)
    rprint(next_state)

    new_state_json = snapshot_path("import_02_pdf_to_md.json")

    save_state(next_state, new_state_json)
    logger.info("PDF to Markdown 处理完成")
    logger.info(f"状态保存路径: {new_state_json}")
    logger.info(f"文件输出路径: {next_state['markdown_file_path']}")
