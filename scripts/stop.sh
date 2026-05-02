#!/usr/bin/env bash
# scripts/stop.sh
# 停止 Bilibili RAG 后端服务
set -euo pipefail

PORT="${1:-8000}"
TIMEOUT=10

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*" >&2; }
log_ok()    { echo -e "${GREEN}[OK]${NC}   $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# 查找端口对应的进程 PID
find_pid() {
    local port="$1"
    if command -v lsof >/dev/null 2>&1; then
        # Linux/macOS 通用 lsof
        lsof -ti :"$port" 2>/dev/null | head -1
    elif command -v ss >/dev/null 2>&1; then
        # fallback: ss
        ss -tlnp 2>/dev/null | grep ":$port " | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -1
    fi
}

PID=$(find_pid "$PORT")

if [[ -z "$PID" ]]; then
    log_ok "Port $PORT is not in use, service is not running"
    exit 0
fi

log_ok "Found process $PID on port $PORT"

# 尝试优雅终止
kill -TERM "$PID" 2>/dev/null
for i in $(seq 1 "$TIMEOUT"); do
    if ! kill -0 "$PID" 2>/dev/null; then
        log_ok "Service stopped gracefully"
        exit 0
    fi
    sleep 1
done

# 强制终止
log_warn "Force stopping..."
kill -KILL "$PID" 2>/dev/null || true
log_ok "Process forcefully stopped"
exit 0