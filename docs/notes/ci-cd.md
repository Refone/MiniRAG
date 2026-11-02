# GitHub Actions 自动部署

目标：`main` 分支有新提交时，GitHub Actions 通过 SSH 登录部署服务器，
更新代码并执行 `minirag.py deploy`。

> GitHub Actions 默认运行在 GitHub 云端临时 runner 上，不在你的服务器上；
> runner 通过 SSH 操作服务器。若希望直接在服务器上执行，见第 7 节 self-hosted runner。

推荐架构：

```text
本地机器（你的 Mac / Windows / Linux）
      │  git push main
      ▼
GitHub
      │  触发 workflow
      ▼
GitHub-hosted runner（GitHub 临时创建的 VM，不是你的服务器）
      │  ssh ubuntu@<SERVER>（使用部署专用私钥）
      ▼
部署服务器（腾讯云 Ubuntu）
  ~/deploy/MiniRAG
      │  git fetch + checkout -B main origin/main
      │  python3 minirag.py deploy --mirror cn
      ▼
Docker Compose: infra → backend → frontend
```

构建在服务器上完成，不需要把镜像推到镜像仓库，也不需要把 Docker 权限交给
GitHub-hosted runner。

### 先分清三台机器

| 机器                      | 在哪里                       | 在本文档里做什么                                                |
| ------------------------- | ---------------------------- | --------------------------------------------------------------- |
| **本地机器**              | 你正在使用的电脑             | 生成 SSH key、执行 `ssh`、配置 GitHub Secrets、`git push`       |
| **部署服务器**            | 腾讯云 Ubuntu（`<SERVER>`）  | 保存仓库和 `.env`，运行 Docker；接收 GitHub Actions 的 SSH 登录 |
| **GitHub Actions runner** | GitHub 每次部署临时创建的 VM | 运行 workflow，用私钥 SSH 到服务器执行部署命令                  |

`ssh ubuntu@<SERVER>` 是**在本地机器或 GitHub runner 上执行**的命令，
意思是“以 `ubuntu` 用户登录 `<SERVER>` 这台服务器”。
它不是在服务器上执行的命令；如果你已经登录服务器，就不要再执行它。

其中 `ubuntu` 是 SSH 用户名，`<SERVER>` 是服务器 IP 或域名；按你的实际情况替换。

> 注意：真正执行 `git` / `docker` / `minirag.py` 的机器是**服务器**。
> GitHub runner 只是通过 SSH 把命令发过去；`ssh` 是“客户端连到服务器”的通道，
> 不是让部署命令运行在 GitHub 上。

## 1. 服务器准备（先登录服务器）

先在**本地机器**登录服务器：

```shell
# 在本地机器执行：以 ubuntu 用户登录 <SERVER>
ssh ubuntu@<SERVER>
```

登录成功后，提示符会变成类似 `ubuntu@VM-0-11-ubuntu:~$`。下面的命令都在
**服务器上**执行（如果你已经通过其他方式登录服务器，直接执行即可）：

```shell
# 以下命令在服务器上执行
# 1) 确认部署用户在 docker 组（重新登录后生效）
groups | grep -q docker || sudo usermod -aG docker "$USER"

# 2) 代码仓库已 clone 到固定目录，且 remote 指向 GitHub
cd ~/deploy/MiniRAG
git remote -v
git checkout main
git pull --ff-only

# 3) .env 必须存在且不入库（工作流不会修改它）
ls -l .env

# 4) 服务器能非交互拉取 GitHub（凭据已配置，不会弹密码）
GIT_TERMINAL_PROMPT=0 git fetch origin main

# 5) 确认 docker / compose / python3 可用
docker version
docker compose version
python3 --version
```

部署目录将被工作流执行 `git fetch` + `git checkout -B main origin/main`。
工作流不会删除未入库的 `.env`、`docker/volumes`、`var/`；但会**拒绝**在
存在已跟踪文件修改，或服务器 HEAD 包含未推送到 `origin/main` 的本地 commit 时部署。

## 2. 生成部署专用 SSH key（在本地机器执行）

> 如果你现在正登录在服务器上（提示符是 `ubuntu@...`），第 1 节可以直接做；
> 但本节要先 `exit` 回到本地机器再执行。原因是私钥要交给 GitHub Actions，
> 不应该留在服务器上。

### 为什么需要 key，为什么在本地生成

SSH 登录使用一对 key：

- **私钥**保存在 GitHub Actions Secret，部署时写入 GitHub 的临时 runner；
- **公钥**放到服务器部署用户的 `~/.ssh/authorized_keys`。

服务器是 SSH 服务端，只需要公钥，**不需要私钥**。所以正确做法是：

1. 在本地机器生成 key pair；
2. 公钥装到服务器；
3. 私钥填到 GitHub Secret `DEPLOY_SSH_KEY`。

也可以在服务器上生成 key，再把私钥复制到 GitHub，但这样私钥会额外留在服务器上，
泄露面更大，也容易误操作；不建议。

### 2.1 在本地生成 key

- 在本地机器执行

```shell
ssh-keygen -t ed25519 -C "minirag-github-actions" -f ~/.ssh/minirag_deploy -N ""
```

会生成两个文件：

- `~/.ssh/minirag_deploy`：私钥，只用于填 GitHub Secret；
- `~/.ssh/minirag_deploy.pub`：公钥，装到服务器。

不要复用个人 key，也不要把私钥放进仓库。

### 2.2 把公钥安装到服务器

推荐用 `ssh-copy-id`（macOS / Linux / WSL 通常自带）：

- 在本地机器执行；它会登录服务器并追加公钥

```shell
ssh-copy-id -i ~/.ssh/minirag_deploy.pub ubuntu@<SERVER>
```

如果本地没有 `ssh-copy-id`（例如 Windows PowerShell），用这条等价命令：

- 在本地机器执行；引号里的命令在服务器上执行

```shell
cat ~/.ssh/minirag_deploy.pub | ssh ubuntu@<SERVER> \
  'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
```

这条命令的分工是：

```text
本地机器: cat ~/.ssh/minirag_deploy.pub      # 读出公钥
本地机器: ssh ubuntu@<SERVER>                # 登录服务器
服务器:   cat >> ~/.ssh/authorized_keys      # 把公钥追加到服务器
```

注意：追加的是 `.pub` 公钥，不是私钥。

### 2.3 在本地测试 key

- 在本地机器执行；引号里的命令在服务器上执行

```shell
ssh -i ~/.ssh/minirag_deploy ubuntu@<SERVER> 'cd ~/deploy/MiniRAG && git status --short && docker compose version'
```

能登录并看到仓库状态，说明公钥和私钥匹配，服务器授权成功。

### 2.4 把私钥填到 GitHub Secret

`DEPLOY_SSH_KEY` 填 `~/.ssh/minirag_deploy` 的**私钥全文**（包含
`-----BEGIN OPENSSH PRIVATE KEY-----`），不是 `.pub` 文件。

```shell
# macOS 可复制到剪贴板，再粘贴到 GitHub Secret
pbcopy < ~/.ssh/minirag_deploy
```

`DEPLOY_KNOWN_HOSTS` 是另一回事：它是**服务器的主机公钥**，用 `ssh-keyscan`
获取，见下一节；不要和部署 key 混用。

### 2.5 为什么不能只“在服务器上执行”

因为触发部署的是 GitHub Actions runner，它不在你的服务器上，而是在 GitHub
临时创建的 VM 里。runner 要登录服务器，必须持有私钥；服务器只保存公钥。
`ssh ubuntu@<SERVER>` 就是从 runner（或你的本地机器）登录服务器的动作。

如果你希望命令直接在服务器上执行、完全不使用 SSH，可以改用第 7 节的
self-hosted runner 方案；那种方案不需要本节这套部署 key。

## 3. 配置 GitHub Secrets（在本地机器或 GitHub 网页操作）

仓库 Settings → Secrets and variables → Actions：

| Secret               | 必填 | 说明                                                   |
| -------------------- | ---- | ------------------------------------------------------ |
| `DEPLOY_HOST`        | 是   | 服务器 IP 或域名                                       |
| `DEPLOY_USER`        | 是   | SSH 用户，例如 `ubuntu`                                |
| `DEPLOY_PATH`        | 是   | 服务器仓库绝对路径，例如 `/home/ubuntu/deploy/MiniRAG` |
| `DEPLOY_SSH_KEY`     | 是   | 部署专用私钥全文                                       |
| `DEPLOY_KNOWN_HOSTS` | 是   | `ssh-keyscan -H -p 22 <SERVER>` 的输出                 |
| `DEPLOY_PORT`        | 否   | SSH 端口，默认 `22`                                    |

如果在**本地机器**已安装并登录 `gh` CLI，可以直接写入仓库 secrets：

```shell
gh secret set DEPLOY_HOST --body "<SERVER>"
gh secret set DEPLOY_USER --body "ubuntu"
gh secret set DEPLOY_PATH --body "/home/ubuntu/deploy/MiniRAG"
gh secret set DEPLOY_PORT --body "22"
gh secret set DEPLOY_SSH_KEY < ~/.ssh/minirag_deploy
ssh-keyscan -H -p 22 <SERVER> 2>/dev/null | gh secret set DEPLOY_KNOWN_HOSTS
```

如果 secrets 放在 `production` environment 下，给每条命令加 `--env production`。

生成 `DEPLOY_KNOWN_HOSTS`（在本地机器执行；它获取的是服务器主机公钥，不是部署 key）：

```shell
ssh-keyscan -H -p 22 <SERVER> 2>/dev/null
```

也可以把 secrets 放到 GitHub Environment `production` 中；workflow 已声明
`environment: production`。如果给该 environment 配置了 Required reviewers，
部署会等待人工批准。

## 4. 触发方式（在本地机器 push）

workflow 文件：[.github/workflows/deploy.yml](../.github/workflows/deploy.yml)

> 推送“包含 deploy.yml 的这次提交”本身也会触发一次部署。
> 建议先把服务器和 secrets 配好，再推送 workflow。

- `push` 到 `main`：自动部署，默认 `--mirror cn`；
- Actions 页面手动 `Run workflow`：可选择 `cn` / `auto` / `global` 镜像策略；
- `concurrency: deploy-production`：同一时间只跑一个部署，后续任务排队，
  不会中途取消正在进行的部署。

远程步骤：

1. 检查工作区是否有已跟踪文件修改，有则中止；
2. `git fetch --prune origin main`；
3. `git checkout -B main origin/main`（不删除未入库文件）；
4. `python3 minirag.py deploy --mirror "$MIRROR"`。

## 5. 安全与运维注意

- 使用独立的 ed25519 部署 key，只授权部署用户，不复用个人 key；
- `StrictHostKeyChecking=yes`，通过 `DEPLOY_KNOWN_HOSTS` 固定主机指纹；
- 不要把 `.env`、私钥、`docker/volumes` 提交到仓库；
- 建议给 `production` environment 开启审批或限制可部署分支；
- 服务器磁盘不足时，先在服务器执行：

  ```shell
  docker system df
  docker builder prune
  ```

  再触发部署；

- 工作流只更新代码，不修改服务器的 `.env`；配置变更需要手动编辑 `.env` 后重新部署；
- 部署失败时旧容器可能仍在运行；回滚方式见下一节。

## 6. 回滚（在服务器上执行）

```shell
cd ~/deploy/MiniRAG
git log --oneline -5
git checkout -B main <previous-commit>
python3 minirag.py deploy --mirror cn
```

不要只 `git reset` 而不重建镜像：容器使用的是构建好的镜像，代码回滚后需要
重新执行 `deploy` 才会生效。

## 7. 如果服务器无法被 GitHub-hosted runner SSH

部分国内服务器的安全组只允许固定 IP，而 GitHub-hosted runner 出口 IP 是动态的。
两种方案：

1. 安全组放行 GitHub Actions 的 IP 段（出口 IP 会变化，维护成本高）；
2. 在服务器上安装 **self-hosted runner**，把 workflow 的
   `runs-on: ubuntu-latest` 改为 `runs-on: [self-hosted, linux, x64]`，
   并去掉 SSH 步骤，直接在部署目录执行同样的 `git` + `minirag.py` 命令。

如果选择方案 2：

- **不需要第 2 节的 SSH key**，也不需要 `DEPLOY_SSH_KEY` / `DEPLOY_KNOWN_HOSTS`；
- workflow 直接在服务器上运行，本质就是“在服务器上执行命令”；
- 但仍需要配置 `DEPLOY_PATH`，并让 runner 用户有仓库和 Docker 权限。

self-hosted runner 能直接访问服务器本地环境，但 runner 本身拥有仓库读取和
服务器执行权限，建议只给私有仓库、限制 runner 组、定期更新。

## 8. 常见问题

| 现象                                                             | 排查                                                                                                                                               |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Permission denied (publickey)`                                  | 先在**本地**用 `ssh -i ~/.ssh/minirag_deploy ubuntu@<SERVER>` 测试；确认公钥在服务器 `authorized_keys`、`DEPLOY_SSH_KEY` 是私钥全文、用户/端口正确 |
| `Host key verification failed`                                   | 重新生成 `DEPLOY_KNOWN_HOSTS`，确认主机指纹                                                                                                        |
| `permission denied while trying to connect to the Docker daemon` | 部署用户加入 `docker` 组并重新登录                                                                                                                 |
| `Server working tree has tracked changes`                        | 服务器上有未提交的已跟踪改动，先提交/恢复再部署                                                                                                    |
| `Server HEAD has commits not in origin/main`                     | 服务器有本地 commit，确认后 `git reset --hard origin/main` 或先推送                                                                                |
| `No space left on device`                                        | `docker system df`、`docker builder prune`，清理旧镜像/构建缓存                                                                                    |
| 部署卡在 `uv sync`                                               | 检查服务器访问 PyPI 的情况，workflow 默认 `--mirror cn`；也可手动选择 `auto`                                                                       |
| `port is already allocated`                                      | 服务器上已有占端口的进程，先停止再部署                                                                                                             |
