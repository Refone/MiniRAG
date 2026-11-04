"""真栈启动冒烟：需要本机 Mongo / MinIO / Milvus，默认不跑。"""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.startup_checks import startup_checks

pytestmark = pytest.mark.integration


def test_startup__real_infra__idempotent_and_health_ok():
    """Given 本机真实 Mongo/MinIO/Milvus 已启动
    When 连续执行两次启动自检并进入应用 lifespan
    Then 自检幂等、/api/health 返回 ok

    这是访问器/启动改造的手动回归入口：默认套件用 fake，不覆盖真实连接。
    """
    startup_checks()
    startup_checks()

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200, (
        f"期望 /api/health 返回 200，实际 {response.status_code}: {response.text}"
    )
    payload = response.json()
    assert payload["status"] == "ok", f"期望 status=ok，实际 {payload!r}"
    assert payload.get("version"), f"期望返回 version，实际 {payload!r}"
