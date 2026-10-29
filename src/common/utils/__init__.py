"""纯工具函数（tier 0）：零项目内依赖，可被任意层 import。

| 模块 | 内容 |
| --- | --- |
| `brief` | 日志与调试用的简短格式化（`brief` / `brief_list` / `brief_dict`） |
| `net` | `probe_tcp()` 连通性探测 |
| `tokenizer` | `compute_token()` 本地 Qwen 分词计数 |
| `markdown_splitter` | Markdown 按标题切分 + 超长二次切分 |
| `markdown_image` | Markdown/HTML 图片引用的定位、下载与改写 |

约束：本包内**不允许** import 项目内其他模块（路径配置在
`common.config.path_config`）。不在这里 re-export，避免 `import common.utils`
就加载 chunkana / tiktoken 词表。
"""
