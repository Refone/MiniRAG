<div align="center">

<img height="120" src="assets/brand/logo.svg" alt="MiniRAG" />

<h1>MiniRAG</h1>

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](backend/api/main.py)
[![React 19](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=white)](frontend/package.json)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](pyproject.toml)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2.12-1C3C3C?style=flat-square&logo=langgraph&logoColor=white)](backend/graphs)
[![Docker Compose](https://img.shields.io/badge/Docker_Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](docs/web-deploy.md)
[![Milvus](https://img.shields.io/badge/Milvus-Vector_Store-00A1EA?style=flat-square&logo=milvus&logoColor=white)](docs/architecture.md)
[![MinIO](https://img.shields.io/badge/MinIO-File_Store-C72E49?style=flat-square&logo=minio&logoColor=white)](docker/compose.infra.yaml)
[![MongoDB](https://img.shields.io/badge/MongoDB-Json_Store-47A248?style=flat-square&logo=mongodb&logoColor=white)](docker/compose.infra.yaml)
[![MinerU](https://img.shields.io/badge/MinerU-PDF_Parser-8C46FF?style=flat-square)](backend/common/client/mineru_client.py)

Minimal Demo for RAG

LLM 能力 + 专业文档参考 = 更好的回答

<img src="assets/showcase/overview-demo.gif" width="1200" alt="MiniRAG 全流程演示"><br/>
<span style="color: #888;">全流程演示</span>

<br/>

[导入流程](#导入流程) | [查询流程](#查询流程) | [项目结构](#项目结构) | [快速开始](#快速开始)

</div>

## 导入流程

<div align="center">
<img src="assets/workflow-graph/import-graph-flow.animated.svg" width="880" alt="文档导入流程"><br/>
<span style="color: #888;">文档导入流程图</span><br/>

| 节点名称                     | 节点功能说明                                                                                                        |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `node_entry`                 | 文档导入入口。<br>识别上传文件类型，路由到后续节点。                                                                |
| `node_pdf_to_md`             | PDF 转 Markdown 节点。<br>调用 MinerU 把 PDF 解析为带图片的 Markdown。                                              |
| `node_process_standalone_md` | 单文件 Markdown 处理节点。<br>下载外链图片保存至本地。                                                              |
| `node_process_md_zip`        | Markdown zip 处理节点。<br>对压缩包内每个 Markdown 文件进行处理，下载外链图片保存至本地。                           |
| `node_md_fork`               | 压缩包分发节点。<br>把 zip 里面的多个 Markdown 变成可并行的子任务。                                                 |
| `node_md_img`                | 图片处理节点。<br>调用 VLM 生成每张图片摘要。<br>图片上传 MinIO、更新 Markdown 文件中的图片链接。                   |
| `node_document_split`        | 文档切分节点。<br>根据标题层级递归切分 Markdown 文档，生成可向量化的文档切片。                                      |
| `node_document_embedding`    | 信息入库节点。<br>三类制品（原始文档、处理后文档、切片文件）分别上传 MinIO。<br>文档摘要、切片、向量化入库 Milvus。 |

</div>

## 查询流程

<div align="center">
<img src="assets/workflow-graph/query-graph-flow.animated.svg" width="880" alt="查询流程"><br/>
<span style="color: #888;">信息查询流程图</span><br/>

| 节点名称                | 节点功能说明                                                                          |
| ----------------------- | ------------------------------------------------------------------------------------- |
| `node_intent_recognize` | 意图识别节点。<br>意图识别 + 查询改写 + 文档级召回                                    |
| `node_search_embedding` | 嵌入检索节点。<br>在确认文档范围内做切片级混合检索。                                  |
| `node_search_hyde`      | HyDE 假设性答案召回。<br>让 LLM 先编一个答案，在根据答案中的线索进行向量检索。        |
| `node_search_web`       | 联网搜索节点。<br>通过网络搜索 MCP 获取相关信息。                                     |
| `node_rrf_and_rerank`   | RRF 融合与重排序节点。<br>对多源检索结果进行 RRF 融合，并调用 Reranker 模型进行精排。 |
| `node_answer_output`    | 答案输出节点。<br>整合多源检索结果，让 LLM 进行总结归纳。生成最终答案并返回给前端。   |

</div>

## 项目结构

<div align="center">
<img src="assets/architecture/minirag-architecture-v3.svg" width="880" alt="项目结构">
</div>

```text
MiniRAG
├── backend/                   Python 源码根（sys.path 根）
│   ├── api/                   HTTP 层：路由 / DTO / SSE 传输 / 启动自检
│   ├── service/               业务编排：docs / import / query
│   ├── graphs/                LangGraph 图
│   │   ├── import_graph/      导入图：解析 → 图片 → 切分 → 入库
│   │   └── query_graph/       查询图：改写 → 多路召回 → 融合精排 → 生成
│   └── common/                唯一共享层
│       ├── config/            运行参数 / 环境变量 / 路径
│       ├── model/             LLM / VLM / Embedding / Reranker 访问器
│       ├── client/            Milvus / MinIO / MongoDB / MinerU / WebSearch
│       ├── events/            SSE 事件总线 / 任务表 / Token 计量
│       ├── store/             会话历史 / 文档仓储 / 用量存储
│       ├── prompt/            Prompt 模板
│       ├── schema/            全局数据结构
│       └── utils/             切分 / 图片 / Token 等工具
├── frontend/                  React 19 + Vite 6
│   └── src/                   pages / components / store / lib / hooks / types / styles
├── docker/                    compose.infra / backend / frontend + 两个 Dockerfile
├── tests/                     unit / contract / integration / live + support / fixtures
├── evals/                     RAGAS 评估脚本与报告
├── tools/                     check_layout / check_layers / reset_db 等维护脚本
├── docs/                      architecture / setup / web-deploy / manual / notes / feat
├── assets/                    架构图 / 流程图 / 演示 GIF
├── var/                       运行时产物（gitignore）
├── minirag.py                 一键 env_check / env_prepare / deploy / reset
├── pyproject.toml             依赖与 pytest 配置
└── uv.lock                    依赖锁定

主调用方向：api → service → graphs → common → 外部服务

```

## 快速开始

### 1. 前置软件准备

- Docker:
  - Docker Desktop 4.27+
  - 或 Docker Engine 24+ 加 Docker Compose v2.24+
- Python 3.12+
- uv（仅本地开发需要；`env_prepare` 也会检测并提示安装）
- Node.js 20+（推荐 22 LTS；本地前端开发 / E2E 需要）

### 2. 配置 `.env`

```shell
cp .env.example .env  # Windows PowerShell: Copy-Item .env.example .env
```

其中需要配置的项目：

- `DASHSCOPE_API_KEY`：[千问 AI 平台](https://platform.qianwenai.com/home) API Key，所有大模型调用统一走千问平台。
- `MINERU_API_KEY`：[MinerU](https://mineru.net/) API Key，用于 PDF 解析。

### 3. 生产环境部署

本项目提供一键部署脚本 `minirag.py`，脚本只依赖 Python 标准库，可直接运行。

```shell
# 检查系统 / .env / Docker / 网络 / 端口 / 磁盘
uv run minirag.py env_check

# 安装依赖并拉取镜像
uv run minirag.py env_prepare

# 构建并依次拉起 infra → backend → frontend
uv run minirag.py deploy
```

国内网络可加 `--mirror cn`（`env_prepare` / `deploy` 均支持）。

部署完成后访问 <http://localhost:8080>，API 文档在 <http://localhost:8000/docs>。

### 4. 本地开发部署

```shell
# 拉起 infra, 启动数据库服务
docker compose -f docker/compose.infra.yaml up -d --wait

# 同步 Python 环境
uv sync

# 启动后端服务
uv run uvicorn --app-dir backend api.main:app --reload

# 启动前端服务
cd frontend && npm ci && npm run dev

# 启动前端组件工作台  http://localhost:6006
cd frontend && npm run storybook
```

### 5. 默认端口映射

<details>
<summary>Docker 服务端口</summary>

| 端口      | 服务 / 容器         | 协议             | 浏览器打开后     | 用途                                                                        |
| --------- | ------------------- | ---------------- | ---------------- | --------------------------------------------------------------------------- |
| **8080**  | `mini-rag-frontend` | HTTP             | MiniRAG 页面     | **唯一入口**：nginx 托管 React SPA，并把 `/api` 反代到 `backend:8000`       |
| **8000**  | `mini-rag-backend`  | HTTP             | FastAPI Swagger  | `/api/health` 健康检查、`/docs` 接口文档、`/openapi.json`；SSE 接口也在这里 |
| **19530** | `milvus`            | **gRPC**         | 打不开，连接报错 | Python SDK（`pymilvus`）连 Milvus 的端口，不是 HTTP                         |
| **9001**  | `milvus-minio`      | HTTP             | MinIO 登录页     | MinIO 控制台，账号 `minioadmin / minioadmin`（Compose 里固定）              |
| **7001**  | `attu`（容器 7000） | HTTP             | Attu 界面        | Milvus 可视化管理：集合、schema、向量数据浏览                               |
| **27017** | `mongodb`           | **MongoDB 协议** | -                | 会话历史、Token 计量；用 `mongosh mongodb://localhost:27017` 或 Compass 连  |

</details>

<details>
<summary>开发 / 测试端口</summary>

| 端口     | 谁在用               | 启动方式                  | 用途                                       |
| -------- | -------------------- | ------------------------- | ------------------------------------------ |
| **5173** | Vite dev server      | `npm run dev`             | 前端热更新；`/api` 代理到 `localhost:8000` |
| **6006** | Storybook            | `npm run storybook`       | 组件工作台                                 |
| **4000** | Playwright mock API  | `npm run test:e2e`        | E2E 的假后端                               |
| **5174** | Playwright 专用前端  | `npm run test:e2e`        | 避开日常 5173，直连 mock                   |
| **9323** | Playwright HTML 报告 | `npm run test:e2e:report` | 测试报告服务（默认端口）                   |

</details>

## 文档

| 想了解                       | 看这里                                                                    |
| ---------------------------- | ------------------------------------------------------------------------- |
| 分层、主链路、存储与外部依赖 | [docs/architecture.md](docs/architecture.md)                              |
| 环境检查、一键部署、镜像源   | [docs/setup.md](docs/setup.md) · [docs/web-deploy.md](docs/web-deploy.md) |
| 后端测试分层与写法           | [docs/manual/backend-testing.md](docs/manual/backend-testing.md)          |
| 端到端测试（Playwright）     | [docs/manual/e2e-testing.md](docs/manual/e2e-testing.md)                  |
| 自动部署与回滚               | [docs/notes/ci-cd.md](docs/notes/ci-cd.md)                                |
| 需求过程与历史决策           | [docs/feat/README.md](docs/feat/README.md)                                |

## 已知限制

**只支持单 worker**：任务进度（`TASK_MANAGER`）与 SSE 通道（`EVENT_BUS`）都是进程内状态，
多 worker 下各进程独立，进度会推到没有订阅者的进程。后端启动时会检测
`WEB_CONCURRENCY` / `UVICORN_WORKERS` 并 WARN。

进程内状态有 30 分钟 TTL 兜底（任务无更新 / 通道无读写即清扫）。横向扩展需要把两者
换成 Redis 等外部存储，接口已按可替换设计。

## 参与开发

- 仓库约定（代码验证、Git、需求 SOP）见 [AGENTS.md](AGENTS.md)。
- 需求按 `PRD → 交互 demo → 后端改动方案 → 动工 → 测试反馈` 推进，
  对应 skill 位于 `.agents/skills/`。
- 提交前必须通过 pre-commit：`ruff`、`check_layout`、`check_layers`、`pytest`。
