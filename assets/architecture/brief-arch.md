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
