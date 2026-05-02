#!/usr/bin/env bash
# scripts/status.sh
# 检查 Bilibili RAG 后端服务状态
set -euo pipefail

PORT="${1:-8000}"

find_pid() {
    if command -v lsof >/dev/null 2>&1; then
        lsof -ti :"$PORT" 2>/dev/null | head -1
    elif command -v ss >/dev/null 2>&1; then
        ss -tlnp 2>/dev/null | grep ":$PORT " | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -1
    fi
}

PID=$(find_pid "$PORT")

if [[ -z "$PID" ]]; then
    echo "{\"running\":false,\"port\":$PORT,\"pid\":null}"
    exit 1
fi

# 检查进程是否存活
if kill -0 "$PID" 2>/dev/null; then
    echo "{\"running\":true,\"port\":$PORT,\"pid\":$PID}"
    exit 0
else
    echo "{\"running\":false,\"port\":$PORT,\"pid\":null}"
    exit 1
fi