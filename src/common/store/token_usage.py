"""Token 用量持久化（tier 4）。

`token_usage` 集合：每个浏览器会话一行（session_id 唯一索引），
query_*/upload_* 拆分列经 `$inc` 原子累计；PRD 的四模型字段与
total_tokens 在读取时由两口径派生（见 `common.schema.token_usage`）。

与 `chat_history` 的差异：读取失败显式抛领域异常（由 api 译成 500），
不复刻吞异常返回 0 值的风格——前端面板需要可区分的错误态。
"""

from datetime import datetime

from common.client import MONGODB_CLIENT
from common.logging import logger
from common.schema.token_usage import (
    ModelTokenUsage,
    TokenScope,
    TokenUsage,
    TokenUsageSnapshot,
    build_snapshot,
)


class TokenUsageStoreError(RuntimeError):
    """token_usage 读写失败（api 层译成 500 + detail）。"""


def _usage_from_doc(doc: dict, scope: TokenScope) -> ModelTokenUsage:
    """从 Mongo 文档读出单口径（query / upload）的四模型用量。"""
    prefix = f"{scope.value}_"
    return ModelTokenUsage(
        llm_tokens=doc.get(f"{prefix}llm_tokens") or 0,
        vlm_tokens=doc.get(f"{prefix}vlm_tokens") or 0,
        embedding_tokens=doc.get(f"{prefix}embedding_tokens") or 0,
        reranker_tokens=doc.get(f"{prefix}reranker_tokens") or 0,
    )


class TokenUsageManager:
    """token_usage 集合的读写：get_usage 读快照、add_usage 原子累计。"""

    def __init__(self):
        self.token_usage = MONGODB_CLIENT.db["token_usage"]
        # create index 自带幂等性: 索引已存在时不会重复创建
        self.token_usage.create_index([("session_id", 1)], unique=True)

    def get_usage(self, session_id: str) -> TokenUsageSnapshot:
        """读取会话快照；无记录返回全 0（空统计态），读失败抛领域异常。"""
        try:
            doc = self.token_usage.find_one({"session_id": session_id}, {"_id": False})
        except Exception as e:
            logger.error(f"读取 {session_id} token 统计失败: {e}")
            raise TokenUsageStoreError("Token 统计读取失败") from e

        if doc is None:
            return build_snapshot(session_id)

        return build_snapshot(
            session_id,
            user_ip=doc.get("user_ip") or "",
            query=_usage_from_doc(doc, TokenScope.QUERY),
            upload=_usage_from_doc(doc, TokenScope.UPLOAD),
            updated_at=doc.get("updated_at"),
        )

    def add_usage(
        self,
        session_id: str,
        user_ip: str,
        scope: TokenScope,
        usage: TokenUsage,
    ) -> None:
        """按口径原子累计一次流（查询 / 导入）的四模型用量。"""
        if not session_id or not usage:
            return

        inc: dict[str, int] = {
            f"{scope.value}_{field}": tokens
            for field, tokens in usage.items()
            if tokens
        }
        if not inc:
            return

        try:
            self.token_usage.update_one(
                {"session_id": session_id},
                {
                    "$inc": inc,
                    "$set": {"updated_at": datetime.now().timestamp()},
                    "$setOnInsert": {"user_ip": user_ip or ""},
                },
                upsert=True,
            )
        except Exception as e:
            logger.error(f"写入 {session_id} token 统计失败: {e}")
            raise TokenUsageStoreError("Token 统计写入失败") from e


TOKEN_USAGE_MANAGER: TokenUsageManager = TokenUsageManager()

if __name__ == "__main__":
    from rich import print as rprint

    session_id = "test_token_session"
    TOKEN_USAGE_MANAGER.add_usage(
        session_id,
        user_ip="127.0.0.1",
        scope=TokenScope.QUERY,
        usage={
            "llm_tokens": 620,
            "embedding_tokens": 905,
            "reranker_tokens": 350,
        },
    )
    TOKEN_USAGE_MANAGER.add_usage(
        session_id,
        user_ip="127.0.0.1",
        scope=TokenScope.UPLOAD,
        usage={
            "llm_tokens": 486,
            "vlm_tokens": 1264,
            "embedding_tokens": 890,
        },
    )
    rprint(TOKEN_USAGE_MANAGER.get_usage(session_id))
