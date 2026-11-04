# 项目整理预研报告

<!-- docs-layout: 2026-11 -->
> 状态：已完结（历史快照） · 文中 `src/`、`web/` 为 2026-11 目录改名前的路径，当前对应 `backend/`、`frontend/`；代码现状以仓库为准。索引见 [docs/feat/README.md](../README.md)。

## 一句话结论

分层**意图**是对的、注释密度罕见地高，但有三处"承诺与实现不符"：`utils` 不是底层（它被 `common` 依赖、又依赖 FastAPI）、图节点同时是 service + repository、节点身份用的是中文文案当协议字段。命名上最大的问题是**同一概念存在 2–4 套词表**（项目名、枚举、状态值、文档版本号）。

---

## 一、先肯定做得好的部分（这些不要动）

- `README` + `tools/check_layout.py` 把"目录契约"变成可执行校验，实测 `目录契约一致: 8 条约定, 7 个顶层目录 ✓`
- `ruff check` / `ruff format --check` 全绿（116 文件）
- `task_utils.py` 顶部那张"API 一览"表和 `sse_utils` 的 `sse_*` 前缀约定，是很清晰的模块自述方式
- `.env` → `.env.example` 自动脱敏生成、`node_*` / `step_N_*` / `__main__` 可单跑，工程习惯很成熟
- 前端 `types / lib / store / hooks / utils` 五分离，`preferenceStore` 用 persist、`chat/docsStore` 用内存，按存储方式分层很干净

---

## 二、架构问题（按优先级）

### P0-1 `common` ↔ `utils` 双向依赖，文档里的分层承诺不成立

`docs/web-arch.md` 和 `service/__init__.py` 都写着 `api → service → graphs → common/utils`（utils 在最底层）。实测的跨层 import：

| 方向           | 文件数          | 典型例子                                                                                                                                              |
| -------------- | --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| common → utils | 7（3 处运行时） | `config/env_config.py` → `utils/path_utils.PROJECT_ROOT`；`client/*`、`store/chat_history.py` → `utils/logging_utils`；`client/*` → `utils/net_utils` |
| utils → common | 3               | `logging_utils` → `env_config`；`markdown_utils` → `app_config`；`path_utils` 在函数内反向 import `env_config`（注释说"避免循环"，其实已经循环）      |

问题不在于今天会不会炸（`path_utils` 用了延迟 import 绕开了），而在于**底层模块的边界是假的**：任何人想在 `utils/path_utils` 里加东西，都要考虑会不会和 config 打死结。

**建议**：把"路径 + 日志"这两个真正的基础设施从 `utils` 提到 `common`：

```
src/common/paths.py      # PROJECT_ROOT / FIXTURES_DIR / fixture_path（无任何项目内依赖）
src/common/logging.py    # 原 logging_utils（依赖 paths，不依赖 env_config：日志配置由 init 时传入）
```

`utils/` 只剩纯函数（markdown / text / token / net / brief），`common` 永远不 import `utils`。

### P0-2 `utils` 里装着 Web 传输层，图节点反向依赖了 HTTP

依赖链：`graphs/*/nodes/*` → `utils/node_utils.trace_node` → `utils/task_utils` → `utils/sse_utils` → **`fastapi.Request`**。

后果：最"业务"的一层（graphs）通过一个装饰器间接依赖了 Web 框架；`service` 层注释里"不碰 HTTP 细节"只对了一半（它调 `sse_push`，而 `sse_push` 的实现体在带 FastAPI 的模块里）。

**建议**拆成三块，切断这条链：

```
common/events/bus.py     # 纯队列 + 发布/订阅协议（不 import fastapi），可换 Redis 实现
common/events/registry.py# 替代 task_utils 的 7 个模块级 dict（见 P0-3）
api/sse.py               # 只做 Request → StreamingResponse 的适配
```

节点只"发布事件"，不关心 SSE 还是日志还是 MQ。

### P0-3 进程内全局状态没有淘汰，且隐含"单 worker"前提

- `sse_utils.py:22` `_session_stream: dict[str, queue.Queue]`：`POST /upload`、`POST /query` 时就 `sse_create_queue`，**只有 SSE 生成器的 finally 才 remove**。客户端从不连 SSE（或连之前就放弃）→ 队列永久驻留。
- `task_utils.py` 的 7 张表同样无 TTL / 上限（文件里 U7 TODO 已承认）。
- 这两处都是模块级 dict，一个加锁（`task_utils`）一个不加（`sse_utils`），风格也不统一。

**建议**：抽成一个 `TaskRegistry` 类（单例），统一 `created_at` / `touch()` / `sweep(ttl)`，启动时起一个后台清扫；并在 README 明确写"当前只支持单 worker"，或在 `startup_checks` 里检测 `WEB_CONCURRENCY > 1` 直接告警。

### P0-4 图节点承担了 repository + service + 编排三重职责

`node_document_embedding.py`（430 行）一个节点干了 7 件事：删旧文档 → 3 次 MinIO 上传 → LLM 生成元数据 → embedding → insert docs → insert chunks。`node_process_md_zip.py`（379 行）同理，且从**另一个节点**里 import 了 7 个下划线私有符号：

```python
from graphs.import_graph.nodes.node_process_standalone_md import (
    _IMG_TAG_RE, _MARKDOWN_IMAGE_RE, _build_local_filename, ... )
```

`node_document_embedding.py` 也从 `node_md_img` import `_MD_FIXED_SUFFIX`。

**建议**：

1. 把 MinIO/Milvus 的写操作下沉到 `common/store/document_repo.py`（`save_document(...)` / `delete_document(...)`），节点只做状态流转和错误处理；
2. 共享的正则/图片工具抽到 `utils/markdown_image.py`（现在它们藏在 node 里，未来想复用必须先"偷私有名"）。

这样做的额外收益：这部分今天**完全无法离线测试**（要真 Milvus/MinIO），下沉后可以 mock 掉。

---

### P1-1 节点返回值契约不一致（有它自己的地雷）

| 返回完整 state（并原地 mutate）                                                                                      | 只返回增量                                                                                                                                 |
| -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `node_entry`、`node_pdf_to_md`、`node_md_fork`、`node_process_md_zip`、`node_intent_recognize`、`node_answer_output` | `node_process_standalone_md`、`node_document_split`、`node_md_img`、`node_document_embedding`、全部 `node_search_*`、`node_rrf_and_rerank` |

`node_document_split.py:96` 和 `node_md_img.py:383` 都有同一段注释解释"返回完整 state 会在并发分支触发 `InvalidUpdateError`"——也就是说**这个契约是被 bug 教出来的，但只打了补丁没统一**。同样的图里两种写法并存，下一个加节点的人一定会踩。

**建议**：硬性规定"节点只返回增量、不 mutate state"，并用一个 20 行的单测/校验脚本兜住（遍历 `nodes/__init__.__all__` 断言调用后入参未被修改）。

### P1-2 `trace_node` 的 `desc` 实际成了协议字段，而 docstring 说的是函数名

`node_utils.py:150-156`：`description = desc or func.__name__` → `_task_trace(description)` → `add_running_node(trace_id, node_name=description)`。我实测验证了：

```
done_list = ['答案输出']     # 不是 'node_answer_output'
```

而 `node_utils.py:146` 写的是"任务追踪以函数名 `func.__name__` 作为节点标识, 与 LangGraph 节点名一致"。三个衍生问题：

1. 改一句 UI 文案 = 改 SSE 协议；
2. 无法 i18n，也无法在前端做图标/分组映射；
3. **同一图里两个节点 desc 相同时会被 `if node_name not in running` 静默吞掉**（今天恰好没有重名，非常脆）。

**建议**：`trace_node(name="answer_output", desc="答案输出")`，`name` 进协议、`desc` 只进日志；前端用 `name` 查展示表。

### P1-3 枚举风格三种并存 + 前后端状态词表两套

| 写法             | 例子                                                               |
| ---------------- | ------------------------------------------------------------------ |
| `StrEnum`        | `TaskStatus`、`MessageRole`、`LogLevel`                            |
| 普通类字符串常量 | `FileType`、`DataFrom`、`SSEEvent`、`Milvus*Field`、`Milvus*Index` |

状态值更是四套词：后端 `complete` / `failed`，前端 `completed` / `error`，`ProgressView.status` 注释写 `completed` 但 store 里直接透传后端值，`PROGRESS_STATUS_LABELS` 里的 `completed` 永远收不到后端 `complete`。今天没炸，是因为 chat 的终态由 `finishTask()` 本地归一、import 的终态由 `CHILD_STATUS_MAP` 映射——**靠约定维持，不是靠类型**。

**建议**：封闭集合统一 `StrEnum`；SSE 只传后端值，前端**只在一处**（`lib/constants.ts`）做映射表。

### P1-4 API 契约风格三种

- `upload` / `docs` → Pydantic `response_model`
- `query` / `history` / `delete_history` → 裸 dict `{status: "ok", msg: ...}`（无模型、Swagger 里看不出结构）
- `delete_doc` 部分失败 → 手写 `JSONResponse({"success": false, "detail": ...})`

另外：`docs_service.list_docs()` 返回 `{"total": ..., "list": ...}`，`list` 遮蔽内建名，建议 `items`。前端 `types/chat.ts` 的 `QueryResponse` 声明了 `answer / done_list / error / message`，但后端 `POST /api/query` 只回 `status / msg / session_id`——**类型在撒谎**（今天只用 `session_id` 所以没暴露）。

### P1-5 两处重复常量靠注释维持一致

`minio_client.py:13` 与 `docs_service.py:18` 各定义一次 `_PROXY_FILES_PREFIX = "/api/files/"`，后者的注释写"与 minio_client.\_PROXY_FILES_PREFIX 保持一致"。抽到一个地方（比如随 `MinioSettings` 走，或 `common/paths.py`）。

### P1-6 图里混入了 prompt 格式化与持久化细节

`common/store/chat_history.py` 的 `summary_history()` 在持久化类里拼 prompt 文本（`"历史对话 {i} | 用户提问 | ..."`）。持久层应该只返回 `list[ChatMessage]`，拼装交给 `common/prompt`。同理 `docs_service` 里做了 MinIO 读取 + JSON 解析 + 级联删除，其实已经是"service"了，可以接受，但它返回 dict 而不是 schema（见 P1-4）。

---

### P2 依赖与死代码（都是 5 分钟能改的）

**依赖声明漂移**（`pyproject.toml`）：

| 类型                                 | 包                                                                                                                                 |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| 直接 import 但没声明                 | `httpx2`、`mcp`、`mcp-types`（`node_search_web.py:4-9`，靠 `openai-agents` 传递依赖，一旦上游换实现就断）                          |
| 声明了但全仓 0 引用                  | `openai-agents`、`langchain-community`、`python-dotenv`、`regex`                                                                   |
| 只有 `__main__` 的 `draw_ascii()` 用 | `grandalf`（应进 `[dependency-groups] dev`）                                                                                       |
| 死配置                               | `llm_tpm` / `vlm_tpm` / `embedding_tpm` / `rerank_tpm` 四个 TPM 在 `.env`、`.env.example`、`env_config.py` 三处都有，代码里 0 引用 |

**死代码**：

- `utils/path_utils.py`：`from_project_root`、`get_path_dir`、`get_src_root` + 模块级 `SRC_ROOT`（只被自己的 `__main__` 用）
- `utils/task_utils.py`：`get_task_results`、`get_task_failed_nodes`、`get_task_result`（只有注释里出现过）
- 两个 `*_state.py` 的 `get_default_state()`
- `web/src/store/sessionStore.ts` 整个文件没人 import（PRD 预留骨架）
- `web/src/hooks/useScrollRestore.ts:96` 有 `// eslint-disable-next-line react-hooks/exhaustive-deps`，但项目根本没有 eslint
- `api/main.py` 里 `delete_doc` 与 `get_doc_detail` 重复了同一段 `int(doc_id)` + 404 逻辑（可用 path converter + exception handler 收口）

**遗留调试输出**：`minio_client.py:188-190` 在生产路径上 `from rich import print as rprint; rprint(res)`——**每上传一个文件就往 stdout 打 SDK 响应**。

---

### P3 工程流程

| 问题                               | 现状                                                                                                                                       | 建议                                                                                                                                                                                        |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 没有测试                           | `tests/` 只有 fixtures，无 pytest 依赖                                                                                                     | 先给 4 个纯函数补 pytest：`markdown_splitter`、`task_utils`、`step_2_rrf_fusion`、`step_4_dynamic_topk`——全是零外部依赖                                                                     |
| 没有 CI                            | 无 `.github/`；AGENTS.md 要求"必须过 pre-commit"但没有闸门                                                                                 | 一个 workflow：`ruff check` + `ruff format --check` + `pytest` + `npm ci && npm run build`                                                                                                  |
| 前端无 lint/format                 | 只有 `tsc --noEmit`，格式已漂移                                                                                                            | prettier + eslint，挂进 pre-commit 的 local hook                                                                                                                                            |
| ruff 规则偏窄                      | 只有 `E4/E7/E9/F/I`                                                                                                                        | 加 `B`（mutable default）、`UP`、`SIM`、`RUF`、`G`（日志格式化）。现成收益：`milvus_client.py:170` `doc_ids: list[int] = None` 注解错、`:221` `output_fields: list[str] = ["*"]` 可变默认值 |
| 日志风格                           | **f-string 108 处 vs `{}` 9 处**；且 `logger.info(f"从 Milvus 中选取的结果: {hits}")`、`待重排序文档内容: {documents}` 把整段正文打进 INFO | 统一 `{}` 惰性格式化（G 规则自动查），内容类日志降到 DEBUG + 复用现成的 `brief()`                                                                                                           |
| `39/65` 个模块带 `__main__` 调试块 | 每个都硬编码 fixture + snapshot JSON                                                                                                       | 这个习惯本身不坏，但它是"手写测试框架"；把其中可断言的部分平移成 pytest，`__main__` 只留"交互式点火"                                                                                        |
| Docker                             | 前端 `npm install`（非确定性）                                                                                                             | 改 `npm ci`（`package-lock.json` 已提交）                                                                                                                                                   |
| 包管理器混用                       | `web/node_modules` 是 pnpm 装的（有 `.pnpm/` + `.modules.yaml`），但仓库只提交 `package-lock.json`                                         | 二选一，删掉另一套产物                                                                                                                                                                      |
| 版本号三处                         | `pyproject` / `api.__version__` / `web/package.json` 全是 0.1.0                                                                            | 后端从 `importlib.metadata` 取，或单源注入                                                                                                                                                  |
| `pyproject` 的 hatch wheel 配置    | `only-include` + `sources`，但 Dockerfile 是 `--no-install-project`，实际不打包                                                            | 要么做成可安装包（顺势解决 `sys.path` 问题），要么删掉免得误导                                                                                                                              |

---

## 三、命名问题（这部分是你问的重点）

### 3.1 项目名有 4 种写法

| 写法       | 出现位置                                                                                                             |
| ---------- | -------------------------------------------------------------------------------------------------------------------- |
| `MiniRAG`  | `web/index.html` title、`NavBar.tsx:19`、所有原型 html                                                               |
| `MiniRag`  | `README.md:1`、`pyproject.description`、`api/main.py:39` 日志、`title="MiniRag API"`、类名前缀 `MiniRagMilvusClient` |
| `mini-rag` | `pyproject.name`、`web/package.json` name、3 个 compose 的 `name:`、容器名                                           |
| `minirag`  | bucket `minirag`、db `minirag`、集合 `minirag_docs/chunks`、`_minirag_hybrid_search`                                 |

建议定一条规则并写进 AGENTS.md：**展示名 `MiniRAG` / 包与容器 `mini-rag` / 存储资源前缀 `minirag`**。现在是随机分布。

### 3.2 三个 client 的封装方式不一致

```python
class MiniRagMilvusClient(MilvusClient): ...  # 继承


class MiniRagMongoClient(MongoClient): ...  # 继承


class MiniRagMinioClient: ...  # 组合
```

且 `Milvus`/`Mongo` 直接继承 SDK 类，把 SDK 的所有私有 API 都暴露成自己的 API（`_minirag_hybrid_search` 里就调了 `super().hybrid_search`）。建议统一组合，或至少统一后缀。

### 3.3 单例的暴露位置不一致

| 位置                                                     | 形态                                                           |
| -------------------------------------------------------- | -------------------------------------------------------------- |
| `common/client/__init__.py`                              | `MILVUS_CLIENT = ...`（全大写，import 即有副作用）             |
| `common/model/__init__.py`                               | `EMBEDDING / RERANKER / LLM / VLM`（同上）                     |
| `common/store/__init__.py`                               | **空**，单例在 `chat_history.py` 里小写 `chat_history_manager` |
| `common/config/__init__.py`、`common/prompt/__init__.py` | **空**                                                         |

同一个 `common/` 下四种约定。建议要么全部"`__init__` 暴露大写单例"，要么全部"`get_xxx()` 工厂"。

### 3.4 目录名与文件名的冗余前缀

- `common/prompt/prompt_*.py`：目录已叫 prompt，8 个文件仍以 `prompt_` 开头
- `graphs/*/nodes/node_*.py`：目录已叫 nodes，8+6 个文件仍以 `node_` 开头，函数名也叫 `node_*`

建议 `nodes/entry.py::node_entry`（保留函数前缀，因为它是 LangGraph 的注册名）或 `nodes/entry.py::run_entry`。至少去掉**文件名**那一层重复。

### 3.5 `api/main.py` 端点动词不统一

| 现有                                          | 建议                                        |
| --------------------------------------------- | ------------------------------------------- |
| `import_document` / `query`                   | `create_import` / `run_query`               |
| `upload_sse` / `query_sse`                    | `stream_import` / `stream_query`            |
| `history` / `delete_history`                  | `list_history` / `delete_history`           |
| `list_docs` / `get_doc_detail` / `delete_doc` | 统一 `list_docs` / `get_doc` / `delete_doc` |
| `get_file`                                    | `get_file` ✅                               |

另外 `def query` 是同步函数、`async def import_document` 是异步，同一文件两种风格。

### 3.6 `sse_utils` 的双下划线

```python
__DEBUG__ = False
def __debug_print(...)      # 模块级用 __ 前缀会触发 name mangling 语义误导
sse_create_queue / sse_get_queue / sse_remove_queue   # 前缀重复模块名
```

模块内部私有应单下划线；既然按模块导入了 `sse_push`，函数名里的 `sse_` 也可以省（`bus.push` 更自然）。

### 3.7 前端命名

- `ChatMessage.role: "user" | "bot"`（后端是 `user | assistant`）
- `types/docs.ts` 里 `ImportFile`（其实是任务）、`ImportChildTask`（是子任务）→ `ImportTask` / `ImportChildTask`
- `types/app.ts` 的 `StatusResponse` 同时描述 query 和 upload 两种载荷（只有 query 有 `answer`）→ 拆两个
- `DocsSidePanel.tsx`：`onUploadFiles={(list) => onUploadFiles(list)}` 纯多余包裹
- `ImportChildStatus` 的展示映射 `IMPORT_CHILD_STATUS` 是数组，而 `PROGRESS_STATUS_LABELS` 是 Record——同一个 `lib/constants.ts` 里两种映射形态
- 引号：`main.tsx`、`utils/text.ts`、`utils/markdown.ts` 混用单引号，其余全双引号；`docsStore.ts:106` 起整个 action 块多缩进一层（合并残留）

### 3.8 docs 命名是最乱的一块

同一目录 `docs/feat/数据库重构/` 三种风格 + 一个 typo：

```
Milvs DB Refactor.md              ← 文件名还是 "Milvs"，git log 里有 "typo error: Milvs -> Milvus" 但只改了代码
Milvus minirag_docs_meta db design.md
milvus_db_design.md
```

而且 `node_document_embedding.py:65` 引用的正是 `docs/feat/数据库重构/Milvus DB Refactor.md`——**这条引用已经 404 了**。

版本后缀 5 种：`v0/v1/V0/V1`、`P1/P2`、`-1`、`demo-v0..v4`（还混一个裸 `demo.html`）、`评审v0/v1` vs `评审反馈-v0`。原型 html 累计 ~1.2 万行、docs 共 7.3MB。

建议：`docs/feat/<feature>/README.md`（终态索引）+ `design/ implementation/ review/ prototype/`；旧原型整目录移到 `docs/prototype/` 或直接归档；文件名统一"小写连字符或中文 + 固定后缀"。

### 3.9 文档与代码不同步

- `docs/setup.md:32` 列的软依赖 `VLM_API_KEY / QWEN_API_KEY / LLM_API_KEY` 已不存在，`startup_checks._API_KEY_CHECKS` 只有 `MINERU_API_KEY` / `DASHSCOPE_API_KEY`
- `docs/web-arch.md` 前半段是历史问答（"src/api 早期只有一个占位模块"），虽有 ⚠️ 声明，但仍会误导新读者
- `AGENTS.md` 最后一条："**代码改动必须能通过 pre-commit，过不了就不算完成：**" —— 冒号后面是空的，句子没写完

---

## 四、顺手发现的 bug（不属于命名，但会在真实流量下出问题）

| #   | 位置                                              | 问题                                                                                                                                                                                         |
| --- | ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `node_md_img.py:268-272`                          | 图片上传失败时 `image_url_dict` 无该 key，`url=None`，最终 md 写成 `![摘要](None)` / `src="None"`，且仍计入替换计数                                                                          |
| 2   | `node_pdf_to_md.py:31,41`                         | `file_title = Path(origin).stem` 立刻被 `state.get("file_title")` 覆盖（死赋值）；docstring 声称"把文件名写入 state"，实际没写                                                               |
| 3   | `api/main.py:85-90`                               | 上传落盘用 `upload_dir / Path(file.filename).name`：**并发同名文件互相覆盖**（`task_id` 生成了但没用上）；`await file.read()` 全量入内存，无大小上限                                         |
| 4   | `sse_utils.py:76-80`                              | 每个 SSE 连接常驻一个线程池线程做 0.1s 轮询的 `run_in_executor`；`asyncio.get_event_loop()` 应为 `get_running_loop()`。连接数一多线程池就顶穿，建议 `asyncio.Queue` + `call_soon_threadsafe` |
| 5   | `service/query_service.py` vs `import_service.py` | 失败路径不一致：import 推 `ERROR + CLOSE`，query 只推 `ERROR` 不推 `CLOSE`，前端只能靠 `closeOnServerError` 的隐含约定兜（chat 传默认 true、import 传 false）                                |
| 6   | `logging_utils.py:97`                             | 每条日志 `inspect.stack()`（构建整个 FrameInfo 列表），热路径开销；应改为 `f_back` 向上走两帧或直接依赖 loguru                                                                               |
| 7   | `chatStore.ts:200+`                               | `openStatusSse` 的 `onServerClose` 里引用 `handle`（TDZ 模式）；当前靠 EventSource 异步派发躲过，但改同步回调就炸                                                                            |

---

## 五、建议的落地顺序（每批都可独立提交、可回滚）

**第 1 批 · 零风险清理（半天）**
删死代码 / 删 4 个 TPM / 删 `rprint` / 修 `docs/setup.md` + `AGENTS.md` + 那条断链 / 依赖声明补 `httpx2,mcp,mcp-types` 删 4 个无用包 / `npm ci` / 前端加 prettier。

**第 2 批 · 命名归一（1 天）**
项目名规则写进 AGENTS.md；`StrEnum` 统一封闭集合；SSE 状态只传后端值+前端单点映射；`trace_node(name=, desc=)` 拆开；`_PROXY_FILES_PREFIX` 收口；`api` 端点动词重命名；`nodes/` 文件名去 `node_` 前缀。

**第 3 批 · 结构重构（2–3 天，需要一次性想清楚）**
`common/paths.py` + `common/logging.py` → 解开 common↔utils 环；`common/events/` + `api/sse.py` → 切断 graphs→fastapi；`TaskRegistry` 类 + TTL 清扫；`document_repo` 下沉；节点统一"只返回增量"。

**第 4 批 · 补闸门**
pytest（先 4 个纯函数）+ GitHub Actions + 前端 eslint/prettier 进 pre-commit。

---

需要我接着动手的话，告个范围就行：**(a)** 只做第 1 批的零风险清理；**(b)** 加做第 2 批命名归一；**(c)** 把这份评审写成 `docs/` 下的文档；**(d)** 直接上第 3 批结构重构（我会先给改动清单再动手）。默认我推荐 **a + b**——收益最大、Review 成本最低，第 3 批单独开一次。
