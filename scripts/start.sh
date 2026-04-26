#!/usr/bin/env bash
# scripts/start.sh
# 启动 Bilibili RAG 后端服务
# 要求：conda 环境 bilibili-rag 已存在
set -euo pipefail

PORT="${1:-8000}"
CONDA_ENV="bilibili-rag"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log_info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}   $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# 检查端口是否被占用
if command -v lsof >/dev/null 2>&1; then
    if lsof -i :"$PORT" >/dev/null 2>&1; then
        log_error "Port $PORT is already in use"
        exit 1
    fi
elif command -v ss >/dev/null 2>&1; then
    if ss -tln | grep -q ":$PORT "; then
        log_error "Port $PORT is already in use"
        exit 1
    fi
fi

log_info "Starting service on port $PORT..."

# 使用 conda activate + 后台启动，捕获真正的 uvicorn PID
# shellcheck disable=SC2086
eval "$(conda shell.bash hook 2>/dev/null)"
conda activate "$CONDA_ENV" 2>/dev/null || true

nohup python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" \
    > /dev/null 2>&1 &
UVICORN_PID=$!

log_info "Waiting for service to be ready..."

# 等待端口就绪，最多 30 秒
for i in $(seq 1 30); do
    sleep 1
    if command -v lsof >/dev/null 2>&1; then
        if lsof -i :"$PORT" >/dev/null 2>&1; then
            log_ok "Service running at http://127.0.0.1:$PORT (PID: $UVICORN_PID)"
            echo "$PORT"
            exit 0
        fi
    elif command -v ss >/dev/null 2>&1; then
        if ss -tln | grep -q ":$PORT "; then
            log_ok "Service running at http://127.0.0.1:$PORT (PID: $UVICORN_PID)"
            echo "$PORT"
            exit 0
        fi
    fi
done

log_error "Service failed to start within 30s"
kill "$UVICORN_PID" 2>/dev/null || true
exit 1