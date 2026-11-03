"""MinerU PDF 转换 seam（tier 3）。

把 PDF 上传、轮询、下载解压收敛到本模块；图节点只做校验、进度回调与 state 编排，
测试 patch `common.client.mineru_pdf_to_md` 即可跳过真实 MinerU。
"""

import shutil
import time
from collections.abc import Callable
from pathlib import Path

import requests

from common.config.app_config import APP_CONFIG
from common.config.env_config import ENV_CONFIG
from common.config.path_config import IMPORT_TMP_DIR
from common.logging import logger

ProgressCallback = Callable[[str, dict], None]


def _report(
    on_progress: ProgressCallback | None,
    text: str,
    metrics: dict | None = None,
) -> None:
    if on_progress is not None:
        on_progress(text, metrics or {})


def _upload_and_poll(
    pdf_path: Path,
    page_cnt: int,
    on_progress: ProgressCallback | None,
) -> str:
    """上传 PDF 到 MinerU 并轮询，返回转换结果 zip 地址。"""
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

    _report(
        on_progress,
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

    with requests.Session() as session:
        # 纯净版的请求头, 不随意携带代理的参数
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

    interval_time = APP_CONFIG.poll_interval
    max_wait_time = APP_CONFIG.per_page_max_wait_time * page_cnt + 30
    start = time.time()
    logger.debug(f"轮询间隔: {interval_time}s, 最大等待时间: {max_wait_time}s")

    last_page = 0
    _report(on_progress, f"{page_cnt} 页 · 排队中", {"stage": "queued"})

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

        if state == "done":
            zip_url = extract_result["full_zip_url"]
            if not zip_url:
                raise requests.RequestException(
                    f"MinerU 解析完毕, zip 地址异常: {poll_resp_data['msg']}"
                )
            _report(
                on_progress,
                f"{page_cnt} 页 · 转换完成 · 正在下载",
                {"stage": "downloading"},
            )
            logger.debug(f"MinerU 解析完毕, zip 地址: {zip_url}")
            return zip_url

        if state == "failed":
            raise requests.RequestException(f"MinerU 解析失败: {poll_resp_data['msg']}")

        # 仍在处理中: 有页进度就报页进度, 否则按状态报排队 / 解析
        progress = extract_result.get("extract_progress") or {}
        total_pages = int(progress.get("total_pages") or 0)
        extracted_pages = int(progress.get("extracted_pages") or 0)

        if total_pages > 0:
            last_page = max(last_page, min(extracted_pages, total_pages))
            _report(
                on_progress,
                f"{page_cnt} 页 · 解析中 {last_page}/{total_pages} 页",
                {
                    "stage": "parsing",
                    "done": last_page,
                    "total": total_pages,
                },
            )
        elif state == "pending":
            _report(on_progress, f"{page_cnt} 页 · 排队中", {"stage": "queued"})
        else:
            _report(on_progress, f"{page_cnt} 页 · 解析中", {"stage": "parsing"})

        logger.debug(f"解析未完成, {interval_time}s 后重试")


def _download_and_unzip(zip_url: str, file_title: str) -> Path:
    """下载结果包并解压，把 full.md 重命名为 <file_title>.md 后返回其路径。"""
    md_dir = IMPORT_TMP_DIR
    md_dir.mkdir(parents=True, exist_ok=True)

    download_response = requests.get(
        zip_url, timeout=APP_CONFIG.mineru_transfer_timeout
    )
    if download_response.status_code != 200:
        raise requests.RequestException(f"下载 zip 文件失败: {download_response.text}")

    zip_path = md_dir / f"{file_title}.zip"
    extract_dir = md_dir / file_title

    zip_path.write_bytes(download_response.content)
    if extract_dir.is_dir():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    shutil.unpack_archive(zip_path, extract_dir)

    full_md = extract_dir / "full.md"
    if not full_md.is_file():
        raise RuntimeError("zip 文件解压后, 没有找到 full.md 文件")

    md_path = full_md.rename(full_md.with_name(f"{file_title}.md"))
    logger.debug(f"下载并解压成功, md 路径: {md_path}")
    return md_path


def mineru_pdf_to_md(
    pdf_path: Path,
    page_cnt: int,
    file_title: str,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """PDF → MinerU 转换 → 下载解压，返回 Markdown 路径。"""
    zip_url = _upload_and_poll(pdf_path, page_cnt, on_progress)
    return _download_and_unzip(zip_url, file_title)
