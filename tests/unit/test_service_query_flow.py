import asyncio
from uuid import uuid4

import pytest

from common.events import EVENT_BUS, TASK_MANAGER, SSEEvent, TaskStatus
from common.schema.token_usage import TokenScope
from common.store.chat_history import MessageRole
from service import query_service
from tests.support.fakes import (
    FakeChatHistory,
    FakeEmbedding,
    FakeLLM,
    FakeMilvus,
    FakeReranker,
    FakeTokenUsage,
)
from tests.support.seams import patch_accessors

pytestmark = pytest.mark.unit


def _run_query(monkeypatch, *, llm, chat, tokens):
    session_id = f"test-{uuid4().hex}"
    EVENT_BUS.create(session_id)
    patch_accessors(
        monkeypatch,
        llm=llm,
        embedding=FakeEmbedding(),
        reranker=FakeReranker(),
        milvus=FakeMilvus(),
        chat_history=chat,
        token_usage=tokens,
    )
    result = asyncio.run(
        query_service.arun_query(
            session_id=session_id,
            query="RS-12 怎么测电阻",
            enable_web_search=False,
            enable_hyde=False,
        )
    )
    return session_id, result, EVENT_BUS.take(session_id)


def test_arun_query__graph_ok__close_complete_usage_once(monkeypatch):
    """Given 真图 + 假访问器 When 查询成功 Then close/complete/usage 恰好一次。"""
    llm = FakeLLM(stream_parts=("答", "案"))
    chat = FakeChatHistory()
    tokens = FakeTokenUsage()

    session_id, _, frames = _run_query(monkeypatch, llm=llm, chat=chat, tokens=tokens)

    events = [event for event, _ in frames]
    assert events[-2:] == [SSEEvent.USAGE, SSEEvent.CLOSE], (
        f"期望末尾 usage→close，实际 {events!r}"
    )
    assert SSEEvent.ERROR not in events, f"成功路径不应出现 error: {events!r}"
    assert SSEEvent.FINAL in events, f"缺少 final 帧: {events!r}"

    snapshot = TASK_MANAGER.snapshot(session_id)
    assert snapshot is not None
    assert snapshot["status"] == TaskStatus.COMPLETE.value, snapshot

    assert len(tokens.calls) == 1, f"usage 应恰好落库一次，实际 {tokens.calls!r}"
    assert tokens.calls[0]["scope"] is TokenScope.QUERY
    assert tokens.calls[0]["usage"]["llm_tokens"] == 22, tokens.calls[0]

    assistant_messages = [
        message for message in chat.saved if message["role"] is MessageRole.ASSISTANT
    ]
    assert [message["text"] for message in assistant_messages] == ["答案"]


def test_arun_query__graph_raises__error_close_failed_no_usage(monkeypatch):
    """Given LLM 抛异常 When 查询失败 Then error→close、failed、不落 usage。"""
    llm = FakeLLM(error=RuntimeError("boom"))
    chat = FakeChatHistory()
    tokens = FakeTokenUsage()

    session_id, result, frames = _run_query(
        monkeypatch, llm=llm, chat=chat, tokens=tokens
    )

    events = [event for event, _ in frames]
    assert events[-2:] == [SSEEvent.ERROR, SSEEvent.CLOSE], (
        f"期望末尾 error→close，实际 {events!r}"
    )
    assert SSEEvent.USAGE not in events, f"失败路径不应落 usage: {events!r}"

    snapshot = TASK_MANAGER.snapshot(session_id)
    assert snapshot is not None
    assert snapshot["status"] == TaskStatus.FAILED.value, snapshot
    assert "boom" in snapshot["error"], snapshot
    assert tokens.calls == [], f"失败路径不应调用 usage 落库: {tokens.calls!r}"
    assert "查询处理失败" in result["reply"], result
