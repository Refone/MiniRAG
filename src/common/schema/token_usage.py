"""Token 计量共享契约（tier 0）。

跨层共用的计量数据形状：
- `TokenUsage`：四模型 token 用量的纯数据对象（可 JSON 序列化），既作图状态
  通道的增量单元，也作 Mongo 落库的输入；节点在结束时返回本节点的增量，
  图通道用 `sum_token_usage` 累加。
- `ModelTokenUsage` / `TokenUsageSnapshot`：单口径用量与对外快照形状。
"""

from enum import StrEnum
from typing import TypedDict

from pydantic import BaseModel, Field, computed_field


class TokenScope(StrEnum):
    """计量口径：一次浏览器会话内的消耗来源维度。"""

    QUERY = "query"
    UPLOAD = "upload"


class TokenUsage(TypedDict):
    """四模型 token 用量的纯数据对象（单节点增量 / 累计值通用）。

    示例实例：
        TokenUsage(
            llm_tokens=620, vlm_tokens=0, embedding_tokens=905, reranker_tokens=350
        )
    """

    llm_tokens: int
    vlm_tokens: int
    embedding_tokens: int
    reranker_tokens: int


def empty_token_usage() -> TokenUsage:
    """全 0 用量（图状态初始值 / 无模型调用节点的占位增量）。"""
    return TokenUsage(llm_tokens=0, vlm_tokens=0, embedding_tokens=0, reranker_tokens=0)


def sum_token_usage(left: TokenUsage | None, right: TokenUsage | None) -> TokenUsage:
    """按模型累加两份用量（LangGraph token_meter 通道的 reducer）。

    只接受增量语义：左值是通道累计值、右值是本次写入的增量，逐字段相加；
    容忍 None / 缺字段（部分写入）。
    """
    left = left or {}
    right = right or {}
    return TokenUsage(
        llm_tokens=left.get("llm_tokens", 0) + right.get("llm_tokens", 0),
        vlm_tokens=left.get("vlm_tokens", 0) + right.get("vlm_tokens", 0),
        embedding_tokens=left.get("embedding_tokens", 0)
        + right.get("embedding_tokens", 0),
        reranker_tokens=left.get("reranker_tokens", 0)
        + right.get("reranker_tokens", 0),
    )


class ModelTokenUsage(BaseModel):
    """单一口径（查询 / 上传）的四模型 token 用量，total_tokens 派生。

    示例实例：
        ModelTokenUsage(
            llm_tokens=620, vlm_tokens=0, embedding_tokens=905, reranker_tokens=350
        )
        # total_tokens == 1875
    """

    llm_tokens: int = 0
    vlm_tokens: int = 0
    embedding_tokens: int = 0
    reranker_tokens: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_tokens(self) -> int:
        return (
            self.llm_tokens
            + self.vlm_tokens
            + self.embedding_tokens
            + self.reranker_tokens
        )


class TokenUsageSnapshot(BaseModel):
    """GET /api/token-usage/{session_id} 响应快照（会话总计 + 查询 + 上传）。

    四模型字段与 total_tokens 由 query / upload 两口径派生（PRD 字段契约）；
    updated_at 为 None 表示该会话尚无任何记录（空统计态）。

    示例实例：
        build_snapshot(
            session_id="sess-ab12cd34",
            user_ip="127.0.0.1",
            query=ModelTokenUsage(
                llm_tokens=620, embedding_tokens=905, reranker_tokens=350
            ),
            upload=ModelTokenUsage(llm_tokens=486, vlm_tokens=1264, embedding_tokens=890),
            updated_at=1751600000.0,
        )
        # total_tokens == 4515
    """

    session_id: str
    user_ip: str = ""
    updated_at: float | None = None
    query: ModelTokenUsage = Field(default_factory=ModelTokenUsage)
    upload: ModelTokenUsage = Field(default_factory=ModelTokenUsage)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def llm_tokens(self) -> int:
        return self.query.llm_tokens + self.upload.llm_tokens

    @computed_field  # type: ignore[prop-decorator]
    @property
    def vlm_tokens(self) -> int:
        return self.query.vlm_tokens + self.upload.vlm_tokens

    @computed_field  # type: ignore[prop-decorator]
    @property
    def embedding_tokens(self) -> int:
        return self.query.embedding_tokens + self.upload.embedding_tokens

    @computed_field  # type: ignore[prop-decorator]
    @property
    def reranker_tokens(self) -> int:
        return self.query.reranker_tokens + self.upload.reranker_tokens

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_tokens(self) -> int:
        return self.query.total_tokens + self.upload.total_tokens


def build_snapshot(
    session_id: str,
    *,
    user_ip: str = "",
    query: ModelTokenUsage | None = None,
    upload: ModelTokenUsage | None = None,
    updated_at: float | None = None,
) -> TokenUsageSnapshot:
    """由查询 / 上传两口径组装对外快照（纯函数，供 store 与单测复用）。"""
    return TokenUsageSnapshot(
        session_id=session_id,
        user_ip=user_ip,
        query=query or ModelTokenUsage(),
        upload=upload or ModelTokenUsage(),
        updated_at=updated_at,
    )
