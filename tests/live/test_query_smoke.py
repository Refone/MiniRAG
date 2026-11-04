"""真模型查询冒烟：手动运行，不进 CI。"""

import asyncio
import os
from uuid import uuid4

import pytest

from common import store
from common.config.env_config import ENV_CONFIG
from common.events import EVENT_BUS, TASK_MANAGER, SSEEvent
from service import query_service

pytestmark = pytest.mark.live

if os.getenv("RUN_LIVE_TESTS") != "1":
    pytest.skip("live 层需显式 RUN_LIVE_TESTS=1", allow_module_level=True)

if not ENV_CONFIG.dashscope.api_key:
    pytest.skip("live 层需要真实的 DASHSCOPE_API_KEY", allow_module_level=True)


def test_query__real_models__final_usage_close():
    """Given 真实模型、真实 key 与本机 Mongo/MinIO/Milvus
    When 执行一次不联网、不启用 HyDE 的查询
    Then 图正常结束，推 final/usage/close，且 usage 落库为正数

    只校验链路与形状，不断言模型回答内容；内容质量归人工评估。
    """
    from api.startup_checks import startup_checks

    startup_checks()

    session_id = f"test-live-{uuid4().hex}"
    EVENT_BUS.create(session_id)
    try:
        asyncio.run(
            query_service.arun_query(
                session_id=session_id,
                query="用一句话解释什么是电阻",
                enable_web_search=False,
                enable_hyde=False,
            )
        )
        frames = EVENT_BUS.take(session_id)
        events = [event for event, _ in frames]

        assert SSEEvent.ERROR not in events, f"真实查询不应失败: {events!r}"
        assert events[-1] == SSEEvent.CLOSE, (
            f"期望最后一帧是 close，实际 {events[-1] if events else None!r}"
        )
        assert SSEEvent.FINAL in events, f"缺少 final 帧: {events!r}"
        assert SSEEvent.USAGE in events, f"缺少 usage 帧: {events!r}"

        snapshot = TASK_MANAGER.snapshot(session_id)
        assert snapshot is not None, "任务快照不应为空"
        assert snapshot["status"] == "complete", (
            f"期望任务 complete，实际 {snapshot['status']!r}"
        )

        usage = store.get_token_usage_manager().get_usage(session_id)
        assert usage.query.total_tokens > 0, (
            f"期望查询 usage 为正数，实际 {usage.query.model_dump()!r}"
        )
    finally:
        store.get_chat_history_manager().clear_history(session_id)
        store.get_token_usage_manager().clear_usage(session_id)
        EVENT_BUS.remove(session_id)
        TASK_MANAGER.clear(session_id)
