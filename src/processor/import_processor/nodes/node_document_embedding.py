import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from common.config.app_config import APP_CONFIG
from common.prompt.prompt_doc_keywords_abstract import (
    PromptDocKeywordsAbstract,
    DocKeywordsAbstractPydantic,
)
from common.model import LLM, EMBEDDING
from common.client import MILVUS_CLIENT, MINIO_CLIENT
from common.client.milvus_client import MilvusDocsItem, MilvusChunksItem
from common.config.env_config import ENV_CONFIG
from utils.markdown_splitter import Chunk
from utils.node_utils import trace_node, step_log
from utils.logging_utils import logger, brief_list, brief_dict
from processor.import_processor.state import FileType, ImportGraphState

# node_md_img 的产物命名约定: {stem}_fixed.md (原始 md 为 {stem}.md)
from processor.import_processor.nodes.node_md_img import _MD_FIXED_SUFFIX


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
    """按 file_title 找到旧 docs 行, 完整删除旧 chunks / docs / MinIO 制品。

    顺序与方案文档 (docs/feat/数据库重构/Milvs DB Refactor.md §4.3) 一致:
    删除全部完成前不做任何新写入, 避免新旧行并存导致检索双份命中。
    V1-7 起 MinIO 对象路径不含 task_id 层级, 单一前缀即覆盖该标题的
    全部历史制品 (三份制品目录), 同名覆盖语义不变。

    注意: 图片目录 (markdown-images/<file_title>/) **不能**在这里清理——
    本节点运行于 node_md_img 之后, 图片已由 node_md_img 重新上传,
    此处再清理会把本次导入刚上传的图片删掉 (图片的覆盖清理由
    node_md_img.step_4 的 clear_dir_if_exist + 重传完成; 文档删除接口
    的图片清理在 docs_service.delete_doc 中, 与导入链路无关)。
    """
    # 1. 按 file_title 查回旧 docs 行 (同名覆盖判定键)
    old_rows = MILVUS_CLIENT.query_doc_rows_by_file_title(file_title)
    old_ids = [row["id"] for row in old_rows]

    # 2. 清理 MinIO 旧制品: 仅三份制品目录 (origin / markdown / chunks)
    del_cnt = MINIO_CLIENT.clear_doc_artifacts(file_title)

    # 3. 删旧 chunks: 按 doc_id 精确删除; 按 file_title 兜底清理历史遗留行
    MILVUS_CLIENT.delete_chunks_by_doc_ids(old_ids)
    MILVUS_CLIENT.delete_chunks_by_file_title(file_title)

    # 4. 删旧 docs
    MILVUS_CLIENT.delete_docs_by_file_title(file_title)

    logger.info(
        f"旧文档完整删除完成: 旧 docs 行数 {len(old_ids)}, MinIO 制品 {del_cnt} 个"
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
    task_id: str,
    file_title: str,
    md_path: Path,
    chunks_path: Path,
    origin_file_path: Path,
    origin_file_type: str,
) -> tuple[str, str, str]:
    """上传原始文件 / 最终 markdown / chunks.json, 返回三个 URL。

    origin 制品: zip 分支取修复前的原始 md (zip 本身不属于某个分支文档),
    其余类型取原始上传文件。
    """
    if origin_file_type == FileType.MARKDOWN_ZIP:
        origin_path = _derive_origin_md_path(md_path)
    else:
        origin_path = origin_file_path

    origin_url = ""
    if origin_path.is_file():
        origin_url = MINIO_CLIENT.upload_file(
            prefix=MINIO_CLIENT.doc_artifact_prefix(
                ENV_CONFIG.minio.origin_dir, file_title
            ),
            as_name=origin_path.name,
            file_path=str(origin_path),
        )

    markdown_url = MINIO_CLIENT.upload_file(
        prefix=MINIO_CLIENT.doc_artifact_prefix(
            ENV_CONFIG.minio.markdown_dir, file_title
        ),
        as_name=md_path.name,
        file_path=str(md_path),
    )

    chunks_url = MINIO_CLIENT.upload_file(
        prefix=MINIO_CLIENT.doc_artifact_prefix(
            ENV_CONFIG.minio.chunks_dir, file_title
        ),
        as_name=chunks_path.name,
        file_path=str(chunks_path),
    )

    logger.info(
        f"三份制品上传完成:\n"
        f"origin: {origin_url or '(空)'}\n"
        f"markdown: {markdown_url}\n"
        f"chunks: {chunks_url}"
    )
    return origin_url, markdown_url, chunks_url


@step_log(desc="LLM 生成文档关键词与摘要")
def step_4_generate_keywords_abstract(
    file_title: str, md_content: str
) -> tuple[str, str]:
    """LLM 生成 docs_keywords / docs_abstract, 失败时回退兜底。

    keywords 的收敛只靠 prompt 约束 (文档指纹原则, 无黑名单后处理);
    LLM 输出为空时回退 file_title。
    """
    prompt = PromptDocKeywordsAbstract(
        file_title=file_title, md_content=md_content
    ).prompt

    keywords, abstract = "", ""
    try:
        logger.info(f"LLM 根据整篇文档生成关键词/摘要，耗时操作...")
        response = LLM.with_structured_output(DocKeywordsAbstractPydantic).invoke(
            prompt
        )
        keywords = (response.keywords or "").strip()
        abstract = (response.abstract or "").strip()
    except Exception as e:
        logger.warning(f"LLM 生成关键词/摘要失败, 使用兜底值: {e}")

    if not keywords:
        keywords = file_title
    if not abstract:
        abstract = md_content[:200]

    logger.info(f"文档元数据: keywords=[{keywords}], abstract=[{abstract}]")
    return keywords, abstract


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


def _vectorize_chunks(chunks_list: list[Chunk]) -> list[dict[str, Any]]:
    """
    对文档切片进行向量化

    Returns:
        list[dict[str, Any]]: 与切片按下标一一对应的向量数据,
        每个元素含 "content" / "dense" / "sparse" 三个键。
    """
    if not chunks_list:
        logger.warning("切片列表为空")
        return []

    batch_size = ENV_CONFIG.dashscope.embedding_batch_size
    batches: list[list[str]] = [
        [_format_chunk_content(chunk) for chunk in chunks_list[i : i + batch_size]]
        for i in range(0, len(chunks_list), batch_size)
    ]

    with ThreadPoolExecutor(max_workers=APP_CONFIG.max_concurrency) as pool:
        vecs_list = list(pool.map(EMBEDDING.embed_document_hybrid, batches))

    embedded: list[dict[str, Any]] = []
    for batch_texts, batch_vecs in zip(batches, vecs_list):
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

    return embedded


@step_log(desc="向量化文档元数据与切片")
def step_5_vectorize(
    keywords: str,
    abstract: str,
    chunks_list: list[Chunk],
) -> tuple[dict[int, float], list[float], list[dict[str, Any]]]:
    """docs 元数据双向量 + chunks 批量向量, 返回可写入 Milvus 的数据。"""
    # 一次批调用同时向量化 keywords 与 abstract, 各取所需分量:
    # keywords -> 稀疏 (术语精确匹配), abstract -> 稠密 (语义模糊匹配)
    meta_vecs = EMBEDDING.embed_document_hybrid([keywords, abstract])
    keywords_sparse = meta_vecs[0]["sparse"]
    abstract_dense = meta_vecs[1]["dense"]

    embedded = _vectorize_chunks(chunks_list)
    return keywords_sparse, abstract_dense, embedded


@step_log(desc="写入 minirag_docs 并查回 doc_id")
def step_6_insert_docs_and_query_id(
    task_id: str,
    file_title: str,
    origin_file_url: str,
    final_markdown_url: str,
    chunks_url: str,
    keywords: str,
    abstract: str,
    keywords_sparse: dict[int, float],
    abstract_dense: list[float],
) -> int:
    """插入 docs 行并取得自增主键 id。

    pymilvus 3.x 的 insert 会返回 auto_id 生成的主键 (ids), 优先直接使用;
    若返回缺失 (兼容旧版 pymilvus), 按 task_id + file_title 查回兜底。
    """
    ret = MILVUS_CLIENT.insert(
        collection_name=ENV_CONFIG.milvus.collection_docs,
        data=[
            MilvusDocsItem(
                task_id=task_id,
                file_title=file_title,
                origin_file_url=origin_file_url,
                final_markdown_url=final_markdown_url,
                chunks_url=chunks_url,
                created_at=int(time.time() * 1000),
                docs_keywords=keywords,
                docs_abstract=abstract,
                keywords_sparse_vector=keywords_sparse,
                abstract_dense_vector=abstract_dense,
            )
        ],
    )

    insert_count = ret.get("insert_count", 0)
    if insert_count != 1:
        raise RuntimeError(f"写入 minirag_docs 条数不一致: 预期=1, 实际={insert_count}")

    doc_id = None
    ret_ids = ret.get("ids")
    if isinstance(ret_ids, list) and ret_ids:
        doc_id = int(ret_ids[0])
    elif isinstance(ret_ids, int):
        doc_id = ret_ids
    if doc_id is None:
        doc_id = MILVUS_CLIENT.query_doc_id(task_id, file_title)
    if doc_id is None:
        raise RuntimeError(
            f"docs 写入后查回 doc_id 失败: task_id={task_id}, file_title={file_title}"
        )

    logger.success(
        f"文档写入 minirag_docs 完成\n"
        f"doc_id:[{doc_id}] task_id:[{task_id}] file_title:[{file_title}]\n"
        f"keywords:[{keywords}]\n"
        f"abstract:[{abstract}]\n"
        f"keywords_sparse:[{brief_dict(keywords_sparse)}](len={len(keywords_sparse)})\n"
        f"abstract_dense:[{brief_list(abstract_dense)}](len={len(abstract_dense)})"
    )
    return doc_id


@step_log(desc="写入 minirag_chunks")
def step_7_insert_chunks(
    doc_id: int, file_title: str, embedded: list[dict[str, Any]]
) -> None:
    """将已向量化的切片写入 minirag_chunks (携带 doc_id 与 chunk_index)。"""
    if not embedded:
        logger.warning("切片向量列表为空, 直接跳过此步骤")
        return

    ret = MILVUS_CLIENT.insert(
        collection_name=ENV_CONFIG.milvus.collection_chunks,
        data=[
            MilvusChunksItem(
                doc_id=doc_id,
                file_title=file_title,
                chunk_index=index,
                chunk_content=chunk["content"],
                content_dense_vector=chunk["dense"],
                content_sparse_vector=chunk["sparse"],
            )
            for index, chunk in enumerate(embedded)
        ],
    )

    insert_count = ret.get("insert_count", 0)
    if insert_count != len(embedded):
        raise RuntimeError(
            f"写入 minirag_chunks 条数不一致: 预期={len(embedded)}, 实际={insert_count}"
        )

    logger.success(
        f"切片写入 minirag_chunks 完成: doc_id:[{doc_id}] "
        f"file_title:[{file_title}] 切片数:[{insert_count}]"
    )


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
    origin_file_url, final_markdown_url, chunks_url = step_3_upload_artifacts(
        task_id, file_title, md_path, chunks_path, origin_file_path, origin_file_type
    )

    # 4. LLM 生成文档关键词与摘要
    md_content = md_path.read_text(encoding="utf-8")
    keywords, abstract = step_4_generate_keywords_abstract(file_title, md_content)

    # 5. 向量化 (docs 元数据 + chunks)
    chunks_list = list(
        map(
            lambda x: Chunk(**x),
            json.loads(chunks_path.read_text(encoding="utf-8")),
        )
    )
    keywords_sparse, abstract_dense, embedded = step_5_vectorize(
        keywords, abstract, chunks_list
    )

    # 6. 写入 docs 并查回 doc_id
    doc_id = step_6_insert_docs_and_query_id(
        task_id=task_id,
        file_title=file_title,
        origin_file_url=origin_file_url,
        final_markdown_url=final_markdown_url,
        chunks_url=chunks_url,
        keywords=keywords,
        abstract=abstract,
        keywords_sparse=keywords_sparse,
        abstract_dense=abstract_dense,
    )

    # 7. 写入 chunks
    step_7_insert_chunks(doc_id, file_title, embedded)

    # 本节点只有 Milvus / MinIO 副作用, 不写回任何状态字段。
    # 注意: md 压缩包扇出时多个分支会并发执行本节点, 若返回完整 state
    # 会让所有 key 在同一 step 被并发写入, 触发 LangGraph InvalidUpdateError。
    return {}


if __name__ == "__main__":
    from rich import print as rprint
    from processor.import_processor.state import load_state, save_state
    from utils.path_utils import PROJECT_ROOT

    prev_state = load_state(
        str(PROJECT_ROOT / "output/tmp/import_04_document_split.json")
    )
    next_state = node_document_embedding(prev_state)

    rprint(next_state)

    new_state_json = str(PROJECT_ROOT / "output/tmp/import_05_document_embedding.json")
    save_state(next_state, new_state_json)
    logger.info(f"文档嵌入入库完成")
    logger.info(f"状态保存路径: {new_state_json}")
