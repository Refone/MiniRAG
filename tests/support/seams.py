"""访问器接缝：一次替换，全库生效（依赖模块命名空间调用约定）。"""

from typing import Any

_TARGETS = {
    "llm": "common.model.get_llm",
    "vlm": "common.model.get_vlm",
    "embedding": "common.model.get_embedding",
    "reranker": "common.model.get_reranker",
    "milvus": "common.client.get_milvus_client",
    "minio": "common.client.get_minio_client",
    "mongo": "common.client.get_mongo_client",
    "web_search": "common.client.search_web",
    "mineru": "common.client.mineru_pdf_to_md",
    "chat_history": "common.store.get_chat_history_manager",
    "token_usage": "common.store.get_token_usage_manager",
    "document_repo": "common.store.get_document_repo",
}


def patch_accessors(monkeypatch, **fakes: Any) -> None:
    """把指定访问器替换为 fake；未传的访问器保持原状（通常是模型守卫）。"""
    unknown = set(fakes) - set(_TARGETS)
    if unknown:
        raise AssertionError(f"未知访问器: {sorted(unknown)}")

    for key, fake in fakes.items():
        if fake is None:
            continue
        monkeypatch.setattr(_TARGETS[key], lambda fake=fake: fake)
