#!/bin/bash
# 启动 Next.js 前端

echo "🎨 启动 Next.js 前端..."

cd frontend

# 安装依赖（如果需要）
if [ ! -d "node_modules" ]; then
    echo "📦 安装依赖..."
    npm install
fi

# 启动开发服务器
npm run dev
