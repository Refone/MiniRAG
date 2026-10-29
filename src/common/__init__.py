"""`common`：唯一共享层。

分层依赖（只允许向下）：

```
api → service → graphs → common
```

`common` 内部 5 个 tier（只允许依赖更低 tier）：

| tier | 模块 | 允许 import |
| --- | --- | --- |
| 0 基础 | `utils/`、`prompt/` | 仅标准库 / 第三方 |
| 1 配置 | `config/` | tier 0 |
| 2 设施 | `logging.py`、`model/` | tier 0–1 |
| 3 资源 | `client/`、`events/` | tier 0–2 |
| 4 聚合 | `store/` | tier 0–3 |

规则：
- 同 tier 的不同模块 / 子包之间禁止互相依赖；同一子包内部自由。
- `common/utils/` 不允许出现 import 项目内模块的文件（需要配置的放 `config/`）。
- `common` 任何模块都不得 import fastapi / starlette。

由 `tools/check_layers.py` 强制，改完跑一次。
"""
