from common.prompt.prompt_final_answer import PromptFinalAnswer
from processor.query_processor.chat_history import chat_history_manager, MessageRole
from utils.node_utils import trace_node
from utils.logging_utils import logger
from processor.query_processor.state import QueryGraphState, RerankResult
from common.model import LLM
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


def step_4_save_message_and_push_final(session_id: str, answer: str) -> None:
    # 图片完全由 LLM 在回答正文中以 Markdown 语法内嵌, 不再走独立的 image_urls 通道
    chat_history_manager.save_message(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        text=answer,
    )

    sse_push(
        sse_id=session_id,
        event=SSEEvent.FINAL,
        data={
            "answer": answer,
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
        step_4_save_message_and_push_final(session_id, answer)
    else:
        answer_prompt = step_2_format_prompt(
            rewritten_query, session_id, rerank_results
        )
        logger.info(f"生成的答案提示: {answer_prompt}")

        answer = step_3_call_llm_generate_answer(session_id, answer_prompt)
        logger.info(f"最终答案: {answer}")

        step_4_save_message_and_push_final(session_id, answer)

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
