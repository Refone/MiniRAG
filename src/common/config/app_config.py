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

    # ==== 图片展示过滤参数 ======
    # 所属切片的 rerank 分数低于该值时不展示其中的图片 (粗筛, 减少图片级 rerank 的候选量)
    image_min_chunk_score: float = 0.6
    # 图片描述 (alt 文本) 与重写后问题的 rerank 分数低于该值时不展示
    # 与 rerank_score_floor 同一量纲, 短描述得分略低于长文本, 如误杀可下调至 0.4~0.45
    image_min_rerank_score: float = 0.7
    # 诉求点 rerank 分数门槛: 将问题与图片描述中已确认的主体名 (confirm_list)
    # 剔除后, 对剩余诉求点 (如"四指操作") 再做一次 rerank, 低于该值说明图片与
    # 问题的实际诉求不相关 (主体名带来的虚高分不算数), 直接丢弃。
    # 剔除后文本更短、得分整体偏低, 建议从 0.35~0.45 起步实测校准
    image_min_aspect_score: float = 0.4
    # 单次回答最多展示的图片数量
    image_max_count: int = 8


APP_CONFIG: Final[_AppConfig] = _AppConfig()
