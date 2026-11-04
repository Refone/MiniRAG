from common import model, store
from common.events import EVENT_BUS, SSEEvent
from common.events.metering import push_usage_delta
from common.events.tracing import trace_node
from common.logging import logger
from common.model.metering import message_usage_tokens
from common.prompt.prompt_final_answer import PromptFinalAnswer
from common.schema.token_usage import TokenUsage
from common.store.chat_history import MessageRole
from graphs.query_graph.query_graph_state import DataFrom, QueryGraphState, RerankResult


def step_1_validate_and_get_data(state: QueryGraphState):
    session_id = state.get("session_id")
    rewritten_query = state.get("rewritten_query")
    rerank_results = state.get("rerank_results") or []
    suspect_titles = state.get("suspect_titles") or []

    return session_id, rewritten_query, rerank_results, suspect_titles


def step_2_format_prompt(
    rewritten_query: str,
    session_id: str,
    rerank_results: list[RerankResult],
    suspect_titles: list[str],
) -> tuple[str, bool]:
    history_summary = store.get_chat_history_manager().summary_history(
        session_id=session_id
    )

    reference = ""
    for docs in rerank_results:
        reference += (
            f"---\n"
            f"数据来源: {docs['data_from']}, 置信度: {docs['score']:0.8f},\n"
            f"内容: {docs['document']}\n\n"
            f"---\n"
        )

    # 以精排结果的实际来源判定: 文库切片为空即兜底, 不依赖 confirm_list
    no_doc_match = not any(
        item.get("data_from") == DataFrom.MILVUS for item in rerank_results
    )
    prompt = PromptFinalAnswer(
        reference=reference,
        history=history_summary,
        question=rewritten_query,
        no_doc_match=no_doc_match,
        suspect_titles=suspect_titles,
    ).prompt

    return prompt, no_doc_match


def step_3_call_llm_generate_answer(
    session_id: str, answer_prompt: str
) -> tuple[str, int]:
    answer = ""
    usage_chunk = None

    for chunk in model.get_llm().stream(answer_prompt):
        # stream_usage=True 时 usage 出现在末段带 usage_metadata 的 chunk 上,
        # 其后可能还有不带 usage 的空尾帧, 故记录"最后一个携带 usage 的 chunk"
        if message_usage_tokens(chunk):
            usage_chunk = chunk
        chunk_str = chunk.content
        EVENT_BUS.push(
            session_id,
            SSEEvent.DELTA,
            {
                "delta": chunk_str,
            },
        )
        answer += chunk_str

    tokens = message_usage_tokens(usage_chunk) if usage_chunk is not None else 0
    if not tokens:
        logger.warning("答案生成 LLM 流式调用未返回 usage, 本次调用不计入统计")

    return answer, tokens


def step_4_save_message_and_push_final(session_id: str, answer: str) -> None:
    # 图片完全由 LLM 在回答正文中以 Markdown 语法内嵌, 不再走独立的 image_urls 通道
    store.get_chat_history_manager().save_message(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        text=answer,
    )

    EVENT_BUS.push(
        session_id,
        SSEEvent.FINAL,
        {
            "answer": answer,
        },
    )


@trace_node(desc="答案输出", need_push=True)
def node_answer_output(state: QueryGraphState) -> QueryGraphState:
    (
        session_id,
        rewritten_query,
        rerank_results,
        suspect_titles,
    ) = step_1_validate_and_get_data(state)

    answer_prompt, no_doc_match = step_2_format_prompt(
        rewritten_query, session_id, rerank_results, suspect_titles
    )
    logger.info(
        f"回答模式: {'fallback（未命中文库）' if no_doc_match else 'library（命中文库）'}, "
        f"参考资料条数: {len(rerank_results)}"
    )
    logger.info(f"生成的答案提示: {answer_prompt}")

    answer, answer_tokens = step_3_call_llm_generate_answer(session_id, answer_prompt)
    push_usage_delta(session_id, "llm", answer_tokens)
    logger.info(f"最终答案: {answer}")

    step_4_save_message_and_push_final(session_id, answer)

    # 答案不写回 state, 仅返回本节点的计量增量
    return {"token_meter": TokenUsage(llm_tokens=answer_tokens)}


if __name__ == "__main__":
    from rich import print as rprint

    from common.config.path_config import snapshot_path
    from graphs.query_graph.query_graph_state import load_state, save_state

    prev_state1 = load_state(snapshot_path("query_01_intent_recognize.json"))
    prev_state2 = load_state(snapshot_path("query_05_rrf_and_rerank.json"))
    prev_state = {**prev_state1, **prev_state2}
    next_state = node_answer_output(prev_state)
    rprint(next_state)

    new_state_json = snapshot_path("query_06_answer_output.json")

    save_state(next_state, new_state_json)
    logger.info("向量化查询处理完成")
    logger.info(f"状态保存路径: {new_state_json}")
