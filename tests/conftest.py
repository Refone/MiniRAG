"""pytest 公共夹具。

本仓库的测试只覆盖"零外部依赖"的部分：纯函数（切分 / 摘要 / RRF / 动态 TopK）
与进程内任务状态机。需要 Milvus / MinIO / LLM 的链路仍靠各节点 `__main__`
点火 + `docs/feat/` 里的人工回归清单。
"""

import pytest


@pytest.fixture
def sample_markdown() -> str:
    """两级标题 + 正文的最小样本。"""
    return "## 一级\n正文 A\n\n### 二级\n正文 B\n"
