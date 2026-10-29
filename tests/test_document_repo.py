"""DocumentRepo：删除顺序与失败语义。

两个删除入口的顺序**不能**混：
- 同名覆盖导入：三制品 → chunks → docs（不动图片，图片刚重传）
- 删除文档接口：三制品 → 图片 → chunks → docs

这是原本散落两处、最容易"改一处忘一处"的逻辑，用假 client 把顺序钉住。
"""

import pytest

from common.store import document_repo as repo_mod
from common.store.document_repo import DocumentNotFoundError, DocumentRepo


class FakeMilvus:
    def __init__(self, rows=None, row=None, fail_on=None):
        self.calls: list[str] = []
        self._rows = rows or []
        self._row = row
        self._fail_on = fail_on or set()

    def query_doc_rows_by_file_title(self, file_title):
        self.calls.append("query_by_title")
        return self._rows

    def query_doc_by_id(self, doc_id):
        self.calls.append("query_by_id")
        return self._row

    def delete_chunks_by_doc_ids(self, ids):
        self.calls.append("delete_chunks")
        if "delete_chunks" in self._fail_on:
            raise RuntimeError("milvus down")

    def delete_chunks_by_file_title(self, file_title):
        self.calls.append("delete_chunks_by_title")

    def delete_docs_by_file_title(self, file_title):
        self.calls.append("delete_docs")

    def delete_doc_by_id(self, doc_id):
        self.calls.append("delete_doc")
        if "delete_doc" in self._fail_on:
            raise RuntimeError("milvus down")


class FakeMinio:
    def __init__(self):
        self.calls: list[str] = []

    def clear_doc_artifacts(self, file_title):
        self.calls.append("clear_artifacts")
        return 2

    def clear_doc_images(self, file_title):
        self.calls.append("clear_images")
        return 1


@pytest.fixture
def fake_clients(monkeypatch):
    milvus = FakeMilvus(rows=[{"id": 11}], row={"file_title": "t"})
    minio = FakeMinio()
    monkeypatch.setattr(repo_mod, "MILVUS_CLIENT", milvus)
    monkeypatch.setattr(repo_mod, "MINIO_CLIENT", minio)
    return milvus, minio


def test_delete_by_title_order_skips_images(fake_clients):
    milvus, minio = fake_clients

    result = DocumentRepo().delete_by_title("t")

    assert minio.calls == ["clear_artifacts"]
    assert milvus.calls == [
        "query_by_title",
        "delete_chunks",
        "delete_chunks_by_title",
        "delete_docs",
    ]
    assert result.docs_rows == 1
    assert result.minio_objects == 2


def test_delete_by_id_order_clears_images(fake_clients):
    milvus, minio = fake_clients

    result = DocumentRepo().delete_by_id(42)

    assert minio.calls == ["clear_artifacts", "clear_images"]
    assert milvus.calls == ["query_by_id", "delete_chunks", "delete_doc"]
    assert result.minio_objects == 3


def test_delete_by_id_raises_when_row_missing(monkeypatch):
    milvus = FakeMilvus(row=None)
    minio = FakeMinio()
    monkeypatch.setattr(repo_mod, "MILVUS_CLIENT", milvus)
    monkeypatch.setattr(repo_mod, "MINIO_CLIENT", minio)

    with pytest.raises(DocumentNotFoundError):
        DocumentRepo().delete_by_id(404)

    assert minio.calls == []
    assert milvus.calls == ["query_by_id"]


def test_delete_stops_at_first_failure(monkeypatch):
    milvus = FakeMilvus(row={"file_title": "t"}, fail_on={"delete_chunks"})
    minio = FakeMinio()
    monkeypatch.setattr(repo_mod, "MILVUS_CLIENT", milvus)
    monkeypatch.setattr(repo_mod, "MINIO_CLIENT", minio)

    with pytest.raises(RuntimeError, match="删除 minirag_chunks 失败"):
        DocumentRepo().delete_by_id(42)

    # chunks 失败后不再删 docs 主行
    assert "delete_doc" not in milvus.calls
