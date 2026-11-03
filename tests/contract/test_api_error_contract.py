import pytest

from common.store import get_token_usage_manager
from common.store.document_repo import DocumentNotFoundError
from common.store.token_usage import TokenUsageStoreError
from tests.support.fakes import FakeDocumentRepo, FakeTokenUsage
from tests.support.seams import patch_accessors

pytestmark = pytest.mark.contract


def test_api__errors__404_500_shapes(client, app, monkeypatch):
    """Given 存储异常 When 查询/删除/Token 读取 Then 返回契约化 404/500。"""
    repo = FakeDocumentRepo(error=DocumentNotFoundError("missing"))
    patch_accessors(monkeypatch, document_repo=repo)

    detail = client.get("/api/docs/7")
    assert detail.status_code == 404, detail.text
    assert "missing" in detail.json()["detail"]

    delete_404 = client.delete("/api/docs/7")
    assert delete_404.status_code == 404, delete_404.text

    repo = FakeDocumentRepo(error=RuntimeError("partial"))
    patch_accessors(monkeypatch, document_repo=repo)
    delete_500 = client.delete("/api/docs/7")
    assert delete_500.status_code == 500, delete_500.text
    assert delete_500.json() == {
        "success": False,
        "detail": "删除未完整完成: partial",
    }

    broken_tokens = FakeTokenUsage(error=TokenUsageStoreError("boom"))
    app.dependency_overrides[get_token_usage_manager] = lambda: broken_tokens

    token_read = client.get("/api/token-usage/s1")
    assert token_read.status_code == 500, token_read.text
    assert token_read.json()["detail"] == "Token 统计读取失败"

    token_reset = client.delete("/api/token-usage/s1")
    assert token_reset.status_code == 500, token_reset.text
    assert token_reset.json()["detail"] == "Token 统计重置失败"
