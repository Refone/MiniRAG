from pymongo import MongoClient
from utils.logging_utils import logger
from common.config.env_config import ENV_CONFIG


class MiniRagMongoClient(MongoClient):
    def __init__(self):
        self.uri = ENV_CONFIG.mongodb.uri
        super().__init__(self.uri)

        self.db_name = ENV_CONFIG.mongodb.db_name
        self.db = self[self.db_name]

        logger.success(f"MongoDB 连接成功, 数据库: {self.db_name}")


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
