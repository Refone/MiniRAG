"""后端启动自检。

startup_checks() 在 FastAPI lifespan 中执行, 检查分为两类:

1. 硬依赖 (任一项失败则阻止后端启动):
   - Milvus: 连通性 + docs / chunks 集合初始化
   - MinIO: 连通性 + bucket 初始化 (含匿名只读策略)
   - MongoDB: 连通性
   - 运行时目录: 上传 / MinerU 解压 / 日志目录, 存在且可写

2. 软依赖 (缺失仅告警, 不阻止启动):
   - 各外部模型 API 密钥 (MinerU / VLM / Embedding+Rerank / LLM / Web Search MCP)
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Callable

from common.client import MILVUS_CLIENT, MINIO_CLIENT, MONGODB_CLIENT
from common.config.app_config import APP_CONFIG
from common.config.env_config import ENV_CONFIG
from utils.logging_utils import logger


def check_milvus() -> None:
    """校验 Milvus 连通性, 并初始化 docs / chunks 集合 (有则跳过, 无则创建)。"""
    MILVUS_CLIENT.check_health()
    MILVUS_CLIENT.prepare_docs_collection()
    MILVUS_CLIENT.prepare_chunks_collection()


def check_minio() -> None:
    """校验 MinIO 连通性, 并初始化 bucket (有则跳过, 无则创建含匿名只读策略)。"""
    MINIO_CLIENT.check_health()
    MINIO_CLIENT.prepare_bucket()


def check_mongodb() -> None:
    """校验 MongoDB 连通性 (无 schema, 无需初始化资源)。"""
    MONGODB_CLIENT.check_health()


def runtime_dirs() -> list[Path]:
    """API 运行所需的目录: 上传目录 / 导入阶段临时目录 / 日志目录。"""
    return [
        Path(ENV_CONFIG.output_dir.upload_tmp_dir),
        Path(ENV_CONFIG.output_dir.import_tmp_dir),
        Path(ENV_CONFIG.output_dir.log_dir),
    ]


def ensure_runtime_dirs() -> None:
    """确保运行时目录存在且可写。

    存在性用 mkdir(parents=True, exist_ok=True) 保证;
    可写性用写入探针文件验证 (名字带 uuid, 避免多进程并发时互相删除)。
    """
    for directory in runtime_dirs():
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".setup_write_probe_{uuid.uuid4().hex}"
        probe.touch()
        probe.unlink()
        logger.debug(f"运行时目录可用: {directory}")


# (环境变量名, 当前值, 对应功能), 值在 import 时读取, 与各 model 单例的初始化时机一致
_API_KEY_CHECKS: list[tuple[str, str, str]] = [
    ("MINERU_API_KEY", ENV_CONFIG.mineru.api_key, "PDF 解析 (MinerU)"),
    ("DASHSCOPE_API_KEY", ENV_CONFIG.dashscope.api_key, "阿里云百炼"),
]


def warn_missing_api_keys() -> None:
    """软检查: 未配置的 API 密钥只告警, 不阻止启动。"""
    for env_name, value, feature in _API_KEY_CHECKS:
        if not value:
            logger.warning(
                f"未配置 {env_name}, 功能「{feature}」将不可用, 请在 .env 中补充"
            )


# (检查名, 检查函数, 失败时的排查提示)
_HARD_STEPS: list[tuple[str, Callable[[], None], str]] = [
    (
        "Milvus (连通性 + 集合初始化)",
        check_milvus,
        "请确认 Milvus 已启动且 MILVUS_ENDPOINT 配置正确",
    ),
    (
        "MinIO (连通性 + bucket 初始化)",
        check_minio,
        "请确认 MinIO 已启动且 MINIO_ENDPOINT / 访问密钥配置正确",
    ),
    (
        "MongoDB (连通性)",
        check_mongodb,
        "请确认 MongoDB 已启动且 MONGODB_URI 配置正确",
    ),
    (
        "运行时目录 (存在且可写)",
        ensure_runtime_dirs,
        "请确认后端进程对输出目录有读写权限",
    ),
]


def startup_checks() -> None:
    """后端启动自检: 逐项执行硬依赖检查, 汇总失败并阻止启动。"""
    logger.info("开始执行后端启动自检 ...")

    failures: list[tuple[str, Exception, str]] = []
    for label, check, hint in _HARD_STEPS:
        try:
            check()
            logger.success(f"自检通过: {label}")
        except Exception as exc:  # noqa: BLE001 - 自检必须兜住任何异常并汇总
            logger.exception(f"自检失败: {label}")
            failures.append((label, exc, hint))

    warn_missing_api_keys()

    if failures:
        details = "; ".join(
            f"{label} -> {exc} (提示: {hint})" for label, exc, hint in failures
        )
        raise RuntimeError(
            f"后端启动自检失败 ({len(failures)}/{len(_HARD_STEPS)} 项未通过): {details}"
        )

    logger.success("后端启动自检完成")
