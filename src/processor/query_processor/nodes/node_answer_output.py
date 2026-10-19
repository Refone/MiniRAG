import html
import re

from regex import R

from common.config.app_config import APP_CONFIG
from common.prompt.prompt_remove_item_names import PromptRerankQuerySanitizer
from processor.query_processor.chat_history import chat_history_manager, MessageRole
from utils.node_utils import trace_node
from common.prompt.prompt_final_answer import PromptFinalAnswer
from utils.logging_utils import logger
import time
from processor.query_processor.state import DataFrom, QueryGraphState, RerankResult
from common.model import LLM, RERANKER
from utils.sse_utils import SSEEvent, sse_push


def step_1_validate_and_get_data(state: QueryGraphState):
    answer = state.get("answer")
    session_id = state.get("session_id")
    rewritten_query = state.get("rewritten_query")
    confirm_list = state.get("confirm_list")
    rerank_results = state.get("rerank_results")

    return answer, session_id, rewritten_query, confirm_list, rerank_results


def step_2_format_prompt(
    rewritten_query: str, session_id: str, rerank_results: list[RerankResult]
) -> str:

    history_summary = chat_history_manager.summary_history(session_id=session_id)

    reference = ""
    for docs in rerank_results:
        reference += (
            f"---\n"
            f"数据来源: {docs['data_from']}, 置信度: {docs['score']:0.8f},\n"
            f"内容: {docs['document']}\n\n"
            f"---\n"
        )

    return PromptFinalAnswer(
        reference=reference, history=history_summary, question=rewritten_query
    ).prompt


def step_3_call_llm_generate_answer(session_id: str, answer_prompt: str) -> str:
    answer = ""

    for chunk in LLM.stream(answer_prompt):
        chunk_str = chunk.content
        sse_push(
            sse_id=session_id,
            event=SSEEvent.DELTA,
            data={
                "delta": chunk_str,
            },
        )
        answer += chunk_str

    return answer


def _remove_item_name_from_query(query: str, confirm_list: list[str]) -> str:
    """移除 query 中的关键字，以避免干扰图片 rerank。"""
    prompt = PromptRerankQuerySanitizer(
        query=query,
        item_names=confirm_list,
    ).prompt
    clean_query = LLM.invoke(prompt).content
    return clean_query


def step_4_collect_images(
    rerank_results: list[RerankResult],
    query_without_item_name: str,
) -> list[str]:
    """从重排序结果中收集要展示给用户的图片。

    过滤策略 (解决"召回的无关图片太多"问题):
    1. 只从 Milvus 切片中取图 (Web 结果不含本地图);
    2. 粗筛: 切片 rerank 分数低于 image_min_chunk_score 的不出图;
    3. 尺寸过滤: 宽高 (像素) 均低于 image_min_width / image_min_height 的
        icon 小图不出图。尺寸由导入时写入 Markdown (title / width / height
        属性), 查询时零成本解析; 解析不到尺寸时兜底保留 (历史数据或切片截断);
    4. 精排: 将图片描述 (markdown 方括号中的 alt 文本或 <img> 标签的 alt
       属性, 导入时为 VLM 生成的图片摘要) 与 rewritten_query 做图片级 rerank,
       分数低于 image_min_rerank_score 的图片直接丢弃。这一步解决"切片文本相关但
       其中某张图无关"的问题 (如含产品名的标题页 LOGO 图);
    5. 按图片级 rerank 分数降序, 保证最相关的图优先;
    6. 去重 (重叠切片可能包含同一张图, 同 URL 保留分数更高切片中的描述,
        重复出现时补全缺失的尺寸信息);
    7. 总数不超过 image_max_count。
    """
    if not rerank_results:
        return []

    # 方括号捕获图片描述 (alt 文本), 圆括号捕获 URL, 可选 title 属性携带 "宽x高"
    image_re = re.compile(
        r"!\[(?P<desc>.*?)\]\((?P<url>.*?)(?:\s+(?P<title>\"[^\"]*\"|'[^']*'))?\)"
    )
    # HTML <img> 标签语法: src 为图片 URL, alt 为图片描述, width/height 为像素尺寸
    img_tag_re = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
    # src/alt/width/height 属性值 (带双引号/单引号/不带引号三种写法)
    img_attr_re = {
        "src": re.compile(
            r"(?<=\s)src\s*=\s*(?:\"(?P<dq>[\s\S]*?)\"|'(?P<sq>[\s\S]*?)'|(?P<uq>[^\s>]*))",
            re.IGNORECASE,
        ),
        "alt": re.compile(
            r"(?<=\s)alt\s*=\s*(?:\"(?P<dq>[\s\S]*?)\"|'(?P<sq>[\s\S]*?)'|(?P<uq>[^\s>]*))",
            re.IGNORECASE,
        ),
        "width": re.compile(
            r"(?<=\s)width\s*=\s*(?:\"(?P<dq>[\s\S]*?)\"|'(?P<sq>[\s\S]*?)'|(?P<uq>[^\s>]*))",
            re.IGNORECASE,
        ),
        "height": re.compile(
            r"(?<=\s)height\s*=\s*(?:\"(?P<dq>[\s\S]*?)\"|'(?P<sq>[\s\S]*?)'|(?P<uq>[^\s>]*))",
            re.IGNORECASE,
        ),
    }

    def _attr_value(match: re.Match) -> str:
        """从 src/alt/width/height 属性匹配结果中取出属性值。"""
        return match.group("dq") or match.group("sq") or match.group("uq") or ""

    def _parse_int(value: str) -> int:
        """宽松解析像素尺寸, 解析失败返回 0 (未知)。"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _title_size(title: str | None) -> tuple[int, int]:
        """解析 Markdown title 属性中的 '宽x高' 尺寸, 未知返回 (0, 0)。"""
        if not title:
            return (0, 0)
        parts = title.strip().strip("\"'").lower().split("x")
        if len(parts) != 2:
            return (0, 0)
        return _parse_int(parts[0]), _parse_int(parts[1])

    def _is_unknown_size(size: tuple[int, int]) -> bool:
        return size[0] <= 0 or size[1] <= 0

    # ---- 1. 粗筛: 只看 Milvus 且切片分数达标的候选, 按切片分数降序 ----
    pre_filtered = sorted(
        (
            doc
            for doc in rerank_results
            if doc["data_from"] == DataFrom.MILVUS
            and doc.get("score", 0.0) >= APP_CONFIG.image_min_chunk_score
        ),
        key=lambda doc: doc.get("score", 0.0),
        reverse=True,
    )
    dropped = sum(1 for d in rerank_results if d["data_from"] == DataFrom.MILVUS) - len(
        pre_filtered
    )
    if dropped:
        logger.info(
            f"图片粗筛: {dropped} 个切片低于分数门槛 "
            f"{APP_CONFIG.image_min_chunk_score}, 不参与图片精排"
        )

    # ---- 2. 提取 (描述, URL, 切片分数, 尺寸), 按 URL 去重 ----
    images: list[tuple[str, str, float, tuple[int, int]]] = []
    seen_urls: set[str] = set()
    idx_by_url: dict[str, int] = {}

    def _record_image(
        desc: str, url: str, chunk_score: float, size: tuple[int, int]
    ) -> None:
        """按 URL 去重收录; 同一 URL 重复出现时补全缺失的尺寸信息。"""
        if url in seen_urls:
            idx = idx_by_url[url]
            if _is_unknown_size(images[idx][3]) and not _is_unknown_size(size):
                images[idx] = (images[idx][0], url, images[idx][2], size)
            return
        seen_urls.add(url)
        idx_by_url[url] = len(images)
        images.append((desc, url, chunk_score, size))

    for doc in pre_filtered:
        chunk_score = doc.get("score", 0.0)
        document = doc["document"]
        # 2.1 Markdown 语法 ![描述](url "宽x高")
        for match in image_re.finditer(document):
            _record_image(
                match.group("desc").strip(),
                match.group("url"),
                chunk_score,
                _title_size(match.group("title")),
            )
        # 2.2 HTML 语法 <img src="url" width=".." height=".." alt="描述">
        for tag_match in img_tag_re.finditer(document):
            src_match = img_attr_re["src"].search(tag_match.group(0))
            if not src_match:
                continue
            url = _attr_value(src_match)
            if not url:
                continue
            alt_match = img_attr_re["alt"].search(tag_match.group(0))
            desc = html.unescape(_attr_value(alt_match)) if alt_match else ""
            width_match = img_attr_re["width"].search(tag_match.group(0))
            height_match = img_attr_re["height"].search(tag_match.group(0))
            size = (
                _parse_int(_attr_value(width_match)) if width_match else 0,
                _parse_int(_attr_value(height_match)) if height_match else 0,
            )
            _record_image(desc.strip(), url, chunk_score, size)
    if not images:
        return []

    # ---- 3. 尺寸过滤: 剔除宽高均低于阈值的 icon 小图 ----
    if APP_CONFIG.image_min_width > 0 and APP_CONFIG.image_min_height > 0:
        kept: list[tuple[str, str, float, tuple[int, int]]] = []
        for desc, url, chunk_score, size in images:
            width, height = size
            if (
                not _is_unknown_size(size)
                and width < APP_CONFIG.image_min_width
                and height < APP_CONFIG.image_min_height
            ):
                logger.debug(
                    f"图片尺寸 {width}x{height} 低于 icon 过滤阈值 "
                    f"{APP_CONFIG.image_min_width}x{APP_CONFIG.image_min_height}, "
                    f"丢弃: {desc[:40]}({url})"
                )
                continue
            kept.append((desc, url, chunk_score, size))
        images = kept
    if not images:
        return []

    # ---- 4. 图片级 rerank: 图片描述 vs 重写后的问题 ----
    # 空描述无法参与 rerank, 用切片分数兜底
    valid_pairs = [(i, desc) for i, (desc, _, _, _) in enumerate(images) if desc]
    score_by_image: dict[int, float] = {}
    if valid_pairs:
        try:
            hits = RERANKER.rerank(
                query=query_without_item_name,
                documents=[desc for _, desc in valid_pairs],
            )
            # rerank 返回的 index 是传入 documents 列表中的下标
            score_by_image = {
                valid_pairs[h["index"]][0]: h["relevance_score"] for h in hits
            }
        except Exception as e:
            logger.warning(f"图片描述 rerank 失败, 退化为切片分数过滤: {e}")

    # ---- 5. 阈值过滤 + 按图片级分数降序 ----
    threshold = APP_CONFIG.image_min_rerank_score
    scored: list[tuple[str, float]] = []
    for idx, (desc, url, chunk_score, _) in enumerate(images):
        image_score = score_by_image.get(idx, chunk_score)
        if image_score < threshold:
            logger.debug(
                f"图片描述 rerank {image_score:.4f} 低于阈值 {threshold}, 丢弃: {desc[:40]}({url})"
            )
        else:
            logger.debug(
                f"图片描述 rerank {image_score:.4f} 高于阈值 {threshold}, 保留: {desc[:40]}({url})"
            )
            scored.append((url, image_score))
    scored.sort(key=lambda x: x[1], reverse=True)

    return [url for url, _ in scored[: APP_CONFIG.image_max_count]]


def step_5_save_message_and_push_final(
    session_id: str, answer: str, image_urls: list[str]
) -> None:
    chat_history_manager.save_message(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        text=answer,
        image_urls=image_urls,
    )

    sse_push(
        sse_id=session_id,
        event=SSEEvent.FINAL,
        data={
            "answer": answer,
            "image_urls": image_urls,
        },
    )


@trace_node(desc="答案输出", need_push=True)
def node_answer_output(state: QueryGraphState) -> QueryGraphState:

    (
        answer,
        session_id,
        rewritten_query,
        confirm_list,
        rerank_results,
    ) = step_1_validate_and_get_data(state)

    if answer:
        step_5_save_message_and_push_final(session_id, answer, [])
    else:
        answer_prompt = step_2_format_prompt(
            rewritten_query, session_id, rerank_results
        )
        logger.info(f"生成的答案提示: {answer_prompt}")

        answer = step_3_call_llm_generate_answer(session_id, answer_prompt)
        logger.info(f"最终答案: {answer}")

        query_without_keywords = _remove_item_name_from_query(
            rewritten_query, confirm_list
        )
        logger.info(f"剔除关键词 {confirm_list} 后的查询: {query_without_keywords}")
        image_urls = step_4_collect_images(rerank_results, query_without_keywords)
        logger.info(f"提取的图片 URL: {image_urls}")
        logger.info(f"共: {len(image_urls)} 张图片")

        step_5_save_message_and_push_final(session_id, answer, image_urls)

    return state


if __name__ == "__main__":
    from rich import print as rprint
    from processor.query_processor.state import load_state, save_state
    from utils.path_utils import PROJECT_ROOT

    prev_state1 = load_state(PROJECT_ROOT / "output/tmp/query_01_intent_recognize.json")
    prev_state2 = load_state(PROJECT_ROOT / "output/tmp/query_05_rrf_and_rerank.json")
    prev_state = {**prev_state1, **prev_state2}
    next_state = node_answer_output(prev_state)
    rprint(next_state)

    new_state_json = str(PROJECT_ROOT / "output/tmp/query_06_answer_output.json")

    save_state(next_state, new_state_json)
    logger.info(f"向量化查询处理完成")
    logger.info(f"状态保存路径: {new_state_json}")
