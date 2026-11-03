import pytest

from common.client import get_minio_client
from tests.support.fakes import FakeMinio

pytestmark = pytest.mark.contract


def test_files__prefix_guard__only_four_prefixes(client, app):
    """Given 四个业务前缀 When GET /api/files Then 放行/404 与缓存头正确。"""
    fake = FakeMinio()
    fake.objects["markdown-images/a.png"] = b"xx"
    app.dependency_overrides[get_minio_client] = lambda: fake

    ok = client.get("/api/files/markdown-images/a.png")
    assert ok.status_code == 200, ok.text
    assert ok.content == b"xx"
    assert ok.headers["cache-control"] == "public, max-age=86400, immutable"

    outside = client.get("/api/files/secret/a.png")
    assert outside.status_code == 404, outside.text

    missing = client.get("/api/files/chunks-json/none.json")
    assert missing.status_code == 404, missing.text
