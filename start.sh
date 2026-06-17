#!/usr/bin/env bash
# 数学建模多Agent系统 - 一键启动脚本（Linux / macOS）
# 用法：./start.sh
# 功能：检测环境、创建虚拟环境、安装前后端依赖、启动服务

set -euo pipefail

cd "$(dirname "$0")"
PROJECT_ROOT="$(pwd)"

echo "========================================"
echo "  多智能体协作论文生产系统 启动器"
echo "========================================"
echo

# 检查 Python
if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] 未找到 python3。请先安装 Python 3.9+ (https://www.python.org/)"
    exit 1
fi

PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
    echo "[ERROR] Python 版本过低，需要 3.9+。当前：$PY_VERSION"
    exit 1
fi
echo "[OK] Python $PY_VERSION"

# 检查 Node.js
if ! command -v node >/dev/null 2>&1; then
    echo "[ERROR] 未找到 Node.js。请先安装 Node.js 18+ (https://nodejs.org/)"
    exit 1
fi

NODE_MAJOR=$(node --version | sed 's/^v//' | cut -d. -f1)
if [ "$NODE_MAJOR" -lt 18 ]; then
    echo "[ERROR] Node.js 版本过低，需要 18+。当前：$(node --version)"
    exit 1
fi
echo "[OK] Node.js $(node --version)"

# 创建虚拟环境
if [ ! -d ".venv" ]; then
    echo "[INFO] 创建 Python 虚拟环境 .venv..."
    python3 -m venv .venv
fi

# 安装后端依赖
echo "[1/4] 检查并安装后端依赖..."
source .venv/bin/activate
python -m pip install -q --upgrade pip
python -m pip install -q -r backend/requirements.txt

# 安装前端依赖
echo "[2/4] 检查并安装前端依赖..."
cd frontend
if [ ! -d "node_modules" ]; then
    echo "[INFO] 首次安装前端依赖，可能需要几分钟..."
    npm install
else
    echo "[INFO] 前端依赖已安装，跳过"
fi
cd "$PROJECT_ROOT"

# 创建必要目录
echo "[3/4] 创建必要目录..."
mkdir -p data/uploads data/tasks data/knowledge_files data/memory

# 检查 .env
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp ".env.example" ".env"
        echo "[WARN] 已从 .env.example 创建 .env，请编辑填写你的 LLM API Key"
    else
        echo "[WARN] 未找到 .env.example，请手动创建 .env 并配置 API Key"
    fi
fi

# 启动服务
echo "[4/4] 启动服务..."
echo
echo "访问地址："
echo "  - 前端：http://localhost:3000"
echo "  - 后端 API：http://localhost:8000/api/v1"
echo "  - API 文档：http://localhost:8000/docs"
echo
echo "按 Ctrl+C 停止服务"
echo

cleanup() {
    echo
    echo "[INFO] 正在停止服务..."
    jobs -p | xargs -r kill
    exit 0
}
trap cleanup INT TERM EXIT

source .venv/bin/activate
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

cd "$PROJECT_ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

wait $BACKEND_PID $FRONTEND_PID
