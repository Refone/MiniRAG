# MiniRag

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
src     # 后端源码 (以 src/ 为 sys.path 根)
├── api       # FastAPI 相关源码 (HTTP 入口 / DTO / 启动自检)
├── common    # 公共逻辑
│   ├── client  # Milvus / MinIO / MongoDB 客户端
│   ├── config  # 各种配置类
│   ├── model   # LLM / Embedding / Reranker / VLM 封装
│   ├── prompt  # 提示词模板
│   └── store   # 持久化 (会话历史)
├── graphs    # 核心 LangGraph 处理逻辑
│   ├── import_graph    # 导入流程: 文档导入-切分-向量化-落库
│   └── query_graph     # 查询流程: query-向量化-三路召回-生成答案
├── service   # 业务编排层 (把图包装成服务)
└── utils     # 工具逻辑
tests   # 调试与测试资源 (只有样例输入, 没有用例代码)
└── fixtures/   # 各节点 __main__ 用的样例文件 (将来 pytest 也放这里)
tools   # 非生产代码: 维护脚本 + 独立工具
├── make_env_example.py     # .env -> .env.example (脱敏)
├── reset_db.py             # 清空并重建 Milvus / MinIO / MongoDB
├── clean_web_cache.py      # 清理浏览器端废弃的 localStorage key
├── check_layout.py         # 校验本文件「目录约定」与磁盘一致
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
| `tests/` | ✅ | 样例输入 (无用例代码) |
| `tools/` | ✅ | 非生产代码: 维护脚本与独立工具 |
| `var/` | ❌ | 运行时产物, 可随时删 |

> 新增 / 重命名顶层目录时**必须同时改上面结构树与本表**；
> `python tools/check_layout.py` 会校验本表与磁盘是否一致。

## 配置

| 文件 | 入库 | 说明 |
| --- | --- | --- |
| `.env` | ❌ | 后端配置 (密钥 / 模型 / 服务地址), 从 `.env.example` 复制后填值 |
| `.env.example` | ✅ | 由 `python tools/make_env_example.py` 从 `.env` 脱敏生成 |
| `web/.env` | ❌ | 前端变量 |
| `web/.env.example` | ✅ | 前端变量模板 (`VITE_API_BASE` 等) |

## Web 应用部署

```shell
# 本地开发
uvicorn --app-dir src api.main:app --reload        # 后端 :8000
cd web && npm run dev                              # 前端 :5173 (代理 /api → :8000)

# 一键容器化 (按顺序拉起)
# 后端配置 (密钥/模型等) 由仓库根目录 .env 经 env_file 注入容器,
# 基础设施地址 (milvus/minio) 在 yaml 内已覆盖为 Docker 服务名。
# 项目名已用 yaml 顶部的 name: mini-rag 固定, 因此不需要 -p。
docker compose -f docker/compose.infra.yaml up -d                # ① 数据/监控服务 (Milvus/MinIO/Mongo/Attu)
docker compose -f docker/compose.backend.yaml up -d --build      # ② 后端 :8000
docker compose -f docker/compose.frontend.yaml up -d --build     # ③ 前端 :8080 (nginx 反代 /api → backend:8000)
```
