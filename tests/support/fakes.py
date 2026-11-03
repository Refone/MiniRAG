"""形状回放器：只回放真实响应形状，不复刻业务逻辑。"""

from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk

from common.schema.token_usage import (
    ModelTokenUsage,
    build_snapshot,
    empty_token_usage,
    sum_token_usage,
)


class FakeLLM:
    def __init__(
        self,
        invoke_content: str = "改写后的问题",
        stream_parts: tuple[str, ...] = ("答", "案"),
        *,
        error: Exception | None = None,
        structured_result: Any = None,
    ) -> None:
        self.invoke_content = invoke_content
        self.stream_parts = stream_parts
        self.error = error
        self.structured_result = structured_result
        self.invoke_calls: list[str] = []
        self.stream_calls: list[str] = []

    def _raise_if_error(self) -> None:
        if self.error is not None:
            raise self.error

    def invoke(self, prompt, **kwargs) -> AIMessage:
        self._raise_if_error()
        self.invoke_calls.append(str(prompt))
        return AIMessage(
            content=self.invoke_content,
            usage_metadata={
                "input_tokens": 7,
                "output_tokens": 4,
                "total_tokens": 11,
            },
        )

    def stream(self, prompt, **kwargs):
        self._raise_if_error()
        self.stream_calls.append(str(prompt))
        for part in self.stream_parts:
            yield AIMessageChunk(content=part)
        yield AIMessageChunk(
            content="",
            usage_metadata={
                "input_tokens": 7,
                "output_tokens": 4,
                "total_tokens": 11,
            },
        )

    def with_structured_output(self, schema, **kwargs):
        return _FakeStructured(
            result=self.structured_result,
            include_raw=bool(kwargs.get("include_raw")),
        )


class _FakeStructured:
    def __init__(self, *, result: Any, include_raw: bool) -> None:
        self.result = result
        self.include_raw = include_raw

    def invoke(self, prompt, **kwargs):
        if self.include_raw:
            return {
                "parsed": self.result,
                "raw": AIMessage(
                    content="",
                    usage_metadata={
                        "input_tokens": 7,
                        "output_tokens": 4,
                        "total_tokens": 11,
                    },
                ),
            }
        return self.result


class FakeVLM:
    def __init__(self, description: str = "图片摘要") -> None:
        self.description = description
        self.calls: list[Any] = []

    def invoke(self, messages, **kwargs) -> AIMessage:
        self.calls.append(messages)
        return AIMessage(
            content=self.description,
            usage_metadata={"input_tokens": 7, "output_tokens": 4, "total_tokens": 11},
        )


class FakeEmbedding:
    def __init__(self, tokens: int = 3) -> None:
        self.tokens = tokens
        self.calls: list[list[str]] = []

    @staticmethod
    def _vector() -> dict:
        return {"dense": [0.1, 0.2, 0.3], "sparse": {1: 0.5}}

    def embed_document_hybrid(self, texts: list[str]):
        self.calls.append(list(texts))
        return [self._vector() for _ in texts], self.tokens

    def embed_query_hybrid(self, texts: list[str]):
        return self.embed_document_hybrid(texts)


class FakeReranker:
    def __init__(self, results: list[dict] | None = None, tokens: int = 4) -> None:
        self.results = results or []
        self.tokens = tokens
        self.calls: list[tuple[str, list[str]]] = []

    def rerank(self, query: str, documents: list[str], **kwargs):
        self.calls.append((query, list(documents)))
        return list(self.results), self.tokens


class FakeChatHistory:
    def __init__(self, history_text: str = "---\n\n") -> None:
        self.history_text = history_text
        self.saved: list[dict] = []
        self.cleared: list[str] = []

    def summary_history(self, session_id: str, **kwargs) -> str:
        return self.history_text

    def save_message(self, session_id: str, role, text: str) -> str:
        self.saved.append({"session_id": session_id, "role": role, "text": text})
        return "fake-id"

    def get_latest_messages(self, session_id: str, limit=None) -> list[dict]:
        return list(self.saved)

    def clear_history(self, session_id: str) -> int:
        self.cleared.append(session_id)
        return 0


class FakeTokenUsage:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self.usage = empty_token_usage()
        self.error = error

    def _raise_if_error(self) -> None:
        if self.error is not None:
            raise self.error

    def add_usage(self, session_id: str, user_ip: str, scope, usage) -> None:
        self._raise_if_error()
        self.calls.append(
            {
                "session_id": session_id,
                "user_ip": user_ip,
                "scope": scope,
                "usage": dict(usage),
            }
        )
        self.usage = sum_token_usage(self.usage, usage)

    def get_usage(self, session_id: str):
        self._raise_if_error()
        return build_snapshot(session_id, query=ModelTokenUsage(**self.usage))

    def clear_usage(self, session_id: str) -> int:
        self._raise_if_error()
        return 0


class FakeMilvus:
    """查询链路只回放命中形状；写入类方法记录调用供删除顺序用例断言。"""

    def __init__(
        self,
        docs_hits: list[dict] | None = None,
        chunks_hits: list[dict] | None = None,
        recorder: list | None = None,
        doc_row: dict | None = None,
    ) -> None:
        self.docs_hits = docs_hits or []
        self.chunks_hits = chunks_hits or []
        self.calls: list[tuple] = []
        self.recorder = recorder
        self.doc_row = doc_row

    def _record(self, *call) -> None:
        self.calls.append(call)
        if self.recorder is not None:
            self.recorder.append(("milvus", *call))

    def hybrid_search_docs(self, texts: list[str], limit: int = 0):
        self.calls.append(("hybrid_search_docs", list(texts)))
        return [list(self.docs_hits)], 0

    def hybrid_search_chunks(self, query_text: list[str], doc_ids=None, limit: int = 0):
        self.calls.append(
            ("hybrid_search_chunks", list(query_text), list(doc_ids or []))
        )
        return [list(self.chunks_hits)], 0

    def count_docs(self) -> int:
        self.calls.append(("count_docs",))
        return 0

    def query_docs_page(self, offset: int, limit: int) -> list[dict]:
        self.calls.append(("query_docs_page", offset, limit))
        return []

    def query_doc_by_id(self, doc_id: int) -> dict | None:
        self._record("query_doc_by_id", doc_id)
        return self.doc_row

    def query_doc_rows_by_file_title(self, file_title: str) -> list[dict]:
        self._record("query_doc_rows_by_file_title", file_title)
        return []

    def delete_chunks_by_doc_ids(self, doc_ids: list[int]) -> None:
        self._record("delete_chunks_by_doc_ids", list(doc_ids))

    def delete_chunks_by_file_title(self, file_title: str) -> None:
        self._record("delete_chunks_by_file_title", file_title)

    def delete_docs_by_file_title(self, file_title: str) -> None:
        self._record("delete_docs_by_file_title", file_title)

    def delete_doc_by_id(self, doc_id: int) -> None:
        self._record("delete_doc_by_id", doc_id)

    def insert(self, collection_name: str, data: list[dict]) -> dict:
        self.calls.append(("insert", collection_name, len(data)))
        return {"insert_count": len(data), "ids": [1]}

    def query_doc_id(self, task_id: str, file_title: str) -> int | None:
        self.calls.append(("query_doc_id", task_id, file_title))
        return 1


class FakeMinio:
    def __init__(
        self,
        recorder: list | None = None,
        fail_on: str | None = None,
    ) -> None:
        self.objects: dict[str, bytes] = {}
        self.calls: list[tuple] = []
        self.recorder = recorder
        self.fail_on = fail_on

    def _record(self, *call) -> None:
        self.calls.append(call)
        if self.recorder is not None:
            self.recorder.append(("minio", *call))
        if self.fail_on == call[0]:
            raise RuntimeError(f"fake minio failure: {call[0]}")

    def upload_file(self, *, prefix: str, as_name: str, file_path: str) -> str:
        object_name = f"{prefix}/{as_name}"
        with open(file_path, "rb") as f:
            self.objects[object_name] = f.read()
        self._record("upload_file", object_name)
        return f"/api/files/{object_name}"

    @staticmethod
    def doc_artifact_prefix(doc_dir: str, file_title: str) -> str:
        return f"{doc_dir}/{file_title}"

    def clear_doc_artifacts(self, file_title: str) -> int:
        self._record("clear_doc_artifacts", file_title)
        return 0

    def clear_doc_images(self, file_title: str) -> int:
        self._record("clear_doc_images", file_title)
        return 0

    def clear_dir_if_exist(self, prefix: str) -> int:
        self._record("clear_dir_if_exist", prefix)
        return 0

    def get_object_stream(self, object_name: str):
        self._record("get_object_stream", object_name)
        data = self.objects.get(object_name)
        if data is None:
            raise FileNotFoundError(object_name)
        return "application/octet-stream", iter([data])


class FakeDocumentRepo:
    def __init__(
        self,
        rows: list[dict] | None = None,
        detail=None,
        error: Exception | None = None,
    ) -> None:
        self.rows = rows or []
        self.detail = detail
        self.error = error
        self.calls: list[tuple] = []

    def count(self) -> int:
        self.calls.append(("count",))
        if self.error is not None:
            raise self.error
        return len(self.rows)

    def list_page(self, offset: int, limit: int) -> list[dict]:
        self.calls.append(("list_page", offset, limit))
        if self.error is not None:
            raise self.error
        return self.rows[offset : offset + limit]

    def get_detail(self, doc_id: int):
        self.calls.append(("get_detail", doc_id))
        if self.error is not None:
            raise self.error
        return self.detail

    def delete_by_id(self, doc_id: int):
        self.calls.append(("delete_by_id", doc_id))
        if self.error is not None:
            raise self.error
        return None
