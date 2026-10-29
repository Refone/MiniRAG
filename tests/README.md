# tests/

分两类：

| 目录 / 文件 | 作用 | 怎么跑 |
| --- | --- | --- |
| `test_*.py` | pytest 用例：只覆盖**零外部依赖**的部分（切分 / 摘要 / RRF / 动态 TopK / 任务状态机 / 事件总线 / 删除顺序） | `.venv/bin/pytest` |
| `fixtures/` | 各节点 `if __name__ == "__main__":` 手工调试 + 端到端验收用的**样例输入** | 见下 |

需要 Milvus / MinIO / LLM 的链路不写自动化用例，靠节点 `__main__` 点火 +
`docs/feat/项目整理/方案设计.md` §8.3 的人工回归清单。

`fixtures/` 统一通过 `common.utils.paths.fixture_path("<文件名>")` 引用，不要写死路径：
统一通过 `common.utils.paths.fixture_path("<文件名>")` 引用，不要写死路径：

```python
from common.utils.paths import fixture_path

origin_file_path = str(fixture_path("hello-agent.md"))
```

| 文件 | 用途 |
| --- | --- |
| `test.txt` | 不支持的文件类型（异常分支） |
| `hello-agent.md` | 单文件 Markdown 导入流程 / 切分 |
| `RAG.png` | VLM 图片理解 |
| `hak180产品安全手册.pdf` | PDF -> Markdown 导入流程 |
| `万用表RS-12的使用.pdf` | PDF 导入 / 全图流程点火 |
| `华为擎云 S520 Gen2 用户指南-*.pdf` | 大体量 PDF（分页 / 超时场景） |
| `LangGraph 学习笔记.zip` | md + 图片的 zip 导入流程 |

> 体积合计约 13 MB，`tests` 已在 `.dockerignore` 中排除，不进运行镜像。
