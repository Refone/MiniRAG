# Web 应用部署

推荐使用仓库顶层的 `minirag.py`（Linux / macOS / Windows 通用；脚本本身只依赖
Python 标准库，容器编排依赖 Docker Compose v2）：

```shell
python minirag.py env_check      # 检查系统 / Python / .env / Docker / 网络 / 端口 / 镜像
python minirag.py env_prepare    # 生成 .env、uv sync、npm ci、拉取 Docker 镜像
python minirag.py deploy         # 构建前后端镜像并按 infra → backend → frontend 拉起
python minirag.py reset          # 清空持久化存储并重置数据库
```

`deploy` 会依次执行：

1. `docker compose -f docker/compose.backend.yaml build` 构建后端镜像；
2. `docker compose -f docker/compose.frontend.yaml build` 构建前端镜像；
3. `docker compose -f docker/compose.infra.yaml up -d --wait` 拉起 Milvus / MinIO / etcd / MongoDB / Attu；
4. `docker compose -f docker/compose.backend.yaml up -d --wait` 拉起后端并等待 `/api/health`；
5. `docker compose -f docker/compose.frontend.yaml up -d --wait` 拉起 nginx 前端；
6. 从宿主机验证 `:8000/api/health`、`:8080/` 与 `:8080/api/health`。

`reset` 会停止三个 compose 文件对应的容器，删除 `docker/volumes` 下的 etcd / Milvus / MinIO 数据、
`mini-rag_mongodb_data` / `mini-rag_mongodb_config` 命名卷，以及 `var/uploads`、
`var/import`、`var/tmp`；默认随后重启 infra 与已构建的前后端，由
`src/api/startup_checks.py` 重建 Milvus 集合与 MinIO bucket。常用参数：

```shell
python minirag.py deploy --dry-run       # 只打印计划
python minirag.py deploy --no-build      # 用已有镜像启动
python minirag.py reset --dry-run        # 预览删除范围
python minirag.py reset --keep-runtime   # 保留 var/ 上传与中间产物
python minirag.py reset --keep-down      # 清空后不重启
```

若不想删除数据卷、只想在现有基础设施上 drop 并重建 Milvus 集合 / MinIO bucket，
可运行 `.venv/bin/python tools/reset_db.py`（需 infra 已启动）。

## 国内网络与镜像源

`env_check` 会并行探测 PyPI / npm / Docker Hub / Quay / GHCR 的直连与镜像耗时
（`--skip-network` 跳过）。`env_prepare` / `deploy` 默认 `--mirror auto`，
直连明显更慢时自动使用阿里云 PyPI + npmmirror：

```shell
python minirag.py env_check
python minirag.py deploy --mirror cn
python minirag.py env_prepare --mirror cn
python minirag.py deploy --pypi-index https://mirrors.aliyun.com/pypi/simple
python minirag.py deploy --npm-registry https://registry.npmmirror.com
# 腾讯云主机可优先用内网镜像
python minirag.py deploy --mirror cn \
  --pypi-index https://mirrors.cloud.tencent.com/pypi/simple
```

后端 Dockerfile 会先用镜像重新 `uv lock`（保持版本，只重写 `uv.lock` 里的 source/URL），
再 `uv sync --frozen`；宿主机 `env_prepare` 同样临时改写并在结束后恢复 `uv.lock`。
对已知国内镜像会按阿里云 → 清华 → 腾讯云 → 华为云 → 官方源回退，避免单点 403 / 缺包。

Docker 基础镜像由 daemon 拉取，国内可配置 `registry-mirrors`（仅 Docker Hub）：

```json
{
  "registry-mirrors": ["https://docker.m.daocloud.io"]
}
```

Linux 修改 `/etc/docker/daemon.json` 后重启 docker；Docker Desktop 在设置 → Docker Engine 修改。
`quay.io` 的 etcd / MinIO 镜像不受此配置影响，直连不通时需代理或离线导入。
基础镜像也可用 `PYTHON_IMAGE` / `UV_IMAGE` / `NODE_IMAGE` / `NGINX_IMAGE` 环境变量
覆盖为镜像站地址（示例见 README「国内网络与镜像源」）。

## 手动部署

```shell
# 本地开发
uvicorn --app-dir src api.main:app --reload        # 后端 :8000
cd web && npm run dev                              # 前端 :5173 (代理 /api → :8000)

# 一键容器化 (按顺序拉起)
# 后端配置 (密钥/模型等) 由仓库根目录 .env 经 env_file 注入容器,
# 基础设施地址 (milvus / minio / mongodb) 在 yaml 内已覆盖为 Docker 服务名。
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
