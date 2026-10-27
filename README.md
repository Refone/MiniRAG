# MiniRag

## 基本架构

```shell
docker  # docker 启动文件
docs    # 项目文档与笔记
scripts # 一次性维护脚本 (生成 .env.sample / 重置数据库)
src     # 主要源码
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
test    # 测试资源 (fixture/ 下为各节点 __main__ 调试用的样例文件)
tools   # 独立工具 (markdown-splitter)
web     # 前端 (Vite + React)
```

## Web 应用部署

```shell
# 本地开发
uvicorn --app-dir src api.main:app --reload        # 后端 :8000
cd web && npm run dev                              # 前端 :5173 (代理 /api → :8000)

# 一键容器化 (按顺序拉起)
# 后端配置 (密钥/模型等) 由仓库根目录 .env 经 env_file 注入容器,
# 基础设施地址 (milvus/minio) 在 yaml 内已覆盖为 Docker 服务名。
docker compose -p mini-rag -f docker/data-services.yaml up -d      # ① 数据/监控服务 (Milvus/MinIO/Mongo/Attu)
docker compose -p mini-rag -f docker/web-backend.yaml up -d --build  # ② 后端 :8000
docker compose -p mini-rag -f docker/web-frontend.yaml up -d --build # ③ 前端 :8080 (nginx 反代 /api → backend:8000)
```