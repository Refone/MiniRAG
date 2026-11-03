import shutil

from common import client
from common.config.env_config import ENV_CONFIG
from common.config.path_config import IMPORT_TMP_DIR, UPLOAD_TMP_DIR


def clean_db():
    milvus = client.get_milvus_client()
    print("删除 Milvus 集合")
    for collection_name in (
        ENV_CONFIG.milvus.collection_docs,
        ENV_CONFIG.milvus.collection_chunks,
    ):
        if milvus.has_collection(collection_name):
            milvus.drop_collection(collection_name)

    print("删除 MinIO 桶")
    client.get_minio_client().remove_bucket()

    print("删除 MongoDB 数据库")
    client.get_mongo_client().drop_database(ENV_CONFIG.mongodb.db_name)


def rebuild_db():
    milvus = client.get_milvus_client()
    print("重建 Milvus 集合")
    milvus.prepare_docs_collection()
    milvus.prepare_chunks_collection()

    print("重建 MinIO 桶")
    client.get_minio_client().prepare_bucket()


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
