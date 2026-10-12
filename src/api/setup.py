from common.client import MILVUS_CLIENT
from utils.logging_utils import logger


def init_milvus_collections() -> None:
    logger.info("校验并初始化 Milvus 集合 (kb_item_name / kb_chunks) ...")

    MILVUS_CLIENT.prepare_item_name_collection()
    MILVUS_CLIENT.prepare_chunks_collection()

    logger.info("Milvus 集合校验完成")


def setup() -> None:

    logger.info("执行后端启动 setup ...")

    try:
        init_milvus_collections()
    except Exception:
        logger.exception(
            "Milvus 集合初始化失败: 请确认 Milvus 已启动且 MILVUS_ENDPOINT 配置正确"
        )
        raise

    logger.info("后端启动 setup 完成")
