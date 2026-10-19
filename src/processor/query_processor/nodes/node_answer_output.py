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


# 剔除主体名后、与诉求无关的口语填充词
_FILLER_RE = re.compile(
    r"给我|说说|介绍|一下|请问|什么是|是什么|怎么样|如何|麻烦|的|吗|呢|么"
    r"|[，。？！?,\s]"
)


def _aspect_core(aspect_query: str) -> str:
    """剔除口语填充词后的诉求核心, 用于判断诉求点是否足够具体。

    例如 "给我说说 的四指操作" -> "四指操作"; "介绍一下" -> ""。
    """
    return _FILLER_RE.sub("", aspect_query).strip()


def _remove_item_names(text: str, item_names: list[str]) -> tuple[str, bool]:
    """从文本中剔除已确认的主体名, 只保留问题的"诉求点"。

    例如: "给我说说华为擎云 S520 Gen2 的四指操作" 剔除主体名后变为
    "给我说说 的四指操作", 剩余的 "四指操作" 才是图片需要满足的真正诉求。

    返回: (剔除后的文本, 是否真的删除了至少一个主体名)
    """
    cleaned = text
    removed = False
    # 长主体名优先剔除, 避免短主体名是长主体名子串时误伤
    for name in sorted(item_names, key=len, reverse=True):
        if name and name in cleaned:
            cleaned = cleaned.replace(name, " ")
            removed = True
    return re.sub(r"\s+", " ", cleaned).strip(), removed


def step_4_collect_images(
    rerank_results: list[RerankResult],
    rewritten_query: str,
    item_names: list[str] | None = None,
) -> list[str]:
    """从重排序结果中收集要展示给用户的图片。

    过滤策略 (解决"召回的无关图片太多"问题):
    1. 只从 Milvus 切片中取图 (Web 结果不含本地图);
    2. 粗筛: 切片 rerank 分数低于 image_min_chunk_score 的不出图;
    3. 精排: 将图片描述 (markdown 方括号中的 alt 文本或 <img> 标签的 alt
       属性, 导入时为 VLM 生成的图片摘要) 与 rewritten_query 做图片级 rerank,
       分数低于 image_min_rerank_score 的图片直接丢弃。这一步解决"切片文本相关但
       其中某张图无关"的问题 (如含产品名的标题页 LOGO 图);
    4. 诉求点复核 (解决"描述只因包含主体名而得分虚高"的问题): 问题与描述
       共现主体名 (如"华为擎云 S520 Gen2") 时, 全题 rerank 分会被主体名拉高。
       因此将问题与描述中已确认的主体名 (item_names, 即 confirm_list) 剔除,
       用剩余诉求点 (如"四指操作") 再做一次 rerank, 分数低于
       image_min_aspect_score 的图片直接丢弃。例如问题问"四指操作", 描述为
       "展示双指点击功能"时, 全题 rerank 分因共现主体名虚高, 但诉求点
       rerank 分很低, 会被此步拦截;
    5. 按图片级 rerank 分数降序, 保证最相关的图优先;
    6. 去重 (重叠切片可能包含同一张图, 同 URL 保留分数更高切片中的描述);
    7. 总数不超过 image_max_count。
    """
    if not rerank_results:
        return []

    item_names = [name for name in (item_names or []) if name]

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

    # ---- 3.5 诉求点 rerank: 剔除主体名后二次打分, 拦截"只命中主体名"的虚高分 ----
    # 有确认主体名 (item_names) 时, 问题与描述共现主体名会让全题 rerank 分虚高,
    # 导致"问四指、图是双指"的无关图片混进来。把问题与描述里的主体名都剔除,
    # 只对诉求点 (如"四指操作") 打分, 作为通过精排后的第二道硬门槛。
    aspect_query, query_stripped = _remove_item_names(rewritten_query, item_names)
    # 诉求点必须是"具体信息需求" (如"四指操作")。泛介绍类问题 ("介绍一下…")
    # 剔除主体名后只剩口语填充词, 不启用门槛, 避免误杀产品概览图
    aspect_gate_enabled = bool(
        query_stripped and len(_aspect_core(aspect_query)) >= 2
    )
    aspect_scores: dict[int, float] = {}
    if aspect_gate_enabled:
        # 剔除主体名后仍有内容的描述才参与诉求点打分
        aspect_pairs = [
            (i, _remove_item_names(desc, item_names)[0]) for i, desc in valid_pairs
        ]
        aspect_pairs = [(i, desc) for i, desc in aspect_pairs if desc]
        if aspect_pairs:
            try:
                hits = RERANKER.rerank(
                    query=aspect_query,
                    documents=[desc for _, desc in aspect_pairs],
                )
                # rerank 返回的 index 是传入 documents 列表中的下标
                aspect_scores = {
                    aspect_pairs[h["index"]][0]: h["relevance_score"] for h in hits
                }
            except Exception as e:
                logger.warning(f"诉求点 rerank 失败, 关闭诉求点门槛: {e}")
                aspect_gate_enabled = False

    # ---- 4. 阈值过滤 + 按图片级分数降序 ----
    threshold = APP_CONFIG.image_min_rerank_score
    scored_idx = {i for i, _ in valid_pairs}  # 有原始描述、参与过全题 rerank 的图片
    scored: list[tuple[str, float]] = []
    for idx, (desc, url, chunk_score) in enumerate(images):
        image_score = score_by_image.get(idx, chunk_score)
        if image_score < threshold:
            logger.debug(
                f"图片描述 rerank {image_score:.4f} 低于阈值 {threshold}, 丢弃: {desc[:40]}({url})"
            )
            continue
        # 诉求点硬门槛: 有描述但诉求点分不足 (含剔除主体名后描述为空的) 的丢弃;
        # 无描述 (无 alt) 的图片无法验证诉求点, 沿用切片分数兜底的旧行为
        if aspect_gate_enabled and idx in scored_idx:
            aspect_score = aspect_scores.get(idx, 0.0)
            if aspect_score < APP_CONFIG.image_min_aspect_score:
                logger.debug(
                    f"诉求点 rerank {aspect_score:.4f} 低于门槛 "
                    f"{APP_CONFIG.image_min_aspect_score}, 丢弃: {desc[:40]}({url})"
                )
                continue
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

        image_urls = step_4_collect_images(
            rerank_results, rewritten_query, state.get("confirm_list", [])
        )
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
