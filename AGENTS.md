# AGENTS.md

面向所有 AI 编码助手（Claude Code / Codex / Cursor / DSH …）的仓库约定。
**本文件是唯一来源**，各工具的私有配置目录不再单独维护规则。

## 代码验证

- 直接运行目标脚本，或启动服务观察日志（loguru）。
- 临时验证脚本请放 `var/tmp/`（已 gitignore）或用 `uv run python -c '...'`。
- 代码改动必须能通过 pre-commit，过不了就不算完成。手动等价命令：

```shell
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python tools/check_layout.py     # 目录契约
.venv/bin/python tools/check_layers.py     # 分层依赖
.venv/bin/pytest -q                        # 单测
```

## 关于 Git

- 任何**只读**命令都可以执行：`git status`、`git log`、`git diff`、`git show` 等。
- **不要做任何改变状态的操作**，包括但不限于 `git add`、`git commit`、`git push`、
  `git checkout --`、`git restore`、`git reset`。
- 改动留在工作区，由人审阅后自行提交。

## 关于需求开发 SOP

需求开发 AI 与 人类基于文档进行协作，需求中的关键文档，以及文档中需要输出的内容，见 `docs/notes/RD-SOP-draft.md`。

## 代码结构规则

### 分层（只允许向下依赖）

```
api → service → graphs → common
```

| 从 \ 到 | api | service | graphs | common | fastapi |
| --- | --- | --- | --- | --- | --- |
| `api` | — | ✅ | ❌ | ✅ | ✅ |
| `service` | ❌ | — | ✅ | ✅ | ❌ |
| `graphs` | ❌ | ❌ | — | ✅ | ❌ |
| `common` | ❌ | ❌ | ❌ | 见下表 | ❌ |

- `if __name__ == "__main__":` 块不参与校验（脚本，允许 import 任意层）。
- 只有 `api/` 允许 import fastapi / starlette；`common`、`graphs`、`service` 一律禁止。
- 由 `tools/check_layers.py` 强制，改动后必须跑通。

### `common` 内部 5 个 tier（只允许依赖更低 tier）

| tier | 模块 | 允许 import |
| --- | --- | --- |
| **0** 基础 | `utils/`（`brief` / `net` / `tokenizer` / `markdown_splitter` / `markdown_image`）、`prompt/` | 仅标准库 / 第三方 |
| **1** 配置 | `config/` | tier 0 |
| **2** 设施 | `logging.py`、`model/` | tier 0–1 |
| **3** 资源 | `client/`、`events/` | tier 0–2 |
| **4** 聚合 | `store/` | tier 0–3 |

- 同 tier 的不同模块 / 子包之间**禁止**互相依赖；同一子包内部自由。
- `common/utils/` **不允许**出现 import 项目内模块的文件——需要配置的函数放 `config/`。
- 路径统一走 `common/config/path_config.py`（`PROJECT_ROOT` 定位 + `FIXTURES_DIR` / `IMPORT_TMP_DIR` / `UPLOAD_TMP_DIR` / `LOG_DIR` / `TMP_DIR` + `fixture_path` / `runtime_tmp_dir` / `snapshot_path`），`.env` 不配置任何路径参数；`env_config` 与 `path_config` 互相独立，`env_config` 自行向上查找 `.env` 文件。
- 新增模块先定 tier 再写代码；tier 表以本节为唯一文档源。

### 模块命名

- 节点函数以 `node_` 开头（= LangGraph 注册名 = SSE 里的节点标识），**不要**随意改名。
- 节点文件名当前仍为 `node_*.py`（与函数名一致）；批量去掉文件名前缀属于后续需求，做时同步改本节。
- `common/utils/` 下不带 `_utils` 后缀（`brief.py` 而非 `brief_utils.py`）。
- 避免与标准库同名：不新建 `token.py` / `tokenize.py`（用 `tokenizer.py`）；`common/logging.py` 是包内子模块，Python 3 绝对导入下不与标准库冲突。
- 一个文件一个主题；超过 400 行考虑拆分。

### 状态词表

后端 `TaskStatus` 是唯一词表，SSE / HTTP 只传后端值：`pending` / `processing` / `complete` / `failed`。

前端 `src/types/app.ts` 1:1 对齐，不得自造 `completed` / `error`；前端本地态只允许 `uploading`（导入前）与 `interrupted`（派生）两个。展示文案只放 `web/src/lib/constants.ts`。

### 项目名

| 场景 | 写法 |
| --- | --- |
| 展示名（页面标题 / NavBar / README / 日志 / API title） | `MiniRAG` |
| Python 标识符（类名等） | `MiniRag` |
| 包 / 容器 / 项目名 | `mini-rag` |
| 存储资源前缀（bucket / db / collection） | `minirag` |
