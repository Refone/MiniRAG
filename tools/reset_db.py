from common.client import *
from common.config.app_config import APP_CONFIG
from common.config.env_config import ENV_CONFIG
import shutil
import os


def clean_db():
    print("删除 Milvus 集合")
    for collection_name in (
        ENV_CONFIG.milvus.collection_item_name,
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
    MILVUS_CLIENT.prepare_item_name_collection()
    MILVUS_CLIENT.prepare_chunks_collection()

    print("重建 MinIO 桶")
    MINIO_CLIENT.prepare_bucket()


def clean_output_dir():
    output_dir = ENV_CONFIG.mineru.unzip_dir
    if os.path.exists(output_dir):
        print(f"删除输出目录 {output_dir}")
        shutil.rmtree(output_dir)


def clean_upload_dir():
    upload_dir = APP_CONFIG.upload_dir
    if os.path.exists(upload_dir):
        print(f"删除上传目录 {upload_dir}")
        shutil.rmtree(upload_dir)


if __name__ == "__main__":
    clean_db()
    clean_output_dir()
    clean_upload_dir()
    rebuild_db()
