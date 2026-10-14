from datetime import datetime
from typing import TypedDict

from common.client import MONGODB_CLIENT
from common.config.app_config import APP_CONFIG
from utils.logging_utils import logger
from pymongo import DESCENDING


class ChatMessage(TypedDict):
    session_id: str
    role: str
    text: str
    key_words: list[str]
    image_urls: list[str]
    timestamp: float


class ChatHistoryManager:
    def __init__(self):
        self.chat_history = MONGODB_CLIENT.db["chat_history"]
        # create index 自带幂等性: 索引已存在时不会重复创建
        self.chat_history.create_index([("session_id", 1), ("timestamp", -1)])

    def clear_history(self, session_id) -> int:
        try:
            result = self.chat_history.delete_many({"session_id": session_id})
            logger.info(f"清除 {session_id} 会话记录 {result.deleted_count} 条")
            return result.deleted_count
        except Exception as e:
            logger.error(f"清除 {session_id} 会话记录失败: {e}")
            return 0

    def save_message(
        self,
        session_id: str,  # 会话 ID
        role: str,  # 角色
        text: str,  # 文本内容
        key_words: list[str] = [],  # 关键字列表
        image_urls: list[str] = [],  # 图片 URL 列表
    ) -> str | None:
        ts = datetime.now().timestamp()

        document: ChatMessage = {
            "session_id": session_id,
            "role": role,
            "text": text,
            "key_words": key_words,
            "image_urls": image_urls,
            "timestamp": ts,
        }

        try:
            result = self.chat_history.insert_one(document)
            logger.info(f"保存 {session_id} 会话记录成功: {result.inserted_id}")
            return result.inserted_id
        except Exception as e:
            logger.error(f"保存 {session_id} 会话记录失败: {e}")
            return None

    def get_latest_messages(
        self,
        session_id: str,
        limit: int = APP_CONFIG.chat_message_lookback_count,
    ) -> list[ChatMessage]:
        try:
            cursor = (
                self.chat_history.find(
                    {"session_id": session_id},
                    {
                        "_id": False
                    },  # 不返回 MongoDB 自动生成的 _id 字段, ObjectId 类型不可序列化
                )
                .sort("timestamp", DESCENDING)
                .limit(limit)
            )
            messages: list[ChatMessage] = list(cursor)

            logger.debug(f"获取 {session_id} 会话的最新 {limit} 条记录: {messages}")

            return messages
        except Exception as e:
            logger.error(f"获取 {session_id} 会话的最新 {limit} 条记录失败: {e}")
            return []


chat_history_manager: ChatHistoryManager = ChatHistoryManager()

if __name__ == "__main__":
    session_id = "test_session"

    # chat_history_manager.clear_history(session_id)
    chat_history_manager.save_message(
        session_id=session_id,
        role="user",
        text="Hello, world!",
        key_words=[],
        image_urls=[],
    )
    chat_history_manager.save_message(
        session_id=session_id,
        role="assistant",
        text="你好我的朋友, 很高兴见到你!",
        key_words=["item1", "item2"],
        image_urls=["http://example.com/image1.jpg", "http://example.com/image2.jpg"],
    )
    chat_history_manager.save_message(
        session_id=session_id,
        role="user",
        text="这个 item1 怎么退货?",
        key_words=["item1", "item3"],
        image_urls=["http://example.com/image1.jpg", "http://example.com/image2.jpg"],
    )
    latest_messages = chat_history_manager.get_latest_messages(session_id)
    for message in latest_messages:
        print(message)
