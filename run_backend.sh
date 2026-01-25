#!/bin/bash
# 启动后端 API 服务

echo "🚀 启动 Bilibili RAG 后端服务..."

# 激活 conda 环境
source $(conda info --base)/etc/profile.d/conda.sh
conda activate bilibili-rag

# 创建必要目录
mkdir -p data logs

# 启动服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
