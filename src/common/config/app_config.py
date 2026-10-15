from dataclasses import dataclass
import os
from typing import Final


@dataclass(frozen=True)
class _AppConfig:
    # 支持的图片格式
    support_image_format: tuple[str, ...] = (
        "jpg",
        "jpeg",
        "png",
        "gif",
        "bmp",
        "webp",
    )

    # 解释 Markdown 中图片时, 最大探测前后的字符数
    md_image_surrounding_context_max_chars: int = 500

    # VLM 请求超时时间 (秒)
    vlm_request_timeout: int = 60
    # VLM 请求重试次数
    vlm_request_retry_attempts: int = 3

    # 切分 Markdown 内容时的配置（软限制）
    max_chunk_size: int = 1000
    min_chunk_size: int = 200
    overlap_size: int = 100

    max_concurrent_requests: int = os.cpu_count() - 1

    # 聊天记录回溯限制，综合分析过去多少条消息(user assistant 成对)
    chat_message_lookback_count: int = 3 * 2

    # ==== 查询阶段主体识别参数 ======
    # 向量数据库召回条数
    item_name_recall_limit: int = 5
    # 稠密+稀疏融合排序, 稠密向量权重
    item_name_dense_vector_weight: float = 0.3
    # Milvus 向量检索超时时间 (秒)
    milvus_search_timeout: int = 30
    # 融合相似分数 确认阈值
    item_name_confirm_threshold: float = 0.85
    # 融合相似分数 疑似阈值
    item_name_suspect_threshold: float = 0.1
    # 确认 topk
    item_name_confirm_topk: int = 5
    # 疑似 topk
    item_name_suspect_topk: int = 5


APP_CONFIG: Final[_AppConfig] = _AppConfig()
