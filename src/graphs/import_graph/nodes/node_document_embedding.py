import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from common.config.app_config import APP_CONFIG
from common.config.env_config import ENV_CONFIG
from common.events.metering import push_usage_delta
from common.events.tracing import step_log, trace_node
from common.logging import logger
from common.model import EMBEDDING, LLM
from common.model.metering import message_usage_tokens
from common.prompt.prompt_doc_keywords_abstract import (
    DocKeywordsAbstractPydantic,
    PromptDocKeywordsAbstract,
)
from common.schema.token_usage import TokenUsage
from common.store import DOCUMENT_REPO
from common.store.document_repo import DocumentArtifacts
from common.utils.markdown_splitter import Chunk
from graphs.import_graph.import_graph_state import FileType, ImportGraphState

# node_md_img 的产物命名约定: {stem}_fixed.md (原始 md 为 {stem}.md)
from graphs.import_graph.nodes.node_md_img import _MD_FIXED_SUFFIX


@step_log(desc="校验并获取数据")
def step_1_validate_and_get_data(
    state: ImportGraphState,
) -> tuple[str, str, Path, Path, Path, str]:
    task_id = state.get("task_id")
    if not task_id:
        raise ValueError("状态异常: task_id 缺失")

    file_title = state.get("file_title")
    if not file_title:
        raise ValueError("状态异常: file_title 缺失")

    md_path = Path(state.get("markdown_file_path") or "")
    if not md_path.is_file():
        raise FileNotFoundError(f"最终 markdown 文件不存在: {md_path}")

    chunks_path = Path(state.get("chunks_json_path") or "")
    if not chunks_path.is_file():
        raise FileNotFoundError(f"chunks.json 不存在: {chunks_path}")

    origin_file_path = Path(state.get("origin_file_path") or "")
    origin_file_type = state.get("origin_file_type", "")

    return task_id, file_title, md_path, chunks_path, origin_file_path, origin_file_type


@step_log(desc="同名覆盖: 完整删除旧文档数据")
def step_2_delete_old_doc(file_title: str) -> None:
    """同名覆盖：清三制品 + 该标题的全部 chunks/docs（**不动图片目录**）。

    删除顺序由 `DOCUMENT_REPO.delete_by_title` 统一维护（与删除文档接口共用
    一份实现）；本节点只传参与记录。

    注意: 图片目录 (markdown-images/<file_title>/) **不能**在这里清理——
    本节点运行于 node_md_img 之后, 图片已重新上传, 再清理会把本次导入的图片
    删掉 (图片覆盖清理由 node_md_img.step_4 负责; 删除文档接口的图片清理在
    DOCUMENT_REPO.delete_by_id 中, 与导入链路无关)。
    """
    result = DOCUMENT_REPO.delete_by_title(file_title)
    logger.info(
        f"旧文档完整删除完成: 旧 docs 行数 {result.docs_rows}, "
        f"MinIO 制品 {result.minio_objects} 个"
    )


def _derive_origin_md_path(fixed_md_path: Path) -> Path:
    """zip 分支的 origin 制品取图片修复前的原始 md ({stem}.md)。"""
    if fixed_md_path.stem.endswith(_MD_FIXED_SUFFIX):
        stem = fixed_md_path.stem[: -len(_MD_FIXED_SUFFIX)]
        origin = fixed_md_path.with_name(f"{stem}{fixed_md_path.suffix}")
        if origin.is_file():
            return origin
    return fixed_md_path


@step_log(desc="上传三份制品至 MinIO")
def step_3_upload_artifacts(
    file_title: str,
    md_path: Path,
    chunks_path: Path,
    origin_file_path: Path,
    origin_file_type: str,
) -> DocumentArtifacts:
    """选择 origin 制品并上传三份制品（上传细节在 DOCUMENT_REPO）。

    origin 制品: zip 分支取修复前的原始 md (zip 本身不属于某个分支文档),
    其余类型取原始上传文件。
    """
    if origin_file_type == FileType.MARKDOWN_ZIP:
        origin_path: Path | None = _derive_origin_md_path(md_path)
    else:
        origin_path = origin_file_path

    artifacts = DOCUMENT_REPO.upload_artifacts(
        file_title, origin=origin_path, markdown=md_path, chunks=chunks_path
    )
    logger.info(
        f"三份制品上传完成:\n"
        f"origin: {artifacts.origin_file_url or '(空)'}\n"
        f"markdown: {artifacts.final_markdown_url}\n"
        f"chunks: {artifacts.chunks_url}"
    )
    return artifacts


@step_log(desc="LLM 生成文档关键词与摘要")
def step_4_generate_keywords_abstract(
    file_title: str, md_content: str
) -> tuple[str, str, int]:
    """LLM 生成 docs_keywords / docs_abstract, 失败时回退兜底。

    keywords 的收敛只靠 prompt 约束 (文档指纹原则, 无黑名单后处理);
    LLM 输出为空时回退 file_title。include_raw=True 让返回结构同时携带
    原始消息, usage 直接取自 raw 消息的 usage_metadata。
    """
    prompt = PromptDocKeywordsAbstract(
        file_title=file_title, md_content=md_content
    ).prompt

    keywords, abstract = "", ""
    llm_tokens = 0
    try:
        logger.info("LLM 根据整篇文档生成关键词/摘要，耗时操作...")
        raw_result = LLM.with_structured_output(
            DocKeywordsAbstractPydantic, include_raw=True
        ).invoke(prompt)
        llm_tokens = message_usage_tokens(raw_result["raw"])
        if not llm_tokens:
            logger.warning("关键词/摘要 LLM 未返回 usage, 本次调用不计入统计")

        response = raw_result["parsed"]
        if response is None:
            logger.warning(
                f"关键词/摘要结构化解析失败, 使用兜底值: "
                f"{raw_result.get('parsing_error')}"
            )
        else:
            keywords = (response.keywords or "").strip()
            abstract = (response.abstract or "").strip()
    except Exception as e:
        logger.warning(f"LLM 生成关键词/摘要失败, 使用兜底值: {e}")

    if not keywords:
        keywords = file_title
    if not abstract:
        abstract = md_content[:200]

    logger.info(f"文档元数据: keywords=[{keywords}], abstract=[{abstract}]")
    return keywords, abstract, llm_tokens


def _format_chunk_content(chunk: Chunk) -> str:
    """
    将单个文档切片转换为字符串表示，包含标题层级和内容

    Example:
        {
            "title_stack": ["Chapter 1", "Section 1.1"],
            "content": "This is the content."
        }
        ->
        # Chapter 1
        ## Section 1.1
        This is the content.
    """
    lines = []
    for i, title in enumerate(chunk.get("title_stack", [])):
        if title:
            lines.append("#" * (i + 1) + " " + title)
    lines.append(chunk["content"])
    return "\n".join(lines)


def _vectorize_chunks(
    chunks_list: list[Chunk],
) -> tuple[list[dict[str, Any]], int]:
    """
    对文档切片进行向量化, 返回 (向量数据, 全部批次 embedding token 总数)。

    Returns:
        向量数据与切片按下标一一对应, 每个元素含
        "content" / "dense" / "sparse" 三个键。
    """
    if not chunks_list:
        logger.warning("切片列表为空")
        return [], 0

    batch_size = ENV_CONFIG.dashscope.embedding_batch_size
    batches: list[list[str]] = [
        [_format_chunk_content(chunk) for chunk in chunks_list[i : i + batch_size]]
        for i in range(0, len(chunks_list), batch_size)
    ]

    # 各 worker 独立返回 (向量, token), 无需共享状态或锁
    with ThreadPoolExecutor(max_workers=APP_CONFIG.max_concurrency) as pool:
        batch_results = list(pool.map(EMBEDDING.embed_document_hybrid, batches))

    embedded: list[dict[str, Any]] = []
    total_tokens = 0
    for batch_texts, (batch_vecs, batch_tokens) in zip(batches, batch_results):
        if len(batch_vecs) != len(batch_texts):
            raise ValueError(
                f"向量化结果数量与切片数量不一致: "
                f"切片数={len(batch_texts)}, 向量数={len(batch_vecs)}"
            )
        for text, vec in zip(batch_texts, batch_vecs):
            embedded.append(
                {
                    "content": text,
                    "dense": vec["dense"],
                    "sparse": vec["sparse"],
                }
            )
        total_tokens += batch_tokens

    return embedded, total_tokens


@step_log(desc="向量化文档元数据与切片")
def step_5_vectorize(
    keywords: str,
    abstract: str,
    chunks_list: list[Chunk],
) -> tuple[dict[int, float], list[float], list[dict[str, Any]], int]:
    """docs 元数据双向量 + chunks 批量向量, 返回可写入 Milvus 的数据与 token。"""
    # 一次批调用同时向量化 keywords 与 abstract, 各取所需分量:
    # keywords -> 稀疏 (术语精确匹配), abstract -> 稠密 (语义模糊匹配)
    meta_vecs, meta_tokens = EMBEDDING.embed_document_hybrid([keywords, abstract])
    keywords_sparse = meta_vecs[0]["sparse"]
    abstract_dense = meta_vecs[1]["dense"]

    embedded, chunk_tokens = _vectorize_chunks(chunks_list)
    return keywords_sparse, abstract_dense, embedded, meta_tokens + chunk_tokens


@step_log(desc="写入 minirag_docs 并查回 doc_id")
def step_6_insert_docs_and_query_id(
    task_id: str,
    file_title: str,
    artifacts: DocumentArtifacts,
    keywords: str,
    abstract: str,
    keywords_sparse: dict[int, float],
    abstract_dense: list[float],
) -> int:
    """写入 docs 行并返回 auto_id 主键（pymilvus 版本兼容在 repo 内处理）。"""
    doc_id = DOCUMENT_REPO.save_meta(
        task_id=task_id,
        file_title=file_title,
        artifacts=artifacts,
        keywords=keywords,
        abstract=abstract,
        keywords_sparse=keywords_sparse,
        abstract_dense=abstract_dense,
    )
    logger.info(
        f"文档元数据写入: doc_id=[{doc_id}] keywords=[{keywords}] "
        f"abstract=[{abstract}] 关键词稀疏维度={len(keywords_sparse)} "
        f"摘要稠密维度={len(abstract_dense)}"
    )
    return doc_id


@step_log(desc="写入 minirag_chunks")
def step_7_insert_chunks(
    doc_id: int, file_title: str, embedded: list[dict[str, Any]]
) -> None:
    """将已向量化的切片写入 minirag_chunks（条数校验在 repo 内处理）。"""
    DOCUMENT_REPO.save_chunks(doc_id=doc_id, file_title=file_title, embedded=embedded)


@trace_node(desc="文档嵌入入库", need_push=True)
def node_document_embedding(state: ImportGraphState) -> ImportGraphState:
    """合并节点: 同名覆盖先完整删除旧文档, 再上传制品 + 生成元数据 + 写入两表。

    取代原 node_item_name_vect + node_chunks_vect (见 docs/feat/数据库重构/Milvs DB Refactor.md §4)。
    """
    # 1. 校验并获取数据
    task_id, file_title, md_path, chunks_path, origin_file_path, origin_file_type = (
        step_1_validate_and_get_data(state)
    )

    # 2. 同名覆盖: 先完整删除旧文档 (chunks + docs + MinIO 制品)
    step_2_delete_old_doc(file_title)

    # 3. 上传新三份制品至 MinIO
    artifacts = step_3_upload_artifacts(
        file_title, md_path, chunks_path, origin_file_path, origin_file_type
    )

    # 4. LLM 生成文档关键词与摘要
    md_content = md_path.read_text(encoding="utf-8")
    keywords, abstract, llm_tokens = step_4_generate_keywords_abstract(
        file_title, md_content
    )
    push_usage_delta(task_id, "llm", llm_tokens)

    # 5. 向量化 (docs 元数据 + chunks)
    chunks_list = list(
        map(
            lambda x: Chunk(**x),
            json.loads(chunks_path.read_text(encoding="utf-8")),
        )
    )
    keywords_sparse, abstract_dense, embedded, embedding_tokens = step_5_vectorize(
        keywords, abstract, chunks_list
    )
    push_usage_delta(task_id, "embedding", embedding_tokens)

    # 6. 写入 docs 并查回 doc_id
    doc_id = step_6_insert_docs_and_query_id(
        task_id=task_id,
        file_title=file_title,
        artifacts=artifacts,
        keywords=keywords,
        abstract=abstract,
        keywords_sparse=keywords_sparse,
        abstract_dense=abstract_dense,
    )

    # 7. 写入 chunks
    step_7_insert_chunks(doc_id, file_title, embedded)

    # 只返回本节点计量增量 (不写回其他状态字段):
    # md 压缩包扇出时多个分支会并发执行本节点, 若返回完整 state
    # 会让所有 key 在同一 step 被并发写入, 触发 LangGraph InvalidUpdateError
    return {
        "token_meter": TokenUsage(
            llm_tokens=llm_tokens, embedding_tokens=embedding_tokens
        )
    }


if __name__ == "__main__":
    from rich import print as rprint

    from common.config.path_config import snapshot_path
    from graphs.import_graph.import_graph_state import load_state, save_state

    prev_state = load_state(snapshot_path("import_04_document_split.json"))
    next_state = node_document_embedding(prev_state)

    rprint(next_state)

    new_state_json = snapshot_path("import_05_document_embedding.json")
    save_state(next_state, new_state_json)
    logger.info("文档嵌入入库完成")
    logger.info(f"状态保存路径: {new_state_json}")
