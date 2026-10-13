from utils.node_utils import trace_node
from utils.logging_utils import logger
import time
from processor.query_processor.state import QueryGraphState
from utils.sse_utils import SSEEvent, sse_push


@trace_node(desc="答案输出")
def node_answer_output(state: QueryGraphState) -> QueryGraphState:

    # FAKE:
    base_answer = f"这是关于 \"{state.get('original_query')}\" 的测试回答，正在演示打字机流式输出效果"

    final_text = ""
    for ch in base_answer:
        final_text += ch
        sse_push(
            sse_id=state.get("session_id"),
            event=SSEEvent.DELTA,
            data={
                "delta": ch,
            },
        )
        time.sleep(0.05)

    image_urls = [
        "https://www.baidu.com/img/PCtm_d9c8750bed0b3c7d089fa7d55720d6cf.png",
        "https://atguigu.com/images/index_new/logo.png",
    ]

    logger.info(f"流式输出完成, 总长度: {len(final_text)}")

    sse_push(
        sse_id=state.get("session_id"),
        event=SSEEvent.FINAL,
        data={
            "answer": final_text,
            "image_urls": image_urls,
        },
    )

    return {}
