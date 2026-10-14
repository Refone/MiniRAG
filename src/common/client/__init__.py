from .milvus_client import MiniRagMilvusClient
from .minio_client import MiniRagMinioClient
from .mongodb_client import MiniRagMongoClient

MILVUS_CLIENT = MiniRagMilvusClient()
MINIO_CLIENT = MiniRagMinioClient()
MONGODB_CLIENT = MiniRagMongoClient()
