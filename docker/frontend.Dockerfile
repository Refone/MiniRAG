# 前端镜像: Vite 多阶段构建 -> nginx 托管静态资源并反代 /api 到后端
# 构建上下文为仓库根目录, 故 COPY 路径带 web/ 前缀。
#
# 基础镜像与 npm registry 可通过 build-arg 换成国内镜像站:
#   NODE_IMAGE=docker.m.daocloud.io/library/node:22-alpine
#   NGINX_IMAGE=docker.m.daocloud.io/library/nginx:alpine
#   NPM_REGISTRY=https://registry.npmmirror.com

ARG NODE_IMAGE=node:22-alpine
ARG NGINX_IMAGE=nginx:alpine

# ---- 构建阶段 ----
FROM ${NODE_IMAGE} AS build
WORKDIR /app
COPY web/package*.json ./
ARG NPM_REGISTRY=https://registry.npmjs.org
RUN npm install --registry="$NPM_REGISTRY"
COPY web/ .
RUN npm run build

# ---- 运行阶段 ----
FROM ${NGINX_IMAGE}
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
