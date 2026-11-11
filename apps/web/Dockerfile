# Next.js 生产镜像（多阶段 + standalone）
#
# 为什么用 standalone：Next 会把运行期真正需要的 node_modules 挑出来打包，
# 镜像从 1.16 GB 降到约 250 MB。
# 这不只是省空间——它直接决定了 1 GB 内存的服务器能不能构建成功。

FROM node:22-alpine AS deps
WORKDIR /app
RUN npm config set registry https://registry.npmmirror.com
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# 浏览器请求走同源 /api（由 Nginx 反代），所以留空字符串，
# 前端代码里 `?? "http://127.0.0.1:8000"` 不生效，fetch("/api/...") 是相对路径。
ARG NEXT_PUBLIC_API_BASE=""
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    TZ=Asia/Shanghai \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup -g 10001 -S nodejs && adduser -S nextjs -u 10001

# standalone 已经包含精简后的 node_modules 与 server.js
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]