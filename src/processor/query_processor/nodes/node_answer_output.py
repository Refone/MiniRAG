import html
import re

from regex import R

from common.config.app_config import APP_CONFIG
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
    rerank_results = state.get("rerank_results")

    return answer, session_id, rewritten_query, rerank_results


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


def step_4_collect_images(
    rerank_results: list[RerankResult],
    rewritten_query: str,
) -> list[str]:
    """从重排序结果中收集要展示给用户的图片。

    过滤策略 (解决"召回的无关图片太多"问题):
    1. 只从 Milvus 切片中取图 (Web 结果不含本地图);
    2. 粗筛: 切片 rerank 分数低于 image_min_chunk_score 的不出图;
    3. 精排: 将图片描述 (markdown 方括号中的 alt 文本或 <img> 标签的 alt
       属性, 导入时为 VLM 生成的图片摘要) 与 rewritten_query 做图片级 rerank,
       分数低于 image_min_rerank_score 的图片直接丢弃。这一步解决"切片文本相关但
       其中某张图无关"的问题 (如含产品名的标题页 LOGO 图);
    4. 按图片级 rerank 分数降序, 保证最相关的图优先;
    5. 去重 (重叠切片可能包含同一张图, 同 URL 保留分数更高切片中的描述);
    6. 总数不超过 image_max_count。
    """
    if not rerank_results:
        return []

    # 方括号捕获图片描述 (alt 文本), 圆括号捕获 URL
    image_re = re.compile(r"!\[(.*?)\]\((.*?)\)")
    # HTML <img> 标签语法: src 为图片 URL, alt 为图片描述
    img_tag_re = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
    # src/alt 属性值 (带双引号/单引号/不带引号三种写法)
    img_attr_re = {
        "src": re.compile(
            r"(?<=\s)src\s*=\s*(?:\"(?P<dq>[\s\S]*?)\"|'(?P<sq>[\s\S]*?)'|(?P<uq>[^\s>]*))",
            re.IGNORECASE,
        ),
        "alt": re.compile(
            r"(?<=\s)alt\s*=\s*(?:\"(?P<dq>[\s\S]*?)\"|'(?P<sq>[\s\S]*?)'|(?P<uq>[^\s>]*))",
            re.IGNORECASE,
        ),
    }

    def _attr_value(match: re.Match) -> str:
        """从 src/alt 属性匹配结果中取出属性值。"""
        return match.group("dq") or match.group("sq") or match.group("uq") or ""

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

    # ---- 2. 提取 (描述, URL, 切片分数), 按 URL 去重 ----
    images: list[tuple[str, str, float]] = []
    seen_urls: set[str] = set()
    for doc in pre_filtered:
        chunk_score = doc.get("score", 0.0)
        document = doc["document"]
        # 2.1 Markdown 语法 ![](url)
        for desc, url in image_re.findall(document):
            if url in seen_urls:
                continue
            seen_urls.add(url)
            images.append((desc.strip(), url, chunk_score))
        # 2.2 HTML 语法 <img src="url" alt="描述">
        for tag_match in img_tag_re.finditer(document):
            src_match = img_attr_re["src"].search(tag_match.group(0))
            if not src_match:
                continue
            url = _attr_value(src_match)
            if not url or url in seen_urls:
                continue
            alt_match = img_attr_re["alt"].search(tag_match.group(0))
            desc = html.unescape(_attr_value(alt_match)) if alt_match else ""
            seen_urls.add(url)
            images.append((desc.strip(), url, chunk_score))
    if not images:
        return []

    # ---- 3. 图片级 rerank: 图片描述 vs 重写后的问题 ----
    # 空描述无法参与 rerank, 用切片分数兜底
    valid_pairs = [(i, desc) for i, (desc, _, _) in enumerate(images) if desc]
    score_by_image: dict[int, float] = {}
    if valid_pairs:
        try:
            hits = RERANKER.rerank(
                query=rewritten_query,
                documents=[desc for _, desc in valid_pairs],
            )
            # rerank 返回的 index 是传入 documents 列表中的下标
            score_by_image = {
                valid_pairs[h["index"]][0]: h["relevance_score"] for h in hits
            }
        except Exception as e:
            logger.warning(f"图片描述 rerank 失败, 退化为切片分数过滤: {e}")

    # ---- 4. 阈值过滤 + 按图片级分数降序 ----
    threshold = APP_CONFIG.image_min_rerank_score
    scored: list[tuple[str, float]] = []
    for idx, (desc, url, chunk_score) in enumerate(images):
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

        image_urls = step_4_collect_images(rerank_results, rewritten_query)
        logger.info(f"提取的图片 URL: {image_urls}")
        logger.info(f"共: {len(image_urls)} 张图片")

        step_5_save_message_and_push_final(session_id, answer, image_urls)

    return state

    # # FAKE:
    # base_answer = (
    #     answer
    #     or f"这是关于 \"{state.get('original_query')}\" 的测试回答，正在演示打字机流式输出效果"
    # )

    # final_text = ""
    # for ch in base_answer:
    #     final_text += ch
    #     sse_push(
    #         sse_id=state.get("session_id"),
    #         event=SSEEvent.DELTA,
    #         data={
    #             "delta": ch,
    #         },
    #     )
    #     time.sleep(0.05)

    # image_urls = [
    #     "https://www.baidu.com/img/PCtm_d9c8750bed0b3c7d089fa7d55720d6cf.png",
    #     "https://atguigu.com/images/index_new/logo.png",
    # ]

    # logger.info(f"流式输出完成, 总长度: {len(final_text)}")

    # chat_history_manager.save_message(
    #     session_id=state.get("session_id"),
    #     role=MessageRole.ASSISTANT,
    #     text=final_text,
    #     image_urls=image_urls,
    # )

    # sse_push(
    #     sse_id=state.get("session_id"),
    #     event=SSEEvent.FINAL,
    #     data={
    #         "answer": final_text,
    #         "image_urls": image_urls,
    #     },
    # )

    # return state


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
