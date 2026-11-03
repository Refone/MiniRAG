"""资源客户端（tier 3）：Milvus / MinIO / MongoDB / Web 搜索 / MinerU。

访问器定义在各客户端文件底部，这里只 re-export；
业务侧一律 `from common import client` 后调用 `client.get_xxx()`，
模块 import 不建立任何外部连接。
"""

from .milvus_client import get_milvus_client
from .mineru_client import mineru_pdf_to_md
from .minio_client import get_minio_client
from .mongodb_client import get_mongo_client
from .web_search import search_web

__all__ = [
    "get_milvus_client",
    "get_minio_client",
    "get_mongo_client",
    "search_web",
    "mineru_pdf_to_md",
]
