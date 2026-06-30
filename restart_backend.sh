#!/usr/bin/env bash
# 数学建模多Agent系统 - 后端重启脚本（v5.3.0）
# 设计原则：无 --reload（避免 reload 期间请求悬挂导致前端假死）
# 用法：./restart_backend.sh
# 行为：
#   1. 优雅停止已运行的后端（SIGTERM，等待 5s）
#   2. 强杀残留进程（SIGKILL，兜底）
#   3. 清理 8000 端口占用
#   4. 后台启动新后端（nohup，无 reload）
#   5. 等 8 秒后 ping /info 验证启动成功

set -euo pipefail

cd "$(dirname "$0")"
PROJECT_ROOT="$(pwd)"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

BACKEND_PORT=8000
LOG_FILE="/tmp/backend.log"

# ===== 1. 停止已运行的后端 =====
print_info "检查并停止已运行的后端..."
PIDS=$(pgrep -f "uvicorn app.main:app" || true)
if [ -n "$PIDS" ]; then
    echo "  找到进程: $PIDS"
    # 先 SIGTERM 优雅停
    kill -TERM $PIDS 2>/dev/null || true
    sleep 2
    # 如果还在，强杀
    REMAINING=$(pgrep -f "uvicorn app.main:app" || true)
    if [ -n "$REMAINING" ]; then
        print_warn "进程未优雅退出，强制 kill..."
        kill -KILL $REMAINING 2>/dev/null || true
        sleep 1
    fi
    print_ok "已停止旧后端"
else
    print_ok "未发现运行中的后端"
fi

# 兜底清理端口（极少用到）
if command -v fuser >/dev/null 2>&1; then
    fuser -k ${BACKEND_PORT}/tcp 2>/dev/null || true
fi

# ===== 2. 启动新后端 =====
print_info "启动新后端（无 --reload）..."

# 激活虚拟环境（如果存在）
if [ -d ".venv" ]; then
    source .venv/bin/activate
    PYTHON_CMD="python"
elif [ -d "backend/.venv" ]; then
    source backend/.venv/bin/activate
    PYTHON_CMD="python"
else
    PYTHON_CMD=$(command -v python3 || command -v python)
fi

cd "$PROJECT_ROOT/backend"
nohup $PYTHON_CMD -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port $BACKEND_PORT \
    --no-access-log \
    > "$LOG_FILE" 2>&1 &

BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"
cd "$PROJECT_ROOT"

# ===== 3. 等待并验证 =====
print_info "等待后端就绪（最多 15s）..."
for i in $(seq 1 30); do
    sleep 0.5
    if curl -sS --max-time 1 "http://localhost:${BACKEND_PORT}/api/v1/info" > /dev/null 2>&1; then
        echo
        print_ok "后端启动成功 (PID=$BACKEND_PID, port=$BACKEND_PORT)"
        print_info "日志: $LOG_FILE"
        print_info "API: http://localhost:${BACKEND_PORT}/api/v1"
        print_info "API 文档: http://localhost:${BACKEND_PORT}/docs"
        exit 0
    fi
done

echo
print_error "后端启动超时（15s 未响应 /info）"
print_info "查看日志最后 30 行:"
echo "---"
tail -30 "$LOG_FILE" 2>/dev/null || echo "无日志"
echo "---"
exit 1