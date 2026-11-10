# Next.js 生产镜像（多阶段）
# 1. deps 阶段只装依赖：package.json 没变时这层直接命中缓存
# 2. build 阶段产出 .next
# 3. runner 只带运行时必需文件，镜像体积能砍掉一半以上

FROM node:22-alpine AS deps
WORKDIR /app
RUN npm config set registry https://registry.npmmirror.com
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# 关键：浏览器请求走同源 /api（由 Nginx 反代），所以这里留空字符串，
# 前端代码里 `?? "http://127.0.0.1:8000"` 不会生效，fetch("/api/...") 是相对路径。
ARG NEXT_PUBLIC_API_BASE=""
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    TZ=Asia/Shanghai

RUN addgroup -g 10001 -S nodejs && adduser -S nextjs -u 10001

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

USER nextjs
EXPOSE 3000
CMD ["npm", "start"]