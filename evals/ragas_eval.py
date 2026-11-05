"""基于 Ragas 的 MiniRAG 端到端评估程序。

evals/ragas_eval.py \
  --sample_doc "tests/fixtures/华为擎云 S520 Gen2 用户指南-(YTGZ,Windows11_03,zh-cn).pdf" \
  --question_num 10 \
  --question evals/output/eval_questions.csv \
  --result evals/output/eval_result.csv \
  --report evals/output/report.md

"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import logging
import math
import os
import re
import sys
import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

# Ragas 默认会上报匿名使用统计；本地评估显式关闭。
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

warnings.filterwarnings(
    "ignore",
    message=r".*langchain-community.*",
    category=DeprecationWarning,
)
# LangChain 在非流式调用拿不到 usage 时会发此警告；评估不依赖该 usage。
warnings.filterwarnings(
    "ignore",
    message=r"Unexpected type for token usage.*",
    category=UserWarning,
)

try:
    import ragas  # noqa: E402
except ModuleNotFoundError as exc:  # pragma: no cover - 环境缺失时的提示
    raise SystemExit(
        "缺少 ragas。请先安装评估依赖，例如：\n"
        '  uv pip install "ragas==0.4.3" "langchain-community<0.4"'
    ) from exc

try:
    # Ragas 0.4.3 仍会直接从 langchain-community 导入该模块；
    # langchain-community 0.4.x 已移除它，需要提前给出可操作的提示。
    import langchain_community.chat_models.vertexai  # noqa: E402,F401
except ModuleNotFoundError as exc:  # pragma: no cover - 依赖版本不兼容时的提示
    raise SystemExit(
        "当前 langchain-community 与 ragas 0.4.3 不兼容。\n"
        "请安装 0.4 以下版本后重试：\n"
        '  uv pip install "ragas==0.4.3" "langchain-community<0.4"'
    ) from exc

from langchain_core.embeddings import Embeddings  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402
from pypdf import PdfReader  # noqa: E402
from ragas import EvaluationDataset, SingleTurnSample, evaluate  # noqa: E402
from ragas.dataset_schema import EvaluationResult  # noqa: E402
from ragas.embeddings.base import LangchainEmbeddingsWrapper  # noqa: E402
from ragas.llms.base import LangchainLLMWrapper  # noqa: E402
from ragas.metrics._answer_correctness import AnswerCorrectness  # noqa: E402
from ragas.metrics._answer_relevance import AnswerRelevancy  # noqa: E402
from ragas.metrics._context_precision import ContextPrecision  # noqa: E402
from ragas.metrics._context_recall import ContextRecall  # noqa: E402
from ragas.metrics._faithfulness import Faithfulness  # noqa: E402
from ragas.run_config import RunConfig  # noqa: E402

from common import client, model, store  # noqa: E402
from common.client.milvus_client import (  # noqa: E402
    MilvusChunksRecall,
    MilvusDocsRecall,
)
from common.config.app_config import APP_CONFIG  # noqa: E402
from common.config.env_config import ENV_CONFIG  # noqa: E402
from common.events import EVENT_BUS, TASK_MANAGER, SSEEvent  # noqa: E402
from common.logging import logger  # noqa: E402
from common.store.chat_history import MessageRole  # noqa: E402
from graphs.query_graph.query_graph_state import RerankResult  # noqa: E402
from service import query_service  # noqa: E402

# 项目模型返回的是 LangChain BaseChatModel；Ragas 0.4 的 legacy 指标仍
# 接受它，但构造 wrapper 时会发两条弃用警告。评估脚本有意使用 legacy
# 通道，以复用项目模型的限速、重试与关闭思考模式等封装。
warnings.filterwarnings(
    "ignore",
    message=r"Langchain(LLM|Embeddings)Wrapper is deprecated.*",
    category=DeprecationWarning,
)

DEFAULT_QUESTIONS_PATH = PROJECT_ROOT / "evals" / "eval_questions.csv"
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent / "output" / "eval_result.csv"
DEFAULT_REPORT_PATH = Path(__file__).resolve().parent / "output" / "report.md"
DEFAULT_DOC_TITLE = "华为擎云 S520 Gen2 用户指南"
DEFAULT_QUESTION_NUM = 10
MIN_DOC_CHARS = 200

# 题目生成时最多送给 LLM 的文档字符数；超长文档按等距窗口抽样。
MAX_DOC_CHARS = 30_000
DOC_EXCERPT_WINDOWS = 10
# 报告里标记“低分题”的阈值（任一指标低于该值即列入）。
LOW_SCORE_THRESHOLD = 0.6

# Ragas 返回的指标键 -> 需求中的 CSV 列名。
METRIC_COLUMNS: dict[str, str] = {
    "faithfulness": "faithfulness",
    "answer_relevancy": "Answer Relevancy",
    "context_precision": "Context Precision",
    "context_recall": "Context Recall",
    "answer_correctness": "Answer Correctness",
}
OUTPUT_COLUMNS = [
    "question",
    "context",
    "Answer",
    "ground_truth",
    *METRIC_COLUMNS.values(),
]


class EvalError(RuntimeError):
    """评估流程中的可预期错误，用于向 CLI 输出简洁的失败原因。"""


@dataclass(frozen=True)
class TargetDocument:
    """评估时限定检索范围的目标文档。"""

    doc_id: int
    file_title: str
    docs_abstract: str = ""


@dataclass(frozen=True)
class RunMeta:
    """一次完整评估运行的元信息，供 Markdown 报告使用。"""

    sample_doc: Path | None
    question_file: Path
    target: TargetDocument | None
    generated_questions: bool
    enable_web_search: bool
    enable_hyde: bool


class GeneratedQA(BaseModel):
    """LLM 生成的单条评估题目。"""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(
        min_length=1,
        description="面向文档的自然语言问题，不依赖上下文即可独立理解",
    )
    ground_truth: str = Field(
        min_length=1,
        description="只依据文档原文得出的简洁标准答案，包含关键数值与单位",
    )


class GeneratedQASet(BaseModel):
    """LLM 生成的一组评估题目。"""

    model_config = ConfigDict(extra="forbid")

    questions: list[GeneratedQA] = Field(
        min_length=1,
        description="按文档不同章节覆盖的题目列表",
    )


@dataclass
class EvalRecord:
    """单题 RAG 运行结果，后续会与 Ragas 分数合并写出 CSV。"""

    question: str
    ground_truth: str
    answer: str
    contexts: list[str] = field(default_factory=list)

    @property
    def context_text(self) -> str:
        """把重排片段拼成单个 CSV 单元格。

        片段之间用 ``---`` 分隔，既保留来源边界，也便于人工排查；Ragas
        计算时仍使用未经拼接的 ``contexts`` 列表。
        """
        return "\n\n---\n\n".join(self.contexts)


class ProjectEmbeddings(Embeddings):
    """把项目 ``QwenEmbedding`` 适配为 LangChain Embeddings。

    Ragas 的 Answer Relevancy 与 Answer Correctness 需要句向量。项目
    embedding 实际返回 ``{dense, sparse}`` 混合向量，这里只取 dense 分量；
    sparse 分量仅用于 Milvus 混合检索。
    """

    def __init__(self, batch_size: int | None = None) -> None:
        """初始化适配器。

        Args:
            batch_size: 单次调用 DashScope embedding 的文本条数，默认读取
                项目配置 ``DASHSCOPE_EMBEDDING_BATCH_SIZE``。
        """
        self._batch_size = batch_size or ENV_CONFIG.dashscope.embedding_batch_size

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入文档文本。

        Args:
            texts: 待嵌入文本列表。

        Returns:
            与输入顺序一致的稠密向量列表。
        """
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            hybrid_vectors, _ = model.get_embedding().embed_document_hybrid(batch)
            vectors.extend(item["dense"] for item in hybrid_vectors)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        """嵌入单条查询文本。

        Args:
            text: 待嵌入的查询。

        Returns:
            查询的稠密向量。
        """
        hybrid_vectors, _ = model.get_embedding().embed_query_hybrid([text])
        return hybrid_vectors[0]["dense"]


class _DocumentScopedMilvusClient:
    """把 Milvus 检索固定到目标文档的代理客户端。

    评估问题来自目标 PDF，但共享向量库里还有其它文档。若走全库文档
    级召回，通用问法（如“安全锁孔尺寸是多少”）可能匹配不到目标文档，
    导致 ``rerank_results`` 为空、评估退化为通识问答。该代理做两件事：

    1. ``hybrid_search_docs`` 直接返回目标文档并置 ``score=1.0``，让
       intent 节点稳定进入二级召回；
    2. ``hybrid_search_chunks`` 忽略传入的 doc_ids，始终限定到目标文档。

    这样评估的是“目标文档内的切片召回 + 重排 + 生成”，而不是跨文档
    选择；文档选择本身不在本测试集要衡量的范围内。
    """

    def __init__(self, inner: Any, target: TargetDocument) -> None:
        """保存真实客户端与目标文档。

        Args:
            inner: 项目真实的 ``MiniRagMilvusClient``。
            target: 目标文档元数据。
        """
        self._inner = inner
        self._target = target

    def hybrid_search_docs(
        self,
        texts: list[str],
        limit: int = APP_CONFIG.docs_recall_limit,
    ) -> tuple[list[list[MilvusDocsRecall]] | None, int]:
        """返回固定目标文档作为文档级召回结果。

        Args:
            texts: 查询文本列表；每个查询返回同一目标文档。
            limit: 兼容真实客户端签名，当前不使用。

        Returns:
            ``(每个查询一组目标文档命中, 0)``；embedding token 记为 0，
            因为此步骤没有调用 embedding。
        """
        del limit
        if not texts:
            return [], 0
        hit: MilvusDocsRecall = {
            "id": self._target.doc_id,
            "score": 1.0,
            "file_title": self._target.file_title,
            "docs_abstract": self._target.docs_abstract,
        }
        return [[dict(hit)] for _ in texts], 0

    def hybrid_search_chunks(
        self,
        query_text: list[str],
        doc_ids: list[int] | None = None,
        limit: int = APP_CONFIG.chunks_recall_limit,
    ) -> tuple[list[list[MilvusChunksRecall]] | None, int]:
        """在目标文档内执行切片级混合检索。

        Args:
            query_text: 查询文本列表。
            doc_ids: 调用方传入的文档范围；本代理忽略并强制使用目标文档。
            limit: 每个查询返回的切片条数。

        Returns:
            真实 Milvus 客户端的切片召回结果与 embedding token 数。
        """
        del doc_ids
        return self._inner.hybrid_search_chunks(
            query_text=query_text,
            doc_ids=[self._target.doc_id],
            limit=limit,
        )

    def __getattr__(self, name: str) -> Any:
        """未覆盖的方法和属性透传给真实客户端。"""
        return getattr(self._inner, name)


def _escape_milvus_literal(value: str) -> str:
    """转义 Milvus 过滤器字符串字面量。

    Args:
        value: 原始字符串。

    Returns:
        对反斜杠和双引号转义后的字符串。
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _resolve_target_document(doc_title: str) -> TargetDocument:
    """按标题子串在 Milvus docs 集合中定位目标文档。

    Args:
        doc_title: 文档标题或标题子串。

    Returns:
        命中的目标文档元数据；存在多个子串命中时优先精确标题。

    Raises:
        EvalError: 没有文档标题匹配，或 Milvus 查询失败。
    """
    milvus = client.get_milvus_client()
    collection = ENV_CONFIG.milvus.collection_docs
    try:
        rows = milvus.query(
            collection_name=collection,
            filter=f'file_title like "%{_escape_milvus_literal(doc_title)}%"',
            output_fields=["id", "file_title", "docs_abstract"],
            limit=10,
        )
    except Exception as exc:  # noqa: BLE001 - 统一翻译成可读的评估错误
        raise EvalError(f"查询 Milvus 文档失败: {exc}") from exc

    if not rows:
        titles = ""
        with contextlib.suppress(Exception):
            available = milvus.query(
                collection_name=collection,
                filter="id >= 0",
                output_fields=["file_title"],
                limit=20,
            )
            titles = "；".join(str(item.get("file_title", "")) for item in available)
        raise EvalError(
            f"未找到标题包含《{doc_title}》的文档。现有文档：{titles or '（空）'}"
        )

    exact = [row for row in rows if row.get("file_title") == doc_title]
    chosen = exact[0] if exact else rows[0]
    if len(rows) > 1:
        print(f"提示: 标题匹配到 {len(rows)} 条文档，使用《{chosen['file_title']}》")

    return TargetDocument(
        doc_id=int(chosen["id"]),
        file_title=str(chosen["file_title"]),
        docs_abstract=str(chosen.get("docs_abstract") or ""),
    )


@contextmanager
def _scoped_milvus(target: TargetDocument | None) -> Iterator[None]:
    """临时把 ``common.client.get_milvus_client`` 替换为文档级代理。

    Args:
        target: 目标文档；为 ``None`` 时不限制检索范围。

    Yields:
        无；退出上下文时恢复原始访问器。
    """
    if target is None:
        yield
        return

    original_getter = client.get_milvus_client
    scoped_client = _DocumentScopedMilvusClient(original_getter(), target)
    client.get_milvus_client = lambda: scoped_client  # type: ignore[assignment]
    try:
        yield
    finally:
        client.get_milvus_client = original_getter  # type: ignore[assignment]


def _extract_final_answer(
    frames: list[tuple[str, dict[str, Any]]],
    session_id: str,
) -> str:
    """从 SSE 帧中提取最终答案，失败时回退到会话历史。

    Args:
        frames: ``EVENT_BUS.take`` 返回的 ``(event, payload)`` 列表。
        session_id: 当前评估会话 ID，用于历史回退。

    Returns:
        非空的最终答案文本。

    Raises:
        EvalError: final 帧和历史记录中都没有答案。
    """
    for event, payload in reversed(frames):
        if event == SSEEvent.FINAL:
            answer = str(payload.get("answer") or "").strip()
            if answer:
                return answer

    messages = store.get_chat_history_manager().get_latest_messages(
        session_id=session_id,
        limit=5,
    )
    for message in messages:
        if (
            message.get("role") == MessageRole.ASSISTANT
            and str(message.get("text") or "").strip()
        ):
            return str(message["text"]).strip()

    raise EvalError("流程未产出 final 答案，且会话历史中没有 assistant 消息")


def _extract_contexts(state: dict[str, Any]) -> list[str]:
    """从查询结束 state 的 ``rerank_results`` 中提取上下文文本。

    Args:
        state: ``query_service.arun_query`` 返回的结束状态。

    Returns:
        按重排顺序排列的非空上下文列表。
    """
    rerank_results: list[RerankResult] = state.get("rerank_results") or []
    contexts: list[str] = []
    for item in rerank_results:
        document = str(item.get("document") or "").strip()
        if document:
            contexts.append(document)
    return contexts


async def _arun_single_query(
    question: str,
    ground_truth: str,
    *,
    enable_web_search: bool,
    enable_hyde: bool,
) -> EvalRecord:
    """执行单题 RAG 流程并收集答案与上下文。

    Args:
        question: 用户问题。
        ground_truth: 该题的标准答案，原样带入结果。
        enable_web_search: 是否启用网络搜索分支。
        enable_hyde: 是否启用 HyDE 分支。

    Returns:
        单题运行结果。

    Raises:
        EvalError: 流程推送 error 帧，或没有产出最终答案。
    """
    session_id = f"ragas-eval-{uuid4().hex}"
    EVENT_BUS.create(session_id)
    try:
        state = await query_service.arun_query(
            session_id=session_id,
            query=question,
            enable_web_search=enable_web_search,
            enable_hyde=enable_hyde,
        )
        frames = EVENT_BUS.take(session_id)

        errors = [payload for event, payload in frames if event == SSEEvent.ERROR]
        if errors:
            raise EvalError(str(errors[-1].get("error") or errors[-1]))

        answer = _extract_final_answer(frames, session_id)
        contexts = _extract_contexts(state)
        print(f"     answer={len(answer)} 字符, context={len(contexts)} 条")
        return EvalRecord(
            question=question,
            ground_truth=ground_truth,
            answer=answer,
            contexts=contexts,
        )
    finally:
        with contextlib.suppress(Exception):
            store.get_chat_history_manager().clear_history(session_id)
        with contextlib.suppress(Exception):
            store.get_token_usage_manager().clear_usage(session_id)
        EVENT_BUS.remove(session_id)
        TASK_MANAGER.clear(session_id)


async def _arun_all_queries(
    questions: list[dict[str, str]],
    *,
    enable_web_search: bool,
    enable_hyde: bool,
) -> list[EvalRecord]:
    """顺序执行所有问题，避免并发 requests 触发远端限流。

    Args:
        questions: ``question`` / ``ground_truth`` 字典列表。
        enable_web_search: 是否启用网络搜索分支。
        enable_hyde: 是否启用 HyDE 分支。

    Returns:
        与输入顺序一致的运行结果列表。

    Raises:
        EvalError: 任意一题执行失败。失败即中止，避免产出不完整的评估表。
    """
    records: list[EvalRecord] = []
    total = len(questions)
    for index, item in enumerate(questions, start=1):
        question = item["question"]
        print(f"[{index}/{total}] 运行 RAG: {question}")
        try:
            record = await _arun_single_query(
                question,
                item["ground_truth"],
                enable_web_search=enable_web_search,
                enable_hyde=enable_hyde,
            )
        except Exception as exc:  # noqa: BLE001 - 补充题号后再抛出
            raise EvalError(
                f"第 {index} 题 RAG 执行失败: {question!r} -> {exc}"
            ) from exc
        records.append(record)
    return records


def _normalize_document_text(text: str) -> str:
    """清理 PDF / Markdown 提取文本中的空字符和多余空行。

    Args:
        text: 原始文档文本。

    Returns:
        归一化后的文本。
    """
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _read_sample_document(sample_doc: Path) -> str:
    """读取 ``.md`` / ``.markdown`` / ``.pdf`` 样本文档的纯文本。

    Args:
        sample_doc: 样本文档路径。

    Returns:
        归一化后的文档文本。

    Raises:
        EvalError: 文件不存在、格式不支持、PDF 无法解析或文本过短。
    """
    sample_doc = sample_doc.expanduser()
    if not sample_doc.is_file():
        raise EvalError(f"样本文档不存在: {sample_doc}")

    suffix = sample_doc.suffix.lower()
    if suffix in {".md", ".markdown"}:
        try:
            text = sample_doc.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise EvalError(f"Markdown 不是 UTF-8 编码: {sample_doc}") from exc
    elif suffix == ".pdf":
        # pypdf 遇到缺少 fontTools 的字体时会打印无害告警，评估输出保持干净。
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        try:
            reader = PdfReader(str(sample_doc))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:  # noqa: BLE001 - 统一翻译成可读的评估错误
            raise EvalError(f"PDF 解析失败: {sample_doc} -> {exc}") from exc
    else:
        raise EvalError(
            f"不支持的样本文档格式 {suffix!r}，请使用 .md / .markdown / .pdf"
        )

    text = _normalize_document_text(text)
    if len(text) < MIN_DOC_CHARS:
        raise EvalError(
            f"样本文档提取文本过短（{len(text)} 字符），可能是扫描版 PDF 或空文件"
        )
    return text


def _select_document_excerpt(text: str, max_chars: int = MAX_DOC_CHARS) -> str:
    """为题目生成选取文档文本；超长时按等距窗口覆盖全文。

    Args:
        text: 完整文档文本。
        max_chars: 送给 LLM 的最大字符数。

    Returns:
        不超过 ``max_chars`` 的文档片段。
    """
    if len(text) <= max_chars:
        return text

    window = max(1_000, max_chars // DOC_EXCERPT_WINDOWS)
    step = max(1, (len(text) - window) // max(1, DOC_EXCERPT_WINDOWS - 1))
    parts: list[str] = []
    for index in range(DOC_EXCERPT_WINDOWS):
        start = min(index * step, max(0, len(text) - window))
        part = text[start : start + window].strip()
        if part and part not in parts:
            parts.append(part)
    return "\n\n[...]\n\n".join(parts)[:max_chars]


def _build_question_generation_prompt(
    document_text: str,
    question_num: int,
    doc_name: str,
) -> str:
    """构造“从文档生成 QA 对”的提示词。

    Args:
        document_text: 样本文档文本。
        question_num: 需要生成的题目数。
        doc_name: 文档名称，用于提示词上下文。

    Returns:
        完整提示词。
    """
    return f"""你是一名严谨的 RAG 评测数据工程师。请只根据下面这份文档生成 {question_num} 条中文测试题。

【样本文档】
{doc_name}

【硬性要求】
1. 必须正好生成 {question_num} 条题目，不能多也不能少。
2. 每题只能考察文档中明确写出的事实；禁止使用外部知识、常识补全或猜测。
3. 问题必须像真实用户会问的问题，且脱离文档上下文也能独立理解；不得出现“本文档”“上述”“本指南”等指代。
4. 题目要覆盖文档的不同章节或主题，优先选择具体事实、数值、步骤、条件、限制和安全注意事项；不要全部集中在同一页。
5. ground_truth 必须直接回答问题，简洁、完整，保留关键数值和单位；不要写“根据文档”“原文提到”等套话。
6. 不要生成需要看图、看示意图或看表格才能回答的问题，除非文档文字已明确描述。
7. 题目之间不得重复或同义改写；每题都必须在文档中有明确依据。
8. 生成后自检：如果某题在文档中找不到直接依据，换一个段落重新出题，最终仍然必须凑满 {question_num} 条。

【文档内容开始】
{document_text}
【文档内容结束】

请只输出符合指定结构化格式的结果。"""


def _extract_json_object(text: str) -> str:
    """从可能带 Markdown 代码围栏的 LLM 输出中截取 JSON 对象。

    Args:
        text: LLM 原始输出。

    Returns:
        JSON 对象字符串。

    Raises:
        ValueError: 输出中找不到 JSON 对象。
    """
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM 输出中没有 JSON 对象")
    return stripped[start : end + 1]


def _invoke_question_llm(prompt: str) -> GeneratedQASet:
    """调用项目 LLM 生成题目，优先结构化输出，失败时回退 JSON 文本解析。

    Args:
        prompt: 题目生成提示词。

    Returns:
        解析后的题目集合。

    Raises:
        Exception: 结构化输出和 JSON 回退都失败时抛出。
    """
    try:
        structured_llm = model.get_llm().with_structured_output(GeneratedQASet)
        result = structured_llm.invoke(prompt)
        if isinstance(result, dict):
            return GeneratedQASet.model_validate(result)
        if isinstance(result, GeneratedQASet):
            return result
        return GeneratedQASet.model_validate(result)
    except Exception as structured_exc:  # noqa: BLE001 - 尝试 JSON 文本回退
        print(f"    结构化输出失败，回退 JSON 解析: {structured_exc}")
        raw = (
            model.get_llm()
            .invoke(
                prompt
                + "\n\n如果无法使用结构化输出，请直接输出 JSON，"
                + '格式为 {"questions": [{"question": "...", "ground_truth": "..."}]}。'
            )
            .content
        )
        return GeneratedQASet.model_validate_json(_extract_json_object(raw))


def _validate_generated_questions(
    result: GeneratedQASet | dict[str, Any],
    question_num: int,
) -> list[dict[str, str]]:
    """校验 LLM 生成的题目数量、非空性与唯一性。

    Args:
        result: LLM 返回的题目集合。
        question_num: 期望的题目数。

    Returns:
        ``question`` / ``ground_truth`` 字典列表。

    Raises:
        EvalError: 数量不符、字段为空或题目重复。
    """
    if isinstance(result, dict):
        result = GeneratedQASet.model_validate(result)
    items = result.questions
    if len(items) != question_num:
        raise EvalError(f"期望生成 {question_num} 条，实际 {len(items)} 条")

    questions: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(items, start=1):
        question = item.question.strip()
        ground_truth = item.ground_truth.strip()
        if not question or not ground_truth:
            raise EvalError(f"第 {index} 条生成结果的 question/ground_truth 为空")
        normalized = re.sub(r"\s+", "", question)
        if normalized in seen:
            raise EvalError(f"第 {index} 条问题重复: {question!r}")
        seen.add(normalized)
        questions.append({"question": question, "ground_truth": ground_truth})
    return questions


def _generate_questions_with_llm(
    document_text: str,
    question_num: int,
    doc_name: str,
) -> list[dict[str, str]]:
    """调用 LLM 生成题目，最多重试 3 次。

    Args:
        document_text: 样本文档文本。
        question_num: 需要生成的题目数。
        doc_name: 文档名称。

    Returns:
        校验通过的题目列表。

    Raises:
        EvalError: 连续 3 次生成或校验失败。
    """
    base_prompt = _build_question_generation_prompt(
        document_text, question_num, doc_name
    )
    last_error = ""
    for attempt in range(1, 4):
        prompt = base_prompt
        if attempt > 1:
            prompt += (
                f"\n\n【上次生成不合格】{last_error}。"
                f"请重新生成，必须正好 {question_num} 条，且题目不得重复。"
            )
        try:
            result = _invoke_question_llm(prompt)
            return _validate_generated_questions(result, question_num)
        except Exception as exc:  # noqa: BLE001 - 重试后统一报错
            last_error = str(exc)
            print(f"    第 {attempt}/3 次题目生成失败: {last_error}")
    raise EvalError(f"连续 3 次生成题目失败: {last_error}")


def _write_questions_csv(questions: list[dict[str, str]], output_path: Path) -> Path:
    """把生成的题目写入 ``question,ground_truth`` CSV。

    Args:
        questions: 题目列表。
        output_path: 输出 CSV 路径。

    Returns:
        实际写入的绝对路径。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["question", "ground_truth"],
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(questions)
    except OSError as exc:
        raise EvalError(f"写入问题文件失败: {output_path} -> {exc}") from exc
    return output_path.resolve()


def step_1_resolve_target_document(doc_title: str) -> TargetDocument | None:
    """解析并打印本次评估限定的目标文档。

    Args:
        doc_title: 目标文档标题子串；空字符串表示不做范围限制。

    Returns:
        目标文档；``doc_title`` 为空时返回 ``None``。
    """
    if not doc_title:
        print("检索范围: 全库（未限定文档）")
        return None

    target = _resolve_target_document(doc_title)
    print(f"检索范围: 《{target.file_title}》(doc_id={target.doc_id})")
    return target


def step_2_generate_questions_from_document(
    sample_doc: Path,
    question_num: int,
    output_path: Path,
) -> list[dict[str, str]]:
    """从 Markdown / PDF 样本文档生成评估题目并写入 CSV。

    Args:
        sample_doc: 样本文档路径。
        question_num: 需要生成的题目数量。
        output_path: 题目 CSV 输出路径。

    Returns:
        生成并校验通过的题目列表。

    Raises:
        EvalError: 文档读取、LLM 生成或 CSV 写入失败。
    """
    if not ENV_CONFIG.dashscope.api_key:
        raise EvalError("未配置 DASHSCOPE_API_KEY，无法调用 LLM 生成题目")

    print(f"读取样本文档: {sample_doc}")
    text = _read_sample_document(sample_doc)
    excerpt = _select_document_excerpt(text)
    print(f"文档文本: {len(text)} 字符；送入题目生成的文本: {len(excerpt)} 字符")

    questions = _generate_questions_with_llm(
        excerpt,
        question_num,
        sample_doc.stem,
    )
    absolute_path = _write_questions_csv(questions, output_path)
    print(f"已生成 {len(questions)} 条题目: {absolute_path}")
    for index, item in enumerate(questions, start=1):
        print(f"  {index}. {item['question']}")
    return questions


def step_3_load_eval_questions(path: Path) -> list[dict[str, str]]:
    """读取并校验评估问题 CSV。

    Args:
        path: CSV 路径，必须包含 ``question`` 与 ``ground_truth`` 两列。

    Returns:
        去除首尾空白后的题目列表。

    Raises:
        EvalError: 文件不存在、表头缺失、存在空值或重复问题。
    """
    if not path.is_file():
        raise EvalError(f"问题文件不存在: {path}")

    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames or []
        missing = {"question", "ground_truth"} - set(fieldnames)
        if missing:
            raise EvalError(f"问题文件缺少列 {sorted(missing)}，实际表头: {fieldnames}")

        questions: list[dict[str, str]] = []
        seen: set[str] = set()
        for line_no, row in enumerate(reader, start=2):
            question = (row.get("question") or "").strip()
            ground_truth = (row.get("ground_truth") or "").strip()
            if not question or not ground_truth:
                raise EvalError(f"第 {line_no} 行的 question/ground_truth 为空")
            if question in seen:
                raise EvalError(f"第 {line_no} 行问题重复: {question!r}")
            seen.add(question)
            questions.append({"question": question, "ground_truth": ground_truth})

    if not questions:
        raise EvalError(f"问题文件为空: {path}")
    return questions


def step_4_run_rag_pipeline(
    questions: list[dict[str, str]],
    target: TargetDocument | None,
    *,
    enable_web_search: bool,
    enable_hyde: bool,
) -> list[EvalRecord]:
    """执行全部问题的 RAG 流程并收集 answer / context。

    Args:
        questions: 题目列表。
        target: 限定检索的目标文档；``None`` 表示全库检索。
        enable_web_search: 是否启用网络搜索。
        enable_hyde: 是否启用 HyDE。

    Returns:
        与题目顺序一致的 RAG 运行结果。
    """
    print(
        f"开始执行 RAG 流程: {len(questions)} 题, "
        f"web_search={enable_web_search}, hyde={enable_hyde}"
    )
    with _scoped_milvus(target):
        return asyncio.run(
            _arun_all_queries(
                questions,
                enable_web_search=enable_web_search,
                enable_hyde=enable_hyde,
            )
        )


def step_5_build_ragas_dataset(records: list[EvalRecord]) -> EvaluationDataset:
    """把 RAG 运行结果转换为 Ragas 单轮评估数据集。

    Args:
        records: RAG 运行结果列表。

    Returns:
        每个样本包含 ``user_input`` / ``response`` / ``retrieved_contexts``
        / ``reference`` 四个 Ragas 标准字段。
    """
    samples = [
        SingleTurnSample(
            user_input=record.question,
            response=record.answer,
            retrieved_contexts=record.contexts,
            reference=record.ground_truth,
        )
        for record in records
    ]
    return EvaluationDataset(samples=samples)


def step_6_build_ragas_components(
    *,
    max_workers: int,
    timeout: float,
) -> tuple[Any, Any, list[Any], RunConfig]:
    """构造 Ragas 的 LLM、Embedding、指标与运行配置。

    Args:
        max_workers: Ragas 并发评估的 worker 数。
        timeout: 单个指标调用的超时时间（秒）。

    Returns:
        ``(llm, embeddings, metrics, run_config)``。

    Raises:
        EvalError: 未配置 DashScope API Key。
    """
    if not ENV_CONFIG.dashscope.api_key:
        raise EvalError("未配置 DASHSCOPE_API_KEY，无法调用评估模型")

    run_config = RunConfig(max_workers=max_workers, timeout=timeout)
    # bypass_n: DashScope 兼容接口只支持 n=1，而 Answer Relevancy 默认
    # 一次生成 3 个问题；bypass_n 会拆成 3 次单条请求。
    # bypass_temperature: 不在调用前改写项目模型实例的 temperature。
    llm = LangchainLLMWrapper(
        model.get_llm(),
        run_config=run_config,
        bypass_n=True,
        bypass_temperature=True,
    )
    embeddings = LangchainEmbeddingsWrapper(ProjectEmbeddings())
    metrics = [
        Faithfulness(),
        AnswerRelevancy(),
        ContextPrecision(),
        ContextRecall(),
        AnswerCorrectness(),
    ]
    return llm, embeddings, metrics, run_config


def step_7_run_ragas_evaluation(
    dataset: EvaluationDataset,
    *,
    llm: Any,
    embeddings: Any,
    metrics: list[Any],
    run_config: RunConfig,
    raise_exceptions: bool,
) -> EvaluationResult:
    """调用 Ragas 计算五项指标。

    Args:
        dataset: Ragas 评估数据集。
        llm: Ragas LLM wrapper。
        embeddings: Ragas Embedding wrapper。
        metrics: 指标实例列表。
        run_config: Ragas 运行配置。
        raise_exceptions: 单个指标失败时是否立即抛异常；``False`` 时写 NaN。

    Returns:
        Ragas 评估结果。
    """
    print("开始 Ragas 评估（5 项指标）...")
    return evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=llm,
        embeddings=embeddings,
        run_config=run_config,
        raise_exceptions=raise_exceptions,
        show_progress=True,
    )


def _score_for_csv(value: Any) -> Any:
    """把 Ragas 分数转换为 CSV 可写值。

    Args:
        value: 原始分数，可能是 float、NaN 或 None。

    Returns:
        NaN 转为字符串 ``"nan"``，``None`` 转为空字符串，其余原样返回。
    """
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return "nan"
    return value


def step_8_write_eval_result(
    records: list[EvalRecord],
    result: EvaluationResult,
    output_path: Path,
) -> Path:
    """把 RAG 运行结果与 Ragas 分数合并写入 CSV。

    Args:
        records: RAG 运行结果，顺序必须与评估数据集一致。
        result: Ragas 评估结果。
        output_path: 输出 CSV 路径。

    Returns:
        实际写入的绝对路径。

    Raises:
        EvalError: Ragas 返回的分数行数与题目数不一致。
    """
    scores = result.scores
    if len(scores) != len(records):
        raise EvalError(f"Ragas 分数行数 {len(scores)} 与题目数 {len(records)} 不一致")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=OUTPUT_COLUMNS,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for record, score_row in zip(records, scores, strict=True):
            row: dict[str, Any] = {
                "question": record.question,
                "context": record.context_text,
                "Answer": record.answer,
                "ground_truth": record.ground_truth,
            }
            for metric_key, column_name in METRIC_COLUMNS.items():
                row[column_name] = _score_for_csv(
                    score_row.get(metric_key, float("nan"))
                )
            writer.writerow(row)

    absolute_path = output_path.resolve()
    print(f"评估结果已写入: {absolute_path}")
    return absolute_path


def _metric_averages(result: EvaluationResult) -> dict[str, tuple[float, int]]:
    """计算各指标的有效均值和有效题数。

    Args:
        result: Ragas 评估结果。

    Returns:
        ``{metric_key: (mean, valid_count)}``；没有有效值时均值为 NaN。
    """
    averages: dict[str, tuple[float, int]] = {}
    for metric_key in METRIC_COLUMNS:
        values = [
            float(row[metric_key])
            for row in result.scores
            if isinstance(row.get(metric_key), (int, float))
            and math.isfinite(float(row[metric_key]))
        ]
        mean = sum(values) / len(values) if values else float("nan")
        averages[metric_key] = (mean, len(values))
    return averages


def _context_stats(records: list[EvalRecord]) -> tuple[float, int]:
    """统计平均上下文条数与空上下文题数。

    Args:
        records: RAG 运行结果。

    Returns:
        ``(平均条数, 空上下文题数)``。
    """
    total = len(records)
    if not total:
        return 0.0, 0
    average = sum(len(record.contexts) for record in records) / total
    empty = sum(1 for record in records if not record.contexts)
    return average, empty


def _format_score(value: Any) -> str:
    """把分数格式化为报告中的 4 位小数；缺失或 NaN 显示为 ``nan``。"""
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(number):
        return "nan"
    return f"{number:.4f}"


def _md_cell(value: Any) -> str:
    """转义 Markdown 表格单元格中的竖线和换行。"""
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _md_fence(text: str) -> str:
    """用足够长的反引号围栏包裹可能含反引号的文本。"""
    longest = max(
        (len(match.group(0)) for match in re.finditer(r"`+", text)), default=0
    )
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text}\n{fence}"


def _has_low_score(score_row: dict[str, Any]) -> bool:
    """判断一行分数中是否存在低于阈值或缺失的指标。"""
    for metric_key in METRIC_COLUMNS:
        value = score_row.get(metric_key)
        if not isinstance(value, (int, float)):
            return True
        number = float(value)
        if not math.isfinite(number) or number < LOW_SCORE_THRESHOLD:
            return True
    return False


def step_9_write_markdown_report(
    records: list[EvalRecord],
    result: EvaluationResult,
    output_path: Path,
    meta: RunMeta,
) -> Path:
    """生成便于人工阅读的 Markdown 评估报告。

    Args:
        records: RAG 运行结果。
        result: Ragas 评估结果。
        output_path: 报告输出路径。
        meta: 本次运行的配置元信息。

    Returns:
        实际写入的绝对路径。

    Raises:
        EvalError: 分数行数不一致或报告写入失败。
    """
    if len(result.scores) != len(records):
        raise EvalError("生成报告时发现分数行数与题目数不一致")

    averages = _metric_averages(result)
    average_contexts, empty_contexts = _context_stats(records)
    target_title = (
        f"《{meta.target.file_title}》" if meta.target else "全库（未限定文档）"
    )
    sample_doc_text = (
        f"`{meta.sample_doc.resolve()}`（自动生成题目）"
        if meta.sample_doc is not None
        else "未提供（复用已有题目）"
    )
    generated_text = "是" if meta.generated_questions else "否"

    lines: list[str] = [
        "# RAG 评估报告",
        "",
        f"- 生成时间：{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"- 评估模型：`{ENV_CONFIG.dashscope.llm_model}`",
        f"- 样本文档：{sample_doc_text}",
        f"- 问题文件：`{meta.question_file.resolve()}`",
        f"- 问题是否自动生成：{generated_text}",
        f"- 本次评估题数：{len(records)}",
        f"- 检索范围：{target_title}",
        f"- 检索开关：web_search={meta.enable_web_search}, hyde={meta.enable_hyde}",
        "",
        "## 指标汇总",
        "",
        "| 指标 | 均值 | 有效题数 |",
        "| --- | ---: | ---: |",
    ]
    for metric_key, column_name in METRIC_COLUMNS.items():
        mean, valid = averages[metric_key]
        lines.append(
            f"| {column_name} | {_format_score(mean)} | {valid}/{len(records)} |"
        )

    lines.extend(
        [
            "",
            f"- 上下文：平均 {average_contexts:.2f} 条/题，"
            f"空上下文 {empty_contexts}/{len(records)} 题",
            "",
            "## 逐题得分",
            "",
            "| # | 问题 | " + " | ".join(METRIC_COLUMNS.values()) + " |",
            "| ---: | --- | " + " | ".join("---:" for _ in METRIC_COLUMNS) + " |",
        ]
    )
    for index, (record, score_row) in enumerate(
        zip(records, result.scores, strict=True), start=1
    ):
        metric_cells = " | ".join(
            _format_score(score_row.get(metric_key)) for metric_key in METRIC_COLUMNS
        )
        lines.append(f"| {index} | {_md_cell(record.question)} | {metric_cells} |")

    lines.extend(["", "## 低分题", ""])
    low_items: list[tuple[int, EvalRecord, float]] = []
    for index, (record, score_row) in enumerate(
        zip(records, result.scores, strict=True), start=1
    ):
        if not _has_low_score(score_row):
            continue
        finite_values = [
            float(score_row[metric_key])
            for metric_key in METRIC_COLUMNS
            if isinstance(score_row.get(metric_key), (int, float))
            and math.isfinite(float(score_row[metric_key]))
        ]
        lowest = min(finite_values) if finite_values else float("nan")
        low_items.append((index, record, lowest))
    if low_items:
        lines.append(
            f"以下题目至少一项指标低于 {LOW_SCORE_THRESHOLD:.2f} 或缺失，"
            "建议优先检查检索召回与答案生成："
        )
        lines.append("")
        for index, record, lowest in low_items:
            lines.append(
                f"- 第 {index} 题：{record.question}（最低指标 {_format_score(lowest)}）"
            )
    else:
        lines.append("无低于阈值的题目。")

    lines.extend(["", "## 逐题详情", ""])
    for index, (record, score_row) in enumerate(
        zip(records, result.scores, strict=True), start=1
    ):
        metric_text = " · ".join(
            f"`{column_name}={_format_score(score_row.get(metric_key))}`"
            for metric_key, column_name in METRIC_COLUMNS.items()
        )
        lines.extend(
            [
                f"### {index}. {record.question}",
                "",
                f"**指标**：{metric_text}",
                "",
                "**Ground Truth**",
                "",
                "> " + record.ground_truth.replace("\n", "\n> "),
                "",
                "**Answer**",
                "",
                record.answer or "（空）",
                "",
                f"**Context（{len(record.contexts)} 条）**",
                "",
                "<details>",
                "<summary>展开上下文</summary>",
                "",
                _md_fence(record.context_text or "（空）"),
                "",
                "</details>",
                "",
            ]
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    except OSError as exc:
        raise EvalError(f"写入评估报告失败: {output_path} -> {exc}") from exc

    absolute_path = output_path.resolve()
    print(f"评估报告已写入: {absolute_path}")
    return absolute_path


def step_10_print_summary(
    records: list[EvalRecord],
    result: EvaluationResult,
) -> None:
    """在终端打印各指标均值与上下文覆盖情况。

    Args:
        records: RAG 运行结果。
        result: Ragas 评估结果。
    """
    print("\n===== Ragas 评估汇总 =====")
    averages = _metric_averages(result)
    for metric_key, column_name in METRIC_COLUMNS.items():
        mean, valid = averages[metric_key]
        print(f"{column_name:<20} mean={mean:.4f} valid={valid}/{len(records)}")

    average_contexts, empty_contexts = _context_stats(records)
    print(
        f"上下文: 平均 {average_contexts:.2f} 条/题, "
        f"空上下文 {empty_contexts}/{len(records)} 题"
    )


def _configure_logging(verbose: bool) -> None:
    """按需静音项目内部 DEBUG 日志，保留 Ragas 进度条与脚本输出。

    Args:
        verbose: 为 ``True`` 时保留项目节点日志。
    """
    if verbose:
        return
    for module_name in ("api", "common", "graphs", "service"):
        logger.disable(module_name)


def _positive_int(value: str) -> int:
    """argparse 类型转换：只接受正整数。

    Args:
        value: 命令行原始字符串。

    Returns:
        正整数。

    Raises:
        argparse.ArgumentTypeError: 值不是正整数。
    """
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"必须是正整数，实际为 {value}")
    return parsed


def _determine_doc_title(args: argparse.Namespace) -> str:
    """决定 Milvus 检索范围使用的文档标题。

    优先级：``--no-doc-scope`` > 显式 ``--doc-title`` > 样本文档文件名 >
    内置默认文档。样本文档文件名通常与 Milvus 里的 ``file_title`` 接近，
    例如 fixture PDF 的 stem 就是完整标题。

    Args:
        args: 已解析的命令行参数。

    Returns:
        文档标题子串；空字符串表示全库检索。
    """
    if args.no_doc_scope:
        return ""
    if args.doc_title is not None:
        return args.doc_title
    if args.sample_doc is not None:
        return args.sample_doc.stem
    return DEFAULT_DOC_TITLE


def _build_arg_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。

    Returns:
        配置好的 ``ArgumentParser``。
    """
    parser = argparse.ArgumentParser(
        description=(
            "从 Markdown/PDF 样本文档生成评估题目，运行 MiniRAG，"
            "再用 Ragas 打分并输出 CSV 与 Markdown 报告"
        ),
    )
    parser.add_argument(
        "--sample_doc",
        "--sample-doc",
        dest="sample_doc",
        type=Path,
        default=None,
        help="样本文档路径（.md / .markdown / .pdf）；提供时先从文档生成题目",
    )
    parser.add_argument(
        "--question_num",
        "--question-num",
        dest="question_num",
        type=_positive_int,
        default=DEFAULT_QUESTION_NUM,
        help=f"从样本文档生成的题目数量（默认 {DEFAULT_QUESTION_NUM}）",
    )
    parser.add_argument(
        "--question",
        "--questions",
        dest="questions",
        type=Path,
        default=DEFAULT_QUESTIONS_PATH,
        help=f"问题 CSV 路径（默认 {DEFAULT_QUESTIONS_PATH}）",
    )
    parser.add_argument(
        "--result",
        "--output",
        dest="output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"评估结果 CSV 路径（默认 {DEFAULT_OUTPUT_PATH}）",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help=f"Markdown 评估报告路径（默认 {DEFAULT_REPORT_PATH}）",
    )
    parser.add_argument(
        "--doc-title",
        default=None,
        help=(
            "限定检索的文档标题子串；默认用样本文档文件名，"
            "未提供样本文档时用内置华为指南标题；传空字符串表示全库检索"
        ),
    )
    parser.add_argument(
        "--no-doc-scope",
        action="store_true",
        help="不限定检索文档，按全库检索评估（等价于 --doc-title ''）",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=None,
        help="只评估前 N 题，用于冒烟",
    )
    parser.add_argument(
        "--max-workers",
        type=_positive_int,
        default=2,
        help="Ragas 并发 worker 数（默认 2）",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="单项指标超时秒数（默认 180）",
    )
    parser.add_argument(
        "--web-search",
        action="store_true",
        help="打开网络搜索分支（默认关闭，保证文档内评估可复现）",
    )
    parser.add_argument(
        "--hyde",
        action="store_true",
        help="打开 HyDE 检索分支（默认关闭）",
    )
    parser.add_argument(
        "--raise-exceptions",
        action="store_true",
        help="任一指标失败即抛异常（默认写 NaN 并继续）",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="保留项目节点 DEBUG 日志",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """评估入口：生成/读取题目、运行 RAG、Ragas 打分、输出 CSV 与报告。

    Args:
        argv: 命令行参数；``None`` 时读取 ``sys.argv``。

    Returns:
        进程退出码：0 成功，2 可预期错误。
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    print("=" * 72)
    print("Ragas RAG 评估")
    print(f"Ragas 版本: {ragas.__version__}")
    print(f"样本文档: {args.sample_doc or '未提供（复用已有题目）'}")
    print(f"问题文件: {args.questions}")
    print(f"结果文件: {args.output}")
    print(f"报告文件: {args.report}")
    print(
        f"评估限制: limit={args.limit or '全部'}, "
        f"workers={args.max_workers}, question_num={args.question_num}"
    )
    print("=" * 72)

    try:
        doc_title = _determine_doc_title(args)
        target = step_1_resolve_target_document(doc_title)
        generated_questions = args.sample_doc is not None
        if args.sample_doc is not None:
            step_2_generate_questions_from_document(
                args.sample_doc,
                args.question_num,
                args.questions,
            )
        elif args.question_num != DEFAULT_QUESTION_NUM:
            print("提示: 未提供 --sample_doc，忽略 --question_num")

        questions = step_3_load_eval_questions(args.questions)
        if args.limit is not None:
            questions = questions[: args.limit]
        records = step_4_run_rag_pipeline(
            questions,
            target,
            enable_web_search=args.web_search,
            enable_hyde=args.hyde,
        )
        dataset = step_5_build_ragas_dataset(records)
        llm, embeddings, metrics, run_config = step_6_build_ragas_components(
            max_workers=args.max_workers,
            timeout=args.timeout,
        )
        result = step_7_run_ragas_evaluation(
            dataset,
            llm=llm,
            embeddings=embeddings,
            metrics=metrics,
            run_config=run_config,
            raise_exceptions=args.raise_exceptions,
        )
        step_8_write_eval_result(records, result, args.output)
        step_9_write_markdown_report(
            records,
            result,
            args.report,
            RunMeta(
                sample_doc=args.sample_doc,
                question_file=args.questions,
                target=target,
                generated_questions=generated_questions,
                enable_web_search=args.web_search,
                enable_hyde=args.hyde,
            ),
        )
        step_10_print_summary(records, result)
    except EvalError as exc:
        print(f"\n评估失败: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
