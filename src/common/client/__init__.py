"""资源客户端（tier 3）：Milvus / MinIO / MongoDB。

单例定义在各客户端文件底部，这里只 re-export，
业务侧一律 `from common.client import XXX`。
"""

from .milvus_client import MILVUS_CLIENT
from .minio_client import MINIO_CLIENT
from .mongodb_client import MONGODB_CLIENT

__all__ = ["MILVUS_CLIENT", "MINIO_CLIENT", "MONGODB_CLIENT"]
