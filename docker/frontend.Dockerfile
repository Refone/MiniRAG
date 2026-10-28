# 前端镜像: Vite 多阶段构建 -> nginx 托管静态资源并反代 /api 到后端
# 构建上下文为仓库根目录, 故 COPY 路径带 web/ 前缀。

# ---- 构建阶段 ----
FROM node:22-alpine AS build
WORKDIR /app
COPY web/package*.json ./
RUN npm install
COPY web/ .
RUN npm run build

# ---- 运行阶段 ----
FROM nginx:alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
