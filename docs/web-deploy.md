# Web 应用部署

```shell
# 本地开发
uvicorn --app-dir src api.main:app --reload        # 后端 :8000
cd web && npm run dev                              # 前端 :5173 (代理 /api → :8000)

# 一键容器化 (按顺序拉起)
# 后端配置 (密钥/模型等) 由仓库根目录 .env 经 env_file 注入容器,
# 基础设施地址 (milvus/minio) 在 yaml 内已覆盖为 Docker 服务名。
docker compose -f docker/data-services.yaml up -d      # ① 数据/监控服务 (Milvus/MinIO/Mongo/Attu)
docker compose -f docker/web-backend.yaml up -d --build  # ② 后端 :8000
docker compose -f docker/web-frontend.yaml up -d --build # ③ 前端 :8080 (nginx 反代 /api → backend:8000)
```
