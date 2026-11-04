"""Token 用量持久化（tier 4）。

`token_usage` 集合：每个浏览器会话一行（session_id 唯一索引），
query_*/upload_* 拆分列经 `$inc` 原子累计；PRD 的四模型字段与
total_tokens 在读取时由两口径派生（见 `common.schema.token_usage`）。

与 `chat_history` 的差异：读取失败显式抛领域异常（由 api 译成 500），
不复刻吞异常返回 0 值的风格——前端面板需要可区分的错误态。
"""

from datetime import datetime
from functools import lru_cache

from common import client
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
    """token_usage 集合的读写：get_usage 读快照、add_usage 原子累计、clear_usage 重置。"""

    def __init__(self):
        self.token_usage = client.get_mongo_client().db["token_usage"]

    def prepare(self) -> None:
        """索引初始化（幂等），由启动自检调用。"""
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

    def clear_usage(self, session_id: str) -> int:
        """删除会话统计记录（重置为无记录的空统计态），返回删除条数。

        只动 `token_usage` 集合，不触碰 `chat_history`；无记录时幂等返回 0。
        """
        try:
            result = self.token_usage.delete_one({"session_id": session_id})
        except Exception as e:
            logger.error(f"重置 {session_id} token 统计失败: {e}")
            raise TokenUsageStoreError("Token 统计重置失败") from e

        logger.info(f"重置 {session_id} token 统计, 删除记录 {result.deleted_count} 条")
        return result.deleted_count

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


@lru_cache(maxsize=1)
def get_token_usage_manager() -> TokenUsageManager:
    """Token 用量管理器；首次调用时构造。"""
    return TokenUsageManager()


if __name__ == "__main__":
    from rich import print as rprint

    session_id = "test_token_session"
    manager = get_token_usage_manager()
    manager.add_usage(
        session_id,
        user_ip="127.0.0.1",
        scope=TokenScope.QUERY,
        usage={
            "llm_tokens": 620,
            "embedding_tokens": 905,
            "reranker_tokens": 350,
        },
    )
    manager.add_usage(
        session_id,
        user_ip="127.0.0.1",
        scope=TokenScope.UPLOAD,
        usage={
            "llm_tokens": 486,
            "vlm_tokens": 1264,
            "embedding_tokens": 890,
        },
    )
    rprint(manager.get_usage(session_id))
