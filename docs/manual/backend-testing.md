# 后端测试

pytest 分层：默认只跑 `unit + contract`，不需要 API key、不需要 Docker，目标 < 10s。

```shell
.venv/bin/pytest -q                         # 默认：unit + contract
.venv/bin/pytest -m unit                    # 纯逻辑/节点编排
.venv/bin/pytest -m contract                # API/SSE 契约
.venv/bin/pytest -m integration             # 真 Mongo/MinIO/Milvus（按需）
RUN_LIVE_TESTS=1 .venv/bin/pytest -m live   # 真模型/真 key（手动）
```

Agent 迭代主路径：

```shell
.venv/bin/pytest -q            # 改完先跑
.venv/bin/pytest --lf          # 只跑上次失败
.venv/bin/pytest -k <函数名>   # 按用例名过滤
```

## 分层

| 层 | 默认 | 依赖 | 看护 |
| --- | --- | --- | --- |
| `unit` | ✅ | 无 | 纯函数、状态机、节点编排、service 流程 |
| `contract` | ✅ | 无（TestClient 不起 lifespan） | 路由、状态码/DTO、SSE 帧序、错误翻译 |
| `integration` | ❌ | 真 Mongo/MinIO/Milvus | 启动自检幂等 + 真实连接（手动） |
| `live` | ❌ | 真模型 + key + 本机 infra | 一次真实查询的 final/usage/close（人工） |

真栈用例已建，均不进 CI：

- `tests/integration/test_startup_real.py`：连续两次启动自检 + lifespan + `/api/health`。
- `tests/live/test_query_smoke.py`：真模型跑一次不联网查询，只断言链路与 usage 形状。

## 目录与接缝

```text
tests/
├── conftest.py        # 环境隔离 + anyio + clear_all
├── support/           # fakes / seams / sse / api helper（不放 test_*.py）
├── unit/              # 纯逻辑与编排
├── contract/          # API / SSE 契约
├── integration/       # 真 infra 启动冒烟（-m integration）
├── live/              # 真模型查询冒烟（RUN_LIVE_TESTS=1 -m live）
└── fixtures/          # 节点 __main__ 与 pytest 共用样例（勿移动）
```

- 所有外部依赖单例经访问器获取：`common.model.get_llm()`、`common.client.get_milvus_client()`、`common.store.get_document_repo()`。模块 import 不建连、不校验 key。
- 测试只替换访问器，不替换消费模块：

```python
from tests.support.seams import patch_accessors

patch_accessors(monkeypatch, llm=FakeLLM(), milvus=FakeMilvus())
```

- API 管理面用 `app.dependency_overrides[get_xxx_manager] = lambda: fake`；`TestClient(app)` 不要用 `with`，否则会触发 lifespan/启动自检。
- 事件总线/任务表是进程内全局状态：根 `conftest.py` 在每个用例前后 `clear_all()`；用例自身仍用唯一 ID。

## 写用例的规矩

1. 命名 `test_<域>__<场景>__<期望>`；docstring 用 Given/When/Then 三行写清行为。
2. 断言消息写清「期望 vs 实际」，禁止裸 `assert x`。
3. 只测契约与不变式：API/SSE 形状、状态机、删除顺序、计量口径、图路由。**不测**日志文案、私有步骤调用次数、prompt 全文快照、真实模型输出。
4. 新增行为先写测试跑红再实现；每个线上 bug 补一条回归用例。
5. 不改测试来适配实现；接口/事件契约变更需同步 `web/e2e/mock-server` 与本文档。
6. 禁止在默认套件里 `sleep`、随机、连真实服务；需要外部依赖时用 `patch_accessors` / `dependency_overrides`。

## API key

- 默认套件：**不需要真实 key**；根 conftest 注入 dummy 只是防止误用本机 `.env`。
- `unit/contract` 的模型守卫会在误调真实模型时直接 `AssertionError`。
- `live` 才读真实 key：`DASHSCOPE_API_KEY`；PDF 导入冒烟另需 `MINERU_API_KEY`（手动执行，不是 live 用例）。live 不进 CI、不写进 pre-commit。
- `integration` / `live` 也需要本机 Mongo/MinIO/Milvus；测试资源名由根 `conftest.py` 固定为 `minirag_test` 库、`minirag_test_*` 集合、`minirag-test` bucket（S3/MinIO bucket 名不允许下划线）。

## CI 与 pre-commit

- CI：`.github/workflows/backend-tests.yml`，零 secrets，跑 ruff + layout + layers + `pytest -q`。
- 本地 pre-commit 跑同一套（pytest 约 4~6s）；若未来超过 15s，降级为 `-m unit` 或移出。

## 排障

- 空 key / 无 infra 下 `import api.main` 失败：先看 `tests/unit/test_import_hygiene.py`，通常是新单例又在模块底部实例化。
- 用例间串扰：检查是否漏了唯一 ID 或 `clear_all()`。
- `live` 报「默认测试禁止访问真实模型访问器」：模型守卫必须用 unit/contract 的 autouse fixture 安装（随 monkeypatch 还原），不能在 conftest import 时全局替换，否则会污染 live。
- 假件形状漂移：对照真实响应改 `tests/support/fakes.py`；每个模型保留 1 个 live 冒烟校准。
