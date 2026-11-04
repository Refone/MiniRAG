"""pytest 全局引导：环境隔离、anyio backend、运行态清理。"""

import os

import pytest

# 默认套件不读取本机 .env 里的真实 key；live 层显式放行。
if os.getenv("RUN_LIVE_TESTS") != "1":
    os.environ.setdefault("DASHSCOPE_API_KEY", "test-dummy")
    os.environ.setdefault("MINERU_API_KEY", "test-dummy")

# 任何 common.* import 之前冻结测试资源名，避免 pytest 收集整棵树时误用生产库。
os.environ.setdefault("MONGODB_DB_NAME", "minirag_test")
# S3/MinIO bucket 名不允许下划线, 其余测试资源仍沿用 minirag_test_* 前缀
os.environ.setdefault("MINIO_BUCKET_NAME", "minirag-test")
os.environ.setdefault("MILVUS_COLLECTION_DOCS", "minirag_test_docs")
os.environ.setdefault("MILVUS_COLLECTION_CHUNKS", "minirag_test_chunks")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def sample_markdown() -> str:
    """两级标题 + 正文的最小样本。"""
    return "## 一级\n正文 A\n\n### 二级\n正文 B\n"


@pytest.fixture(autouse=True)
def _clean_runtime():
    from common.events import EVENT_BUS, TASK_MANAGER

    EVENT_BUS.clear_all()
    TASK_MANAGER.clear_all()
    yield
    EVENT_BUS.clear_all()
    TASK_MANAGER.clear_all()
