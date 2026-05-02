# ====== Frontend: Next.js ======
# Stage 1: 构建
FROM node:22-alpine AS builder

WORKDIR /app

# 安装依赖（利用 Docker layer cache）
COPY package.json package-lock.json ./
RUN npm ci

# 复制源码
COPY . .

# 构建（standalone 模式，见 next.config.ts）
RUN npm run build

# Stage 2: 运行
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup -g 1001 -S appgroup && adduser -S appuser -u 1001 -G appgroup

# 仅复制 standalone 输出 + 静态文件
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

# 确保 next.config.ts 中 output: "standalone" 后的额外文件
COPY --from=builder --chown=appuser:appgroup /app/.next/standalone ./

RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 3000

CMD ["node", "server.js"]
