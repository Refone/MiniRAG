from dataclasses import dataclass
import os
from pathlib import Path
from typing import Final

from utils.path_utils import PROJECT_ROOT


@dataclass(frozen=True)
class _AppConfig:
    upload_dir: Path = PROJECT_ROOT / "output/uploads"

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

    # 聊天记录回溯限制，综合分析过去多少条消息(user assistant 成对)。
    # 仅用于意图识别/查询改写等查询分析场景的上下文窗口；
    # 聊天页历史展示不受此限制 (/history/{session_id} 返回该会话全部记录)。
    chat_message_lookback_count: int = 3 * 2

    # ==== 查询阶段文档级一级召回 (minirag_docs) 参数 ======
    # 文档级召回条数
    docs_recall_limit: int = 5
    # Milvus 向量检索超时时间 (秒)
    milvus_search_timeout: int = 30
    # 融合相似分数 确认阈值
    # 疑似文档不参与二级召回, 故确认阈值在旧值 0.8 基础上适当放宽以保覆盖率,
    # 放宽引入的噪声由二级混合检索 + RRF + rerank 兜底 (具体值待实测标定)
    docs_confirm_threshold: float = 0.75
    # 融合相似分数 疑似阈值
    docs_suspect_threshold: float = 0.5
    # 确认 topk
    docs_confirm_topk: int = 5
    # 疑似 topk
    docs_suspect_topk: int = 5
    # docs 混合检索融合权重 (abstract_dense_weight, keywords_sparse_weight)
    docs_hybrid_weight: tuple[float, float] = (0.7, 0.3)

    # chunks 召回条数
    chunks_recall_limit: int = 20
    # chunks 混合检索融合权重 (dense_weight, sparse_weight)
    # 长文本稀疏信号区分度低, 故以稠密为主(0.7)，稀疏为辅(0.3)
    chunks_hybrid_weight: tuple[float, float] = (0.7, 0.3)
    # chunks 混合检索原始分数阈值: 低于该分数的切片视为无关, 在 RRF 融合前直接过滤
    # 注意: WeightedRanker 分数已归一化到 [0,1], 越大越相似
    # 实测: 有效命中 >= 0.78, 噪声尾部集中在 0.52 左右, 故取 0.55 (可继续实测校准)
    chunks_recall_threshold: float = 0.55
    # chunks RRF 融合后最终保留的 top-k 条数
    chunks_recall_topk: int = 5

    # mcp web search 配置
    mcp_web_search_count: int = 4
    # MCP 超时 (秒)
    mcp_timeout: int = 60

    # RRF (Reciprocal Rank Fusion) 参数
    rrf_k: int = 60
    # RRF 融合权重: (embedding_recalls_weight, hyde_recalls_weight)
    # HyDE 假设性回答召回噪声较多, 以真实查询向量为主
    rrf_weights: tuple[float, float] = (0.7, 0.3)

    # ==== 重排序动态 TopK 参数 ======
    # 动态 TopK 硬上限: 最多保留前 N 条重排序结果
    rerank_max_topk: int = 10
    # 动态 TopK 硬下限: 至少保留前 N 条重排序结果 (>=1, 且 <= rerank_max_topk)
    rerank_min_topk: int = 1
    # 重排序绝对分数下限: 低于该分数的候选直接丢弃, 不依赖断崖检测
    rerank_score_floor: float = 0.5
    # 断崖检测阈值 (绝对差): 相邻两条相关性得分差超过该值视为断崖
    rerank_gap_abs: float = 0.2
    # 断崖检测阈值 (相对比例): 相邻两条相关性得分相对降幅超过该比例视为断崖
    rerank_gap_ratio: float = 0.25


APP_CONFIG: Final[_AppConfig] = _AppConfig()
