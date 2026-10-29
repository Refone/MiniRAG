# 环境部署

## Milvus Docker

在 Milvus Github 中可以找到默认配置的 docker-compose.yaml

- https://github.com/milvus-io/milvus
- https://github.com/milvus-io/milvus/blob/master/deployments/docker/standalone/docker-compose.yml

```
wget https://github.com/milvus-io/milvus/raw/refs/heads/master/deployments/docker/standalone/docker-compose.yml
```

稍加调整, 加上 attu、mongodb 服务, 调配成本项目的 [compose.infra.yaml](../docker/compose.infra.yaml)
(项目名已在 yaml 内固定为 `mini-rag`, 启动用 `docker compose -f docker/compose.infra.yaml up -d`)

用以启动相关服务

## 后端启动自检

后端 (FastAPI) 启动时会执行 `src/api/startup_checks.py` 的自检流程:

**硬依赖** (任一项失败则拒绝启动, 并汇总报告全部失败项与排查提示):

| 检查项 | 内容 |
| --- | --- |
| Milvus | TCP 连通性 + `minirag_docs` / `minirag_chunks` 集合初始化 |
| MinIO | TCP 连通性 + `minirag` bucket 初始化 (含匿名只读策略) |
| MongoDB | TCP 连通性 + `ping` |
| 运行时目录 | `var/uploads` / `var/import` / `var/logs` 存在且可写 |

**软依赖** (缺失仅告警, 不阻止启动): `MINERU_API_KEY`（PDF 解析）、`DASHSCOPE_API_KEY`
（LLM / VLM / Embedding / Rerank / Web Search 共用）是否已在 `.env` 中配置。

说明: 各 client 的构造函数不再做任何网络请求, 连通性统一由自检流程负责
(先 TCP 探测快速失败, 再发真实协议请求), 服务未启动时会得到明确的错误提示,
而不是 import 阶段的晦涩堆栈。

如需手动触发自检:

```bash
.venv/bin/python -c "from api.startup_checks import startup_checks; startup_checks()"
```
