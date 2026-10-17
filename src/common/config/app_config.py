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
    # Milvus 向量检索超时时间 (秒)
    milvus_search_timeout: int = 30
    # 融合相似分数 确认阈值
    item_name_confirm_threshold: float = 0.9
    # 融合相似分数 疑似阈值
    item_name_suspect_threshold: float = 0.8
    # 确认 topk
    item_name_confirm_topk: int = 5
    # 疑似 topk
    item_name_suspect_topk: int = 5
    # item_name 混合检索融合权重 (dense_weight, sparse_weight)
    # 短文本以稀疏为主(0.7)，稠密为辅(0.3)
    item_name_hybrid_weight: tuple[float, float] = (0.3, 0.7)

    # chunks 召回条数
    chunks_recall_limit: int = 20
    # chunks 混合检索融合权重 (dense_weight, sparse_weight)
    # 长文本稀疏信号区分度低, 故以稠密为主(0.7)，稀疏为辅(0.3)
    chunks_hybrid_weight: tuple[float, float] = (0.7, 0.3)
    # chunks 融合相似分数阈值: 低于该分数的切片视为无关, 直接过滤
    chunks_recall_threshold: float = 0.85
    # chunks 过滤后最终保留的 top-k 条数
    chunks_recall_topk: int = 10

    # mcp web search 配置
    mcp_web_search_count: int = 5
    # MCP 超时 (秒)
    mcp_timeout: int = 60

    # RRF (Reciprocal Rank Fusion) 参数
    rrf_k: int = 60


APP_CONFIG: Final[_AppConfig] = _AppConfig()
