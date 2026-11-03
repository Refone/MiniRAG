"""import 卫生：空 key + 不可达 Mongo/Milvus 时 api.main 仍可 import。"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def test_import__no_key_no_infra__api_main_imports():
    """Given 空 key 且 Mongo/Milvus 不可达 When import api.main Then 成功。"""
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(ROOT / "src"),
            "DASHSCOPE_API_KEY": "",
            "MINERU_API_KEY": "",
            "MONGODB_URI": "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=200",
            "MILVUS_ENDPOINT": "http://127.0.0.1:1",
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", "import api.main"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (
        "空 key / 不可达 infra 下 import api.main 失败：\n" + result.stderr[-2000:]
    )
