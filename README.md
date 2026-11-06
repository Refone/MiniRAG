# MiniRAG

## 基本架构

```shell
minirag.py  # 一键部署脚本: env_check / env_prepare / deploy / reset
docker  # 容器编排与镜像定义
├── compose.infra.yaml      # 基础设施: Milvus (etcd + MinIO) / Attu / MongoDB
├── compose.backend.yaml    # 后端 (FastAPI) :8000
├── compose.frontend.yaml   # 前端 (nginx) :8080
├── backend.Dockerfile
├── frontend.Dockerfile
└── volumes/                # 容器 bind mount 数据 (gitignore)
docs    # 项目文档与笔记 (docs/feat/ 按需求组织; 历史需求索引见 docs/feat/README.md)
assets  # 文档配图与可视化产物: 架构图 / 流程动图 / 演示 GIF
├── architecture/         # 系统架构图 (SVG + 可交互 HTML + JSON)
├── workflow-graph/       # 导入 / 查询流程图与动图 (含生成脚本)
└── showcase/             # README 演示 GIF 与封面
backend # 后端源码 (以 backend/ 为 sys.path 根); 分层规则见 AGENTS.md
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
tests   # pytest 分层 + 样例输入
├── unit/         # 纯逻辑/节点编排 (默认)
├── contract/     # API/SSE 契约 (默认)
├── integration/  # 真 infra 启动冒烟 (手动)
├── live/         # 真模型查询冒烟 (手动)
├── support/      # fakes / seams / helper
└── fixtures/     # 各节点 __main__ 与 pytest 共用的样例文件
tools   # 非生产代码: 维护脚本 + 独立工具
├── make_env_example.py     # .env -> .env.example (脱敏)
├── reset_db.py             # 清空并重建 Milvus / MinIO / MongoDB
├── clean_web_cache.py      # 清理浏览器端废弃的 localStorage key
├── check_layout.py         # 校验本文件「目录约定」与磁盘一致
├── check_layers.py         # 校验分层依赖与 common 内部 tier
└── markdown_chunks_viewer.html  # chunks.json 单文件查看器 (双击打开)
evals   # RAG 评估: 问题集生成、Ragas 打分与报告
├── eval_questions.csv      # 问题 / 标准答案
├── ragas_eval.py           # 生成题目 -> 跑 RAG -> Ragas 评估
├── eval_result.csv         # 逐题上下文、答案与指标
└── report.md               # Markdown 评估报告
var     # 运行时产物 (gitignore, 可随时删)
├── uploads/  import/       # 上传落盘 / 导入中间产物
├── logs/                   # loguru 文件日志 (LOG_FILE_ENABLE=true 时)
└── tmp/                    # 节点状态快照 / chunks.json / 临时脚本
frontend # 前端 (Vite + React)
├── src/
└── .env.example            # 前端环境变量模板 (VITE_API_BASE 等)
```

## 目录约定

| 路径              | 入库 | 定位                                     |
| ----------------- | ---- | ---------------------------------------- |
| `backend/`        | ✅   | 后端源码, 以 `backend/` 为 `sys.path` 根 |
| `frontend/`       | ✅   | 前端工程 (Vite + React)                  |
| `docker/`         | ✅   | 编排与镜像定义                       |
| `docker/volumes/` | ❌   | 容器 bind mount 数据                 |
| `docs/`           | ✅   | 文档与需求笔记                       |
| `assets/`         | ✅   | 文档配图: 架构图 / 流程动图 / 演示 GIF |
| `tests/`          | ✅   | pytest 用例 + 样例输入               |
| `tools/`          | ✅   | 非生产代码: 维护脚本与独立工具       |
| `evals/`          | ✅   | RAG 评估问题集、脚本与报告           |
| `var/`            | ❌   | 运行时产物, 可随时删                 |

> 新增 / 重命名顶层目录时**必须同时改上面结构树与本表**；
> `python tools/check_layout.py` 会校验本表与磁盘是否一致。
>
> `docs/feat/` 是历史需求快照；目录改名后的路径映射与文档状态见
> [docs/feat/README.md](docs/feat/README.md)。
>
> 后端测试的分层、命令与接缝约定见 [docs/manual/backend-testing.md](docs/manual/backend-testing.md)。

## 前端交互 demo（skill）

需求开发时（SOP 见 AGENTS.md「需求开发 SOP」），用项目内置 skill `interactive-demo`
把 `docs/feat/<需求名>/PRD.md` 生成单文件交互原型 `docs/feat/<需求名>/demo.html`。

- 位置：`.agents/skills/interactive-demo/`（`SKILL.md` + `assets/demo-template.html` + `references/`）。
- 触发：向 AI 说「按 `docs/feat/xxx/PRD.md` 生成交互 demo」即可；DSH 等支持 `.agents/skills` 的工具会自动发现该 skill。
- 产物：`docs/feat/<需求名>/demo.html`，单文件、离线可双击、明暗双主题、mock 数据，所有状态可从右上「原型演示」控件直达。
- 约定：只改 demo，不提前动 `frontend/src`；评审通过后才进入后端改动方案与代码实现。

详细规则与自检清单见 `.agents/skills/interactive-demo/SKILL.md`。

## 后端改动方案（skill）

同一 SOP 的下一环：用项目内置 skill `backend-plan` 把 PRD（＋已定稿的 `demo.html`）
调研成人类可审批的后端改动方案 `docs/feat/<需求名>/后端改动方案.md`。

- 位置：`.agents/skills/backend-plan/`（`SKILL.md` + `references/`：`plan-template.md` 文档骨架、`repo-map.md` 后端地图、`decision-patterns.md` 决策与评审协议）。
- 触发：向 AI 说「按 `docs/feat/xxx/PRD.md` 生成后端改动方案」即可。
- 产物：章节对齐 AGENTS.md「后端改动方案.md」（架构调整 / 文件修改清单 / 内部重要变更 / 对外重要变更 / 验收条件），另含需求映射、决策记录、风险与未决。
- 修订：人类写了 `后端评审vX.md` 时，先产出 `后端评审反馈-vX.md` 逐条答复，再合并进方案正文。
- 约定：只写文档、只读取证，不动 `backend/`；方案评审通过后才动工改代码。

用法：

1. **首版**：说「按 `docs/feat/xxx/PRD.md` 生成后端改动方案」。AI 读 PRD＋demo、调研代码后产出 `后端改动方案.md`（v0），并在回复里附待拍板清单（方案中的 `⏳` 项）。
2. **按评审修订**：把意见写进 `docs/feat/xxx/后端评审vX.md`，说「按后端评审 vX 修订方案」——先产出 `后端评审反馈-vX.md` 逐条答复，再合并进方案正文、升版本。
3. **按 PRD 修订**：PRD 末尾「评审纪要」追加要求后，说「更新后端改动方案」做增量修订。
4. **人类核对**：`grep -n '⏳' docs/feat/<需求名>/后端改动方案.md` 查看未决项；文档阶段 AI 不改 `backend/`，`git status` 应只有文档变化。
5. **上下文开销**：AI 按需读取参考（首版约 6–8k token 指引，全读约 10–13k），不整包加载；路由表见 `.agents/skills/backend-plan/SKILL.md`「按需读参考」。

详细规则与自检清单见 `.agents/skills/backend-plan/SKILL.md`。

## 需求动工（skill）

同一 SOP 的「动工」环节：三件套（PRD ＋ 定稿的 `demo.html` ＋ 评审通过的后端改动方案）齐备后，
用项目内置 skill `implement` 把方案落地成 `backend/` 与 `frontend/` 的核心代码变更，产出待人类提交的核心 commit。
测试反馈修复是 SOP 的下一环节，不在此 skill 范围内。

- 位置：`.agents/skills/implement/SKILL.md`（单文件，无 references）。
- 触发：说「按方案动工」「开始实现 `docs/feat/xxx`」即可。
- 口径：前端改动与 `demo.html` 逐点对齐（布局 / 状态 / 文案 / 动效），后端按方案的修改清单与对外契约施工。
- 产物：`backend/` 与 `frontend/src/` 的核心代码变更（即核心 commit 的工作区内容）；**变更记录就是 git commit（人类提交），不另写实施文档**。
- 约定：只写代码，不改 PRD / demo / 方案正文；git 只读，提交由人类完成。

用法：

1. **动工**：说「按 `docs/feat/xxx` 动工」。AI 先核对门槛（方案无 `⏳`、demo 已定稿、基线全绿），再按方案清单改代码。
2. **自测**：后端 ruff ＋ layout ＋ layers ＋ pytest，前端 `npm run build` ＋ 浏览器对照 demo 走查；结果写进交付回复。
3. **人类验收**：`git status` 核对改动面（应与方案清单一致）；认可后由人类 add / commit，commit 即变更记录。

详细规则与自检清单见 `.agents/skills/implement/SKILL.md`。

## 配置

| 文件                    | 入库 | 说明                                                            |
| ----------------------- | ---- | --------------------------------------------------------------- |
| `.env`                  | ❌   | 后端配置 (密钥 / 模型 / 服务地址), 从 `.env.example` 复制后填值 |
| `.env.example`          | ✅   | 由 `python tools/make_env_example.py` 从 `.env` 脱敏生成        |
| `frontend/.env`         | ❌   | 前端变量                                                        |
| `frontend/.env.example` | ✅   | 前端变量模板 (`VITE_API_BASE` 等)                               |

## 运行限制

**当前只支持单 worker**：任务进度（`TASK_MANAGER`）与 SSE 通道（`EVENT_BUS`）都是
**进程内**状态，多 worker 下各进程独立，进度推送会落到没有订阅者的进程里。
后端启动时会检测 `WEB_CONCURRENCY` / `UVICORN_WORKERS` 并 WARN。

进程内状态有 TTL 兜底：任务 30 分钟无更新、SSE 通道 30 分钟无读写会被清扫
（`APP_CONFIG.task_ttl_seconds` / `sse_channel_ttl_seconds`）。
横向扩展需把两者换成 Redis 等外部存储，接口（`TASK_MANAGER` / `EVENT_BUS`）已按可替换设计。

## 一键部署（minirag.py）

仓库顶层的 `minirag.py` 封装了完整的容器化部署流程，支持 **Linux / macOS / Windows**
（WSL 会标记为 `[WSL]`），脚本本身只依赖 Python 标准库，容器编排依赖 Docker Compose v2。

```shell
python minirag.py env_check      # ① 环境检查: 系统 / Python / .env / Docker / 网络 / 端口 / 磁盘 / 镜像
python minirag.py env_prepare    # ② 环境安装: 生成 .env、uv sync、npm ci、拉取 Docker 镜像
python minirag.py deploy         # ③ 一键部署: 构建前后端镜像 → infra → backend → frontend
python minirag.py reset          # ④ 清空持久化存储并重置数据库
```

| 命令          | 行为                                                                                                                                                                             |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `env_check`   | 只读检查；含 PyPI / npm / Docker 镜像源连通性。有失败项时退出码为 1，`--strict` 把警告也视为失败                                                                                 |
| `env_prepare` | 缺少 `.env` 时从 `.env.example` 复制；按 `--mirror` 选择 PyPI/npm 源；安装 Python / 前端依赖；拉取全部基础设施与构建基础镜像                                                     |
| `deploy`      | 依次构建 backend / frontend，按 infra → backend → frontend 拉起并等待健康检查，最后验证 nginx `/api` 反代                                                                        |
| `reset`       | 停止容器，清空 `docker/volumes`（etcd / Milvus / MinIO）、Mongo 命名卷、`var/uploads`、`var/import`、`var/tmp`，随后重启 infra 与已构建的前后端，由后端启动自检重建集合与 bucket |

常用参数：

```shell
python minirag.py deploy --dry-run       # 只打印执行计划，不修改状态
python minirag.py deploy --no-build      # 用已有镜像启动
python minirag.py deploy --no-cache      # 构建不用缓存
python minirag.py reset --dry-run        # 先看清会删哪些目录 / 数据卷
python minirag.py reset --keep-runtime   # 保留 var/ 下的上传与中间产物
python minirag.py reset --keep-down      # 清空后保持容器停止
python minirag.py depoly                 # deploy 的兼容别名（历史拼写）
```

> `reset` 默认会重启基础设施与已构建的应用容器，并由后端启动自检重建数据库资源；
> 若只想清空、不启动，使用 `--keep-down`。

### 国内网络与镜像源

`env_check` 会并行探测 PyPI / npm / Docker Hub / Quay / GHCR 的直连与国内镜像耗时
（`--skip-network` 可跳过）。`env_prepare` / `deploy` 默认 `--mirror auto`：
直连明显更慢或不可达时自动切换到阿里云 PyPI + npmmirror；也可以强制指定：

```shell
python minirag.py deploy --mirror cn
python minirag.py env_prepare --mirror cn
python minirag.py deploy --pypi-index https://mirrors.aliyun.com/pypi/simple
python minirag.py deploy --npm-registry https://registry.npmmirror.com

# 腾讯云主机可优先用内网镜像（仍保留其他镜像回退）
python minirag.py deploy --mirror cn \
  --pypi-index https://mirrors.cloud.tencent.com/pypi/simple
```

- 后端构建会先把 `uv.lock` 按镜像临时重锁（版本不变，只重写下载地址），再执行
  `uv sync --frozen`；宿主机的 `env_prepare` 也会临时改写并在结束后恢复 `uv.lock`。
- 已知国内镜像会按 **阿里云 → 清华 → 腾讯云 → 华为云 → 官方源** 自动回退，
  避免某个镜像对个别包返回 403 / 缺包（例如 `chunkana`）导致整个构建失败。
- 前端 npm registry 通过 Dockerfile build arg 注入。
- Docker 基础镜像与基础设施镜像仍由 Docker 自己拉取。国内可给 daemon 配
  `registry-mirrors`（**仅对 Docker Hub 生效**）：

```json
{
  "registry-mirrors": ["https://docker.m.daocloud.io"]
}
```

Linux 修改 `/etc/docker/daemon.json` 后执行 `sudo systemctl restart docker`；
Docker Desktop 在「Settings → Docker Engine」中修改。镜像站可用性会变化，请按实际网络调整。

- 基础镜像也可以直接换成镜像站地址（示例，需按镜像站实际路径调整）：

```shell
PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim \
UV_IMAGE=ghcr.nju.edu.cn/astral-sh/uv:latest \
NODE_IMAGE=docker.m.daocloud.io/library/node:22-alpine \
NGINX_IMAGE=docker.m.daocloud.io/library/nginx:alpine \
python minirag.py deploy --mirror cn
```

- `quay.io` 上的 etcd / MinIO 镜像不受 Docker Hub 的 `registry-mirrors` 影响；
  直连不通时需要代理或提前导入离线镜像。

### GitHub Actions 自动部署

`main` 分支更新后可自动 SSH 到服务器执行 `minirag.py deploy`。workflow 位于
[.github/workflows/deploy.yml](.github/workflows/deploy.yml)，需要配置
`DEPLOY_HOST` / `DEPLOY_USER` / `DEPLOY_PATH` / `DEPLOY_SSH_KEY` /
`DEPLOY_KNOWN_HOSTS` 等 secrets。

完整步骤、服务器准备、回滚与 self-hosted runner 方案见
[docs/ci-cd.md](docs/ci-cd.md)。

## Web 应用部署

```shell
# 本地开发
uvicorn --app-dir backend api.main:app --reload    # 后端 :8000
cd frontend && npm run dev                         # 前端 :5173 (代理 /api → :8000)
cd frontend && npm run storybook                   # 组件工作台 :6006 (无后端也能看)

# 一键容器化: 推荐使用顶层脚本
python minirag.py env_check
python minirag.py env_prepare
python minirag.py deploy

# 手动方式 (按顺序拉起)
# 后端配置 (密钥/模型等) 由仓库根目录 .env 经 env_file 注入容器,
# 基础设施地址 (milvus / minio / mongodb) 在 yaml 内已覆盖为 Docker 服务名。
# 项目名已用 yaml 顶部的 name: mini-rag 固定, 因此不需要 -p。
docker compose -f docker/compose.infra.yaml up -d                # ① 数据/监控服务 (Milvus/MinIO/Mongo/Attu)
docker compose -f docker/compose.backend.yaml up -d --build      # ② 后端 :8000
docker compose -f docker/compose.frontend.yaml up -d --build     # ③ 前端 :8080 (nginx 反代 /api → backend:8000)
```
