import pytest

from tests.support.fakes import FakeDocumentRepo
from tests.support.seams import patch_accessors

pytestmark = pytest.mark.contract


def test_docs_list__paging__clamped_and_string_doc_id(client, monkeypatch):
    """Given 文档行 When GET /api/docs Then 分页钳制、doc_id 字符串、DTO 形状正确。"""
    rows = [
        {
            "id": 470074271614893543,
            "file_title": "万用表RS-12的使用",
            "origin_file_url": "/api/files/origin-files/万用表RS-12的使用/x.pdf",
            "chunks_url": "/api/files/chunks-json/万用表RS-12的使用/chunks.json",
        }
    ]
    repo = FakeDocumentRepo(rows=rows)
    patch_accessors(monkeypatch, document_repo=repo)

    response = client.get("/api/docs", params={"offset": -5, "limit": 1000})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["list"]) == 1
    assert payload["list"][0]["doc_id"] == "470074271614893543", payload
    assert payload["list"][0]["type"] == "pdf"
    assert payload["list"][0]["pdf_link"].endswith(".pdf")
    assert repo.calls == [("count",), ("list_page", 0, 100)], repo.calls
