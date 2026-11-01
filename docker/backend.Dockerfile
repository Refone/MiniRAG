# 基础镜像可通过 build-arg 换成国内镜像站地址，例如:
#   PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim
#   UV_IMAGE=ghcr.nju.edu.cn/astral-sh/uv:latest
ARG PYTHON_IMAGE=python:3.12-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:latest

# 单独一层用于拷贝 uv 静态二进制 (COPY --from 不支持变量展开)
FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE}

COPY --from=uv /uv /uvx /bin/

ENV PYTHONPATH=/app/src \
    PROJECT_ROOT=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# 依赖层 (可缓存): 只复制依赖清单, 避免源码改动触发重装 torch 等重依赖
COPY pyproject.toml uv.lock ./

# 国内网络可传 --build-arg UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple。
# uv.lock 记录的是 pypi.org / files.pythonhosted.org 地址, 仅设置索引不会改变
# 已锁定 wheel 的下载地址; 因此先用镜像重新锁定 (版本不变, 只重写 source/URL),
# 再用 --frozen 安装。
#
# 单一镜像可能对个别包返回 403 / 暂缺 (例如 chunkana), 所以对已知国内镜像
# 自动按 Aliyun -> 清华 -> 腾讯云 -> 华为云 -> 官方源 依次回退。
ARG UV_INDEX_URL=https://pypi.org/simple
RUN set -eu; \
    if [ "$UV_INDEX_URL" = "https://pypi.org/simple" ]; then \
        uv sync --frozen --no-dev --no-install-project; \
    else \
        indices="$UV_INDEX_URL"; \
        case "$UV_INDEX_URL" in \
            https://mirrors.aliyun.com/*|https://pypi.tuna.tsinghua.edu.cn/*|https://mirrors.cloud.tencent.com/*|https://repo.huaweicloud.com/*) \
                indices="$indices https://mirrors.aliyun.com/pypi/simple https://pypi.tuna.tsinghua.edu.cn/simple https://mirrors.cloud.tencent.com/pypi/simple https://repo.huaweicloud.com/repository/pypi/simple https://pypi.org/simple" ;; \
        esac; \
        for index in $indices; do \
            echo "==> PyPI index: $index"; \
            if uv lock --default-index "$index" \
                && uv sync --frozen --no-dev --no-install-project; then \
                exit 0; \
            fi; \
            echo "!! PyPI index failed: $index"; \
        done; \
        exit 1; \
    fi

# 源码层
COPY src ./src

EXPOSE 8000

# 直接用 venv 内的 uvicorn, 避免 uv run 重新探测/构建项目
CMD [".venv/bin/uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
