# Web 应用部署

```shell
# 本地开发
uvicorn --app-dir src api.main:app --reload        # 后端 :8000
cd web && npm run dev                              # 前端 :5173 (代理 /api → :8000)

# 一键容器化 (按顺序拉起)
# 后端配置 (密钥/模型等) 由仓库根目录 .env 经 env_file 注入容器,
# 基础设施地址 (milvus/minio) 在 yaml 内已覆盖为 Docker 服务名。
# 项目名由 yaml 顶部的 `name: mini-rag` 固定, 不写 -p 也落在同一项目里。
docker compose -f docker/compose.infra.yaml up -d            # ① 数据/监控服务 (Milvus/MinIO/Mongo/Attu)
docker compose -f docker/compose.backend.yaml up -d --build  # ② 后端 :8000
docker compose -f docker/compose.frontend.yaml up -d --build # ③ 前端 :8080 (nginx 反代 /api → backend:8000)
```

若想停止服务

```shell
docker compose \
  -f docker/compose.infra.yaml \
  -f docker/compose.backend.yaml \
  -f docker/compose.frontend.yaml \
  down

# milvus 网络不会被 down 删除。
# 因为 compose.backend.yaml / compose.frontend.yaml 里把这个网络标成了 external: true
# compose 不会去删它。如果你想连网络也一起清掉，down 之后再补一句：
docker network rm milvus

# 数据卷 (mongodb) 不会被 down 删除, 卷名已在 compose.infra.yaml 里显式钉死;
# 连数据一起清掉: docker volume rm mini-rag_mongodb_data mini-rag_mongodb_config
```
