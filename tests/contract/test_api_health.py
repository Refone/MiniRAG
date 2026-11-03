import pytest

pytestmark = pytest.mark.contract


def test_health__get__ok_shape(client):
    """Given 应用已装配 When GET /api/health Then 200 + status/version。"""
    response = client.get("/api/health")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ok", payload
    assert payload["version"], "health 响应缺少 version"
