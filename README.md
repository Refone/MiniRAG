# MiniRAG

## 基本架构

```shell
docker  # 容器编排与镜像定义
├── compose.infra.yaml      # 基础设施: Milvus (etcd + MinIO) / Attu / MongoDB
├── compose.backend.yaml    # 后端 (FastAPI) :8000
├── compose.frontend.yaml   # 前端 (nginx) :8080
├── backend.Dockerfile
├── frontend.Dockerfile
└── volumes/                # 容器 bind mount 数据 (gitignore)
docs    # 项目文档与笔记 (docs/feat/ 按需求组织)
src     # 后端源码 (以 src/ 为 sys.path 根); 分层规则见 AGENTS.md
├── api       # HTTP 层 (入口 / 路由 / DTO / 启动自检 / SSE 传输)
├── service   # 业务编排层 (把图包装成服务)
├── graphs    # 核心 LangGraph 处理逻辑
│   ├── import_graph    # 导入流程: 文档导入-切分-向量化-落库
│   └── query_graph     # 查询流程: query-向量化-三路召回-生成答案
└── common    # 唯一共享层 (原顶层 utils/ 已并入)
    ├── utils/    # T0 纯工具: brief / net / tokenizer / markdown_*
    ├── config/   # T1 配置: app_config / env_config / path_config
    ├── logging.py# T2 日志基础设施
    ├── model/    # T2 LLM / Embedding / Reranker / VLM 封装
    ├── client/   # T3 Milvus / MinIO / MongoDB 客户端
    ├── events/   # T3 进程内任务状态 + SSE 通道 + 节点追踪装饰器
    ├── prompt/   # T0 提示词模板
    └── store/    # T4 持久化 (会话历史 / 文档写路径)
tests   # 单测 + 样例输入
├── test_*.py   # pytest 用例 (纯函数与状态机)
└── fixtures/   # 各节点 __main__ 与 pytest 共用的样例文件
tools   # 非生产代码: 维护脚本 + 独立工具
├── make_env_example.py     # .env -> .env.example (脱敏)
├── reset_db.py             # 清空并重建 Milvus / MinIO / MongoDB
├── clean_web_cache.py      # 清理浏览器端废弃的 localStorage key
├── check_layout.py         # 校验本文件「目录约定」与磁盘一致
├── check_layers.py         # 校验分层依赖与 common 内部 tier
└── markdown_chunks_viewer.html  # chunks.json 单文件查看器 (双击打开)
var     # 运行时产物 (gitignore, 可随时删)
├── uploads/  import/       # 上传落盘 / 导入中间产物
├── logs/                   # loguru 文件日志 (LOG_FILE_ENABLE=true 时)
└── tmp/                    # 节点状态快照 / chunks.json / 临时脚本
web     # 前端 (Vite + React)
├── src/
└── .env.example            # 前端环境变量模板 (VITE_API_BASE 等)
```

## 目录约定

| 路径 | 入库 | 定位 |
| --- | --- | --- |
| `src/` | ✅ | 后端源码, 以 `src/` 为 `sys.path` 根 |
| `web/` | ✅ | 前端工程 (Vite + React) |
| `docker/` | ✅ | 编排与镜像定义 |
| `docker/volumes/` | ❌ | 容器 bind mount 数据 |
| `docs/` | ✅ | 文档与需求笔记 |
| `tests/` | ✅ | pytest 用例 + 样例输入 |
| `tools/` | ✅ | 非生产代码: 维护脚本与独立工具 |
| `var/` | ❌ | 运行时产物, 可随时删 |

> 新增 / 重命名顶层目录时**必须同时改上面结构树与本表**；
> `python tools/check_layout.py` 会校验本表与磁盘是否一致。

## 前端交互 demo（skill）

需求开发时（SOP 见 AGENTS.md「需求开发 SOP」），用项目内置 skill `interactive-demo`
把 `docs/feat/<需求名>/PRD.md` 生成单文件交互原型 `docs/feat/<需求名>/demo.html`。

- 位置：`.agents/skills/interactive-demo/`（`SKILL.md` + `assets/demo-template.html` + `references/`）。
- 触发：向 AI 说「按 `docs/feat/xxx/PRD.md` 生成交互 demo」即可；DSH 等支持 `.agents/skills` 的工具会自动发现该 skill。
- 产物：`docs/feat/<需求名>/demo.html`，单文件、离线可双击、明暗双主题、mock 数据，所有状态可从右上「原型演示」控件直达。
- 约定：只改 demo，不提前动 `web/src`；评审通过后才进入后端方案设计与代码实现。

详细规则与自检清单见 `.agents/skills/interactive-demo/SKILL.md`。

## 配置

| 文件 | 入库 | 说明 |
| --- | --- | --- |
| `.env` | ❌ | 后端配置 (密钥 / 模型 / 服务地址), 从 `.env.example` 复制后填值 |
| `.env.example` | ✅ | 由 `python tools/make_env_example.py` 从 `.env` 脱敏生成 |
| `web/.env` | ❌ | 前端变量 |
| `web/.env.example` | ✅ | 前端变量模板 (`VITE_API_BASE` 等) |

## 运行限制

**当前只支持单 worker**：任务进度（`TASK_MANAGER`）与 SSE 通道（`EVENT_BUS`）都是
**进程内**状态，多 worker 下各进程独立，进度推送会落到没有订阅者的进程里。
后端启动时会检测 `WEB_CONCURRENCY` / `UVICORN_WORKERS` 并 WARN。

进程内状态有 TTL 兜底：任务 30 分钟无更新、SSE 通道 30 分钟无读写会被清扫
（`APP_CONFIG.task_ttl_seconds` / `sse_channel_ttl_seconds`）。
横向扩展需把两者换成 Redis 等外部存储，接口（`TASK_MANAGER` / `EVENT_BUS`）已按可替换设计。

## Web 应用部署

```shell
# 本地开发
uvicorn --app-dir src api.main:app --reload        # 后端 :8000
cd web && npm run dev                              # 前端 :5173 (代理 /api → :8000)
cd web && npm run storybook                        # 组件工作台 :6006 (无后端也能看)

# 一键容器化 (按顺序拉起)
# 后端配置 (密钥/模型等) 由仓库根目录 .env 经 env_file 注入容器,
# 基础设施地址 (milvus/minio) 在 yaml 内已覆盖为 Docker 服务名。
# 项目名已用 yaml 顶部的 name: mini-rag 固定, 因此不需要 -p。
docker compose -f docker/compose.infra.yaml up -d                # ① 数据/监控服务 (Milvus/MinIO/Mongo/Attu)
docker compose -f docker/compose.backend.yaml up -d --build      # ② 后端 :8000
docker compose -f docker/compose.frontend.yaml up -d --build     # ③ 前端 :8080 (nginx 反代 /api → backend:8000)
```
