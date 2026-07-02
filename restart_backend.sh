#!/usr/bin/env bash
# 数学建模多Agent系统 - 后端重启脚本（v5.4.0）
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
CYAN='\033[0;36m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

BACKEND_PORT=8000
LOG_FILE="/tmp/backend.log"

# ===== 1. 激活 Python 环境 =====
print_info "配置 Python 环境..."

USE_CONDA=false
CONDA_ENV_NAME=""

# 优先使用缓存的环境名
CACHE_FILE="$PROJECT_ROOT/.conda_env_cache"
if [ -f "$CACHE_FILE" ]; then
    CONDA_ENV_NAME=$(cat "$CACHE_FILE")
fi

if command -v conda >/dev/null 2>&1; then
    if [ -n "$CONDA_ENV_NAME" ]; then
        print_info "使用缓存的 conda 环境: $CONDA_ENV_NAME"
    else
        echo "可用 conda 环境："
        conda env list 2>/dev/null | grep -v "^#" | grep -v "^$" | awk '{print "  " $1}'
        echo
        read -p "请输入 conda 环境名（回车则用 venv）: " CONDA_ENV_NAME </dev/tty
    fi

    if [ -n "$CONDA_ENV_NAME" ]; then
        if conda env list 2>/dev/null | grep -q "^${CONDA_ENV_NAME} "; then
            eval "$(conda shell.bash hook 2>/dev/null)"
            conda activate "$CONDA_ENV_NAME"
            USE_CONDA=true
            echo "$CONDA_ENV_NAME" > "$CACHE_FILE"
            print_ok "conda 环境 $CONDA_ENV_NAME 已激活"
        else
            print_warn "环境 $CONDA_ENV_NAME 不存在，尝试创建..."
            conda create -n "$CONDA_ENV_NAME" python=3.11 -y
            eval "$(conda shell.bash hook 2>/dev/null)"
            conda activate "$CONDA_ENV_NAME"
            USE_CONDA=true
            echo "$CONDA_ENV_NAME" > "$CACHE_FILE"
            print_ok "环境 $CONDA_ENV_NAME 已创建并激活"
        fi
    fi
fi

if [ "$USE_CONDA" = false ]; then
    if [ -d ".venv" ]; then
        source .venv/bin/activate
        print_ok "venv 环境已激活"
    elif [ -d "backend/.venv" ]; then
        source backend/.venv/bin/activate
        print_ok "venv 环境已激活"
    else
        PYTHON_CMD=$(command -v python3 || command -v python)
        print_warn "未找到虚拟环境，使用系统 Python: $PYTHON_CMD"
    fi
fi

# ===== 2. 验证依赖 =====
print_info "验证关键依赖..."
python -c "
import importlib, sys
pkgs = ['fastapi', 'uvicorn', 'pydantic', 'httpx', 'langgraph']
missing = []
for p in pkgs:
    try: importlib.import_module(p)
    except ImportError: missing.append(p)
if missing:
    print(f'缺失: {missing}', file=sys.stderr)
    sys.exit(1)
print('依赖已就绪')
" 2>/dev/null || {
    print_warn "检测到缺失依赖，自动安装..."
    python -m pip install -q -r backend/requirements.txt
    print_ok "依赖补装完成"
}

# ===== 3. 停止已运行的后端 =====
print_info "检查并停止已运行的后端..."
PIDS=$(pgrep -f "uvicorn app.main:app" || true)
if [ -n "$PIDS" ]; then
    echo "  找到进程: $PIDS"
    kill -TERM $PIDS 2>/dev/null || true
    sleep 2
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

# 兜底清理端口
if command -v fuser >/dev/null 2>&1; then
    fuser -k ${BACKEND_PORT}/tcp 2>/dev/null || true
fi

# ===== 4. 启动新后端 =====
print_info "启动新后端（无 --reload）..."

cd "$PROJECT_ROOT/backend"
nohup python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port $BACKEND_PORT \
    --no-access-log \
    > "$LOG_FILE" 2>&1 &

BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"
cd "$PROJECT_ROOT"

# ===== 5. 等待并验证 =====
print_info "等待后端就绪（最多 15s）..."
for i in $(seq 1 30); do
    sleep 0.5
    if curl -sS --max-time 1 "http://localhost:${BACKEND_PORT}/api/v1/info" > /dev/null 2>&1; then
        echo
        print_ok "后端启动成功 (PID=$BACKEND_PID, port=$BACKEND_PORT)"
        [ "$USE_CONDA" = true ] && print_info "Conda 环境: $CONDA_ENV_NAME"
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
