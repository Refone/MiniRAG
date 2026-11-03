import pytest

from common.store import get_chat_history_manager, get_token_usage_manager
from common.store.token_usage import TokenUsageStoreError
from tests.support.fakes import FakeChatHistory, FakeTokenUsage

pytestmark = pytest.mark.contract


def test_history__empty_and_delete__contract(client, app):
    """Given 空历史 When GET/DELETE Then 200 + 空列表 + 删除调用。"""
    chats = FakeChatHistory()
    app.dependency_overrides[get_chat_history_manager] = lambda: chats

    got = client.get("/api/history/s1")
    assert got.status_code == 200, got.text
    assert got.json() == {"status": "ok", "history": []}

    deleted = client.delete("/api/history/s1")
    assert deleted.status_code == 200, deleted.text
    assert "删除条数" in deleted.json()["msg"]
    assert chats.cleared == ["s1"]


def test_token_usage__empty_reset_and_store_error(client, app):
    """Given Token 存储 When GET/DELETE Then 空态全 0、重置幂等、异常译 500。"""
    tokens = FakeTokenUsage()
    app.dependency_overrides[get_token_usage_manager] = lambda: tokens

    got = client.get("/api/token-usage/s1")
    assert got.status_code == 200, got.text
    assert got.json()["session_id"] == "s1"
    assert got.json()["total_tokens"] == 0

    reset = client.delete("/api/token-usage/s1")
    assert reset.status_code == 200, reset.text
    assert reset.json()["session_id"] == "s1"

    broken = FakeTokenUsage(error=TokenUsageStoreError("boom"))
    app.dependency_overrides[get_token_usage_manager] = lambda: broken
    assert client.get("/api/token-usage/s1").status_code == 500
    assert client.delete("/api/token-usage/s1").status_code == 500
