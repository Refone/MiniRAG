import shutil

from common.client import (
    MILVUS_CLIENT,
    MINIO_CLIENT,
    MONGODB_CLIENT,
)
from common.config.env_config import ENV_CONFIG
from common.config.path_config import IMPORT_TMP_DIR, UPLOAD_TMP_DIR


def clean_db():
    print("删除 Milvus 集合")
    for collection_name in (
        ENV_CONFIG.milvus.collection_docs,
        ENV_CONFIG.milvus.collection_chunks,
    ):
        if MILVUS_CLIENT.has_collection(collection_name):
            MILVUS_CLIENT.drop_collection(collection_name)

    print("删除 MinIO 桶")
    MINIO_CLIENT.remove_bucket()

    print("删除 MongoDB 数据库")
    MONGODB_CLIENT.drop_database(ENV_CONFIG.mongodb.db_name)


def rebuild_db():
    print("重建 Milvus 集合")
    MILVUS_CLIENT.prepare_docs_collection()
    MILVUS_CLIENT.prepare_chunks_collection()

    print("重建 MinIO 桶")
    MINIO_CLIENT.prepare_bucket()


def clean_output_dir():
    if IMPORT_TMP_DIR.exists():
        print(f"删除输出目录 {IMPORT_TMP_DIR}")
        shutil.rmtree(IMPORT_TMP_DIR)


def clean_upload_dir():
    if UPLOAD_TMP_DIR.exists():
        print(f"删除上传目录 {UPLOAD_TMP_DIR}")
        shutil.rmtree(UPLOAD_TMP_DIR)


if __name__ == "__main__":
    clean_db()
    clean_output_dir()
    clean_upload_dir()
    rebuild_db()
