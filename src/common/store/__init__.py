"""持久化聚合层（tier 4）。

- `CHAT_HISTORY_MANAGER`：会话历史（MongoDB）
- `DOCUMENT_REPO`：文档制品与元数据（MinIO + Milvus docs/chunks）

只在这里暴露单例，业务侧一律 `from common.store import XXX`。
"""

from .chat_history import CHAT_HISTORY_MANAGER
from .document_repo import DOCUMENT_REPO

__all__ = ["CHAT_HISTORY_MANAGER", "DOCUMENT_REPO"]
