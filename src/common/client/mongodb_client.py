from pymongo import MongoClient

from common.config.env_config import ENV_CONFIG
from common.logging import logger
from common.utils.net import probe_tcp


class MiniRagMongoClient(MongoClient):
    def __init__(self):
        self.uri = ENV_CONFIG.mongodb.uri
        super().__init__(self.uri)

        self.db_name = ENV_CONFIG.mongodb.db_name
        self.db = self[self.db_name]

    def check_health(self) -> None:
        """连通性自检: TCP 可达 + admin ping 返回 ok。

        pymongo 的 MongoClient 是惰性连接, 构造成功不代表 MongoDB 可达,
        必须实际 ping 一次才能确认服务状态, 因此检查放在本方法而非 __init__。
        """
        probe_tcp(self.uri)
        self.admin.command("ping")
        logger.success(f"MongoDB 连接成功 ({self.uri}), 数据库: {self.db_name}")


if __name__ == "__main__":
    client = MiniRagMongoClient()
    db = client.db
    db.chat_history.delete_many({})  # 清空 chat_history 集合中的所有文档
    db.chat_history.insert_one(
        {
            "session_id": "test_session",
            "timestamp": 1234567890,
            "message": "Hello, world!",
        }
    )
