import re

from regex import R

from processor.query_processor.chat_history import chat_history_manager, MessageRole
from utils.node_utils import trace_node
from common.prompt.prompt_final_answer import PromptFinalAnswer
from utils.logging_utils import logger
import time
from processor.query_processor.state import DataFrom, QueryGraphState, RerankResult
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


def step_4_collecte_images(rerank_results: list[RerankResult]) -> list[str]:
    image_urls: list[str] = []

    image_re = re.compile(r"\!\[.*?\]\((.*?)\)")

    for doc in rerank_results:
        if doc["data_from"] == DataFrom.MILVUS:
            image_urls.extend(image_re.findall(doc["document"]))

    return image_urls


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

    if not answer:
        answer_prompt = step_2_format_prompt(
            rewritten_query, session_id, rerank_results
        )
        logger.info(f"生成的答案提示: {answer_prompt}")

        answer = step_3_call_llm_generate_answer(session_id, answer_prompt)
        logger.info(f"最终答案: {answer}")

        image_urls = step_4_collecte_images(rerank_results)
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
