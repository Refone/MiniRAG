# tests/

**这里没有测试用例，只有样例输入。**

`fixtures/` 存放各节点 `if __name__ == "__main__":` 手工调试时的输入文件，
统一通过 `utils.path_utils.fixture_path("<文件名>")` 引用，不要写死路径：

```python
from utils.path_utils import fixture_path

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

将来引入 pytest 时，用例放 `tests/` 根下（`test_*.py`），断言用的输入仍放 `fixtures/`。

> 体积合计约 13 MB，`tests` 已在 `.dockerignore` 中排除，不进运行镜像。
