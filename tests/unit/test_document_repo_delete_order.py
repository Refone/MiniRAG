import pytest

from common import store
from tests.support.fakes import FakeMilvus, FakeMinio
from tests.support.seams import patch_accessors

pytestmark = pytest.mark.unit


def test_delete_by_id__order__artifacts_images_chunks_docs(monkeypatch):
    """Given 文档存在 When delete_by_id Then 三制品→图片→chunks→docs。"""
    recorder: list[tuple] = []
    milvus = FakeMilvus(recorder=recorder, doc_row={"file_title": "doc"})
    minio = FakeMinio(recorder=recorder)
    patch_accessors(monkeypatch, milvus=milvus, minio=minio)

    store.get_document_repo().delete_by_id(7)

    assert recorder == [
        ("milvus", "query_doc_by_id", 7),
        ("minio", "clear_doc_artifacts", "doc"),
        ("minio", "clear_doc_images", "doc"),
        ("milvus", "delete_chunks_by_doc_ids", [7]),
        ("milvus", "delete_doc_by_id", 7),
    ], recorder


def test_delete_by_id__minio_failure__raises_before_milvus(monkeypatch):
    """Given MinIO 清理失败 When delete_by_id Then 立即抛错且不删 Milvus 行。"""
    recorder: list[tuple] = []
    milvus = FakeMilvus(recorder=recorder, doc_row={"file_title": "doc"})
    minio = FakeMinio(recorder=recorder, fail_on="clear_doc_artifacts")
    patch_accessors(monkeypatch, milvus=milvus, minio=minio)

    with pytest.raises(RuntimeError, match="清理 MinIO 制品失败"):
        store.get_document_repo().delete_by_id(7)

    assert not any(call[1].startswith("delete_") for call in recorder), recorder
