#!/usr/bin/env bash
# 数学建模多Agent系统 - 一键启动脚本（Linux / macOS）
# 用法：./start.sh
# 功能：检测环境、创建虚拟环境、安装前后端依赖、启动服务
# 设计原则：对无技术基础用户友好，每一步都有明确提示和自动修复

set -euo pipefail

cd "$(dirname "$0")"
PROJECT_ROOT="$(pwd)"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  多智能体协作论文生产系统 启动器${NC}"
    echo -e "${BLUE}  版本: v3.1 | 全自动论文产线${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
}

print_ok() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header

# ===== 1. 检查 Python =====
print_info "检查 Python 环境..."
PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    print_error "未找到 Python。请安装 Python 3.9+"
    echo "  macOS:   brew install python3"
    echo "  Ubuntu:  sudo apt install python3 python3-venv"
    echo "  其他系统: https://www.python.org/downloads/"
    exit 1
fi

PY_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
    print_error "Python 版本过低，需要 3.9+。当前：$PY_VERSION"
    exit 1
fi
print_ok "Python $PY_VERSION"

# ===== 2. 检查 Node.js =====
print_info "检查 Node.js 环境..."
if ! command -v node >/dev/null 2>&1; then
    print_error "未找到 Node.js。请安装 Node.js 18+"
    echo "  macOS:   brew install node"
    echo "  Ubuntu:  sudo apt install nodejs npm"
    echo "  其他系统: https://nodejs.org/"
    exit 1
fi

NODE_MAJOR=$(node --version | sed 's/^v//' | cut -d. -f1)
if [ "$NODE_MAJOR" -lt 18 ]; then
    print_error "Node.js 版本过低，需要 18+。当前：$(node --version)"
    exit 1
fi
print_ok "Node.js $(node --version)"

# ===== 3. 检查 npm =====
if ! command -v npm >/dev/null 2>&1; then
    print_error "未找到 npm。请安装 npm（通常随 Node.js 一起安装）"
    exit 1
fi
print_ok "npm $(npm --version)"

# ===== 4. 检查端口占用 =====
print_info "检查端口占用..."
BACKEND_PORT=8000
FRONTEND_PORT=3000

# 自动寻找可用端口
while lsof -Pi :$BACKEND_PORT -sTCP:LISTEN -t >/dev/null 2>&1; do
    BACKEND_PORT=$((BACKEND_PORT + 1))
done
while lsof -Pi :$FRONTEND_PORT -sTCP:LISTEN -t >/dev/null 2>&1; do
    FRONTEND_PORT=$((FRONTEND_PORT + 1))
done

if [ "$BACKEND_PORT" -ne 8000 ]; then
    print_warn "端口 8000 被占用，后端将使用端口 $BACKEND_PORT"
fi
if [ "$FRONTEND_PORT" -ne 3000 ]; then
    print_warn "端口 3000 被占用，前端将使用端口 $FRONTEND_PORT"
fi

# ===== 5. 创建虚拟环境 =====
if [ ! -d ".venv" ]; then
    print_info "创建 Python 虚拟环境 .venv..."
    $PYTHON_CMD -m venv .venv
    print_ok "虚拟环境创建完成"
else
    print_ok "虚拟环境已存在"
fi

# ===== 6. 安装后端依赖 =====
print_info "[1/5] 检查并安装后端依赖..."
source .venv/bin/activate
python -m pip install -q --upgrade pip 2>/dev/null || true

if [ ! -f "backend/requirements.txt" ]; then
    print_error "未找到 backend/requirements.txt"
    exit 1
fi

# 检查是否需要安装（通过对比文件修改时间）
REQ_HASH=$(md5sum backend/requirements.txt 2>/dev/null | awk '{print $1}')
INSTALLED_HASH=""
if [ -f ".venv/.req_hash" ]; then
    INSTALLED_HASH=$(cat .venv/.req_hash)
fi

if [ "$REQ_HASH" != "$INSTALLED_HASH" ]; then
    print_info "安装后端依赖（首次或 requirements.txt 已更新）..."
    python -m pip install -q -r backend/requirements.txt || {
        print_warn "快速安装失败，尝试完整安装..."
        python -m pip install -r backend/requirements.txt
    }
    echo "$REQ_HASH" > .venv/.req_hash
    print_ok "后端依赖安装完成"
else
    print_ok "后端依赖已是最新"
fi

# ===== 7. 安装前端依赖 =====
print_info "[2/5] 检查并安装前端依赖..."
cd frontend
if [ ! -f "package.json" ]; then
    print_error "未找到 frontend/package.json"
    exit 1
fi

if [ ! -d "node_modules" ]; then
    print_info "首次安装前端依赖，可能需要 2-3 分钟..."
    npm install
    print_ok "前端依赖安装完成"
else
    # 检查 package.json 是否更新
    PKG_HASH=$(md5sum package.json 2>/dev/null | awk '{print $1}')
    INSTALLED_PKG_HASH=""
    if [ -f "node_modules/.pkg_hash" ]; then
        INSTALLED_PKG_HASH=$(cat node_modules/.pkg_hash)
    fi
    if [ "$PKG_HASH" != "$INSTALLED_PKG_HASH" ]; then
        print_info "package.json 已更新，重新安装前端依赖..."
        npm install
        echo "$PKG_HASH" > node_modules/.pkg_hash
        print_ok "前端依赖更新完成"
    else
        print_ok "前端依赖已是最新"
    fi
fi
cd "$PROJECT_ROOT"

# ===== 8. 创建必要目录 =====
print_info "[3/5] 创建必要目录..."
mkdir -p data/uploads data/tasks data/knowledge_files data/memory data/venvs data/checkpoints data/langgraph_results
print_ok "目录结构已就绪"

# ===== 9. 检查环境配置 =====
print_info "[4/5] 检查环境配置..."

# 创建 .env（如果不存在）
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp ".env.example" ".env"
        print_warn ".env 已自动创建（从 .env.example 复制）"
    else
        print_warn ".env 和 .env.example 都不存在，将使用默认配置"
    fi
fi

# 创建 backend/.env（如果不存在）
if [ ! -f "backend/.env" ]; then
    if [ -f "backend/.env.example" ]; then
        cp "backend/.env.example" "backend/.env"
        print_ok "backend/.env 已自动创建"
    elif [ -f ".env" ]; then
        cp ".env" "backend/.env"
        print_ok "backend/.env 已自动创建（从 .env 复制）"
    fi
fi

# 检查 API Key 配置
ENV_CONFIGURED=false
if [ -f ".env" ]; then
    # 检查是否已配置真实 API Key（排除占位符）
    if grep -qE "API_KEY=sk-|API_KEY=AK-|OPENAI_API_KEY=sk-|ANTHROPIC_API_KEY=sk-" .env 2>/dev/null; then
        ENV_CONFIGURED=true
        print_ok "已检测到 API Key 配置"
    elif grep -qE "your_api_key_here|YOUR_API_KEY|placeholder|changeme" .env 2>/dev/null; then
        print_warn ".env 中存在未修改的占位符 API Key"
    fi
fi

# 检查 CC-Switch / custom_providers.json 配置
if [ -f "backend/custom_providers.json" ]; then
    PROVIDER_COUNT=$(python -c "import json; data=json.load(open('backend/custom_providers.json')); print(len(data.get('providers', [])))" 2>/dev/null || echo "0")
    if [ "$PROVIDER_COUNT" -gt 0 ]; then
        print_ok "已配置 $PROVIDER_COUNT 个 LLM Provider"
        ENV_CONFIGURED=true
    fi
fi

if [ "$ENV_CONFIGURED" = false ]; then
    echo
    print_warn "⚠️  尚未配置 LLM API Key！"
    echo
    echo "  系统需要至少一个 LLM Provider 才能运行。请按以下步骤配置："
    echo
    echo "  方法 1（推荐）: 通过前端设置界面"
    echo "    1. 启动后访问 http://localhost:$FRONTEND_PORT"
    echo "    2. 点击「设置」Tab → 添加 Provider"
    echo "    3. 选择你的 Provider（OpenAI / Anthropic / 阿里百炼 / 硅基流动 / DeepSeek 等）"
    echo "    4. 填写 API Key 和模型名称"
    echo
    echo "  方法 2: 手动编辑 .env"
    echo "    编辑 .env 文件，填写你的 API Key:"
    echo "      API_KEY=sk-..."
    echo "      或 OPENAI_API_KEY=sk-..."
    echo "      或 ANTHROPIC_API_KEY=sk-..."
    echo
    echo "  支持的 Provider: OpenAI, Anthropic, 阿里百炼, 硅基流动, 智谱, DeepSeek, Ollama, OpenRouter..."
    echo
    read -p "按 Enter 继续启动（系统将使用默认配置，可能无法调用 LLM）..." </dev/tty
fi

# ===== 10. 启动服务 =====
print_info "[5/5] 启动服务..."
echo
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  服务启动完成！访问地址：${NC}"
echo -e "${GREEN}  • 前端界面: http://localhost:$FRONTEND_PORT${NC}"
echo -e "${GREEN}  • 后端 API: http://localhost:$BACKEND_PORT/api/v1${NC}"
echo -e "${GREEN}  • API 文档: http://localhost:$BACKEND_PORT/docs${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo
echo "使用说明："
echo "  1. 打开 http://localhost:$FRONTEND_PORT"
echo "  2. 选择论文模板（NeurIPS / ACM / IEEE / Springer / CUMCM）"
echo "  3. 输入研究题目或问题描述"
echo "  4. 点击提交，系统自动完成：分析→建模→求解→实验→论文→评议"
echo "  5. 在「PDF」Tab 下载 Camera-Ready 投稿包"
echo
echo "按 Ctrl+C 停止服务"
echo

# 保存端口配置到临时文件，供前端读取
echo "{" > .ports.json
echo "  \"backend_port\": $BACKEND_PORT," >> .ports.json
echo "  \"frontend_port\": $FRONTEND_PORT" >> .ports.json
echo "}" >> .ports.json

# 清理函数
cleanup() {
    echo
    print_info "正在停止服务..."
    # 优雅地停止后台进程
    if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "${FRONTEND_PID:-}" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        kill "$FRONTEND_PID" 2>/dev/null || true
        wait "$FRONTEND_PID" 2>/dev/null || true
    fi
    rm -f .ports.json
    print_ok "服务已停止"
    exit 0
}
trap cleanup INT TERM EXIT

source .venv/bin/activate
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --reload &
BACKEND_PID=$!

cd "$PROJECT_ROOT/frontend"
npm run dev -- --port $FRONTEND_PORT &
FRONTEND_PID=$!

wait $BACKEND_PID $FRONTEND_PID
