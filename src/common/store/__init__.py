"""持久化聚合层（tier 4）。

- `get_chat_history_manager`：会话历史（MongoDB）
- `get_document_repo`：文档制品与元数据（MinIO + Milvus docs/chunks）
- `get_token_usage_manager`：浏览器会话 Token 用量（MongoDB）

只在这里暴露访问器，业务侧一律 `from common import store` 后调用 `store.get_xxx()`。
"""

from .chat_history import get_chat_history_manager
from .document_repo import get_document_repo
from .token_usage import get_token_usage_manager

__all__ = [
    "get_chat_history_manager",
    "get_document_repo",
    "get_token_usage_manager",
]
