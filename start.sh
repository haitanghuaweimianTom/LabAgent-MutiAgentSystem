#!/usr/bin/env bash
# 数学建模多Agent系统 - 一键启动脚本（Linux / macOS）
# 用法：./start.sh
# 功能：检测环境、创建虚拟环境、安装前后端依赖、build前端、检测/重启前后端、启动服务
# 设计原则：对无技术基础用户友好，双击即可运行，一切自动化

set -euo pipefail

cd "$(dirname "$0")"
PROJECT_ROOT="$(pwd)"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  多智能体协作论文生产系统 启动器                                  ║${NC}"
    echo -e "${CYAN}║  版本: v5.3.0 | 全自动论文产线 | 数据驱动+知识库+RAG            ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════╝${NC}"
    echo
}

print_ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error(){ echo -e "${RED}[ERROR]${NC} $1"; }
print_step() { echo -e "${CYAN}▶ $1${NC}"; }

print_header

# ===== 1. 检查 Python =====
print_step "[1/7] 检查 Python 环境..."
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
print_step "[2/7] 检查 Node.js 环境..."
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

if ! command -v npm >/dev/null 2>&1; then
    print_error "未找到 npm。请重新安装 Node.js"
    exit 1
fi
print_ok "npm $(npm --version)"

# ===== 3. 检查端口 & 检测已运行服务 =====
print_step "[3/7] 检查端口占用 & 检测已运行服务..."
BACKEND_PORT=8000
FRONTEND_PORT=3000

# 检测后端是否已运行
BACKEND_RUNNING=false
if curl -sS --max-time 1 "http://localhost:${BACKEND_PORT}/api/v1/info" >/dev/null 2>&1; then
    print_warn "后端已在端口 $BACKEND_PORT 运行"
    BACKEND_RUNNING=true
fi

# 检测前端是否已运行
FRONTEND_RUNNING=false
if curl -sS --max-time 1 "http://localhost:${FRONTEND_PORT}" >/dev/null 2>&1; then
    print_warn "前端已在端口 $FRONTEND_PORT 运行"
    FRONTEND_RUNNING=true
fi

# 如果前后端都已运行，提示并重启
if [ "$BACKEND_RUNNING" = true ] && [ "$FRONTEND_RUNNING" = true ]; then
    print_warn "检测到前后端均已运行，将重新启动..."
fi

# 自动寻找可用端口（如果当前端口被非本项目占用）
while lsof -Pi :$BACKEND_PORT -sTCP:LISTEN -t >/dev/null 2>&1; do
    # 如果是本项目后端在运行，先停止它
    if [ "$BACKEND_RUNNING" = true ] && [ "$BACKEND_PORT" -eq 8000 ]; then
        break
    fi
    BACKEND_PORT=$((BACKEND_PORT + 1))
done
while lsof -Pi :$FRONTEND_PORT -sTCP:LISTEN -t >/dev/null 2>&1; do
    if [ "$FRONTEND_RUNNING" = true ] && [ "$FRONTEND_PORT" -eq 3000 ]; then
        break
    fi
    FRONTEND_PORT=$((FRONTEND_PORT + 1))
done

if [ "$BACKEND_PORT" -ne 8000 ]; then
    print_warn "端口 8000 被占用，后端将使用端口 $BACKEND_PORT"
fi
if [ "$FRONTEND_PORT" -ne 3000 ]; then
    print_warn "端口 3000 被占用，前端将使用端口 $FRONTEND_PORT"
fi

# ===== 4. 停止已运行服务 =====
print_step "[4/7] 停止已运行服务（如有）..."

# 停止后端
STOPPED_BACKEND=false
PIDS=$(pgrep -f "uvicorn app.main:app" || true)
if [ -n "$PIDS" ]; then
    print_info "停止后端进程: $PIDS"
    kill -TERM $PIDS 2>/dev/null || true
    sleep 2
    REMAINING=$(pgrep -f "uvicorn app.main:app" || true)
    if [ -n "$REMAINING" ]; then
        kill -KILL $REMAINING 2>/dev/null || true
        sleep 1
    fi
    # 清理端口
    if command -v fuser >/dev/null 2>&1; then
        fuser -k ${BACKEND_PORT}/tcp 2>/dev/null || true
    fi
    print_ok "后端已停止"
    STOPPED_BACKEND=true
else
    print_ok "后端未运行"
fi

# 停止前端
STOPPED_FRONTEND=false
# 查找 next 进程
NEXT_PIDS=$(pgrep -f "next-server" || pgrep -f "next start" || true)
if [ -n "$NEXT_PIDS" ]; then
    print_info "停止前端进程: $NEXT_PIDS"
    kill -TERM $NEXT_PIDS 2>/dev/null || true
    sleep 1
    REMAINING=$(pgrep -f "next-server" || pgrep -f "next start" || true)
    if [ -n "$REMAINING" ]; then
        kill -KILL $REMAINING 2>/dev/null || true
    fi
    print_ok "前端已停止"
    STOPPED_FRONTEND=true
else
    print_ok "前端未运行"
fi

# 如果之前运行过且已停止，给用户一个反馈
if [ "$STOPPED_BACKEND" = true ] || [ "$STOPPED_FRONTEND" = true ]; then
    print_info "服务已重新启动"
fi

# ===== 5. 创建虚拟环境 & 安装后端依赖 =====
print_step "[5/7] 准备后端环境..."

if [ ! -d ".venv" ]; then
    print_info "创建 Python 虚拟环境 .venv..."
    $PYTHON_CMD -m venv .venv
    print_ok "虚拟环境创建完成"
else
    print_ok "虚拟环境已存在"
fi

source .venv/bin/activate
python -m pip install -q --upgrade pip 2>/dev/null || true

if [ ! -f "backend/requirements.txt" ]; then
    print_error "未找到 backend/requirements.txt"
    exit 1
fi

# 检查是否需要重新安装（通过对比文件修改时间）
REQ_HASH=$(md5sum backend/requirements.txt 2>/dev/null | awk '{print $1}')
INSTALLED_HASH=""
if [ -f ".venv/.req_hash" ]; then
    INSTALLED_HASH=$(cat .venv/.req_hash)
fi

if [ "$REQ_HASH" != "$INSTALLED_HASH" ]; then
    print_info "安装/更新后端依赖（requirements.txt 有变化）..."
    python -m pip install -q -r backend/requirements.txt || {
        print_warn "快速安装失败，尝试完整安装..."
        python -m pip install -r backend/requirements.txt
    }
    echo "$REQ_HASH" > .venv/.req_hash
    print_ok "后端依赖安装完成"
else
    print_ok "后端依赖已是最新"
fi

# ===== 6. 安装前端依赖 & Build =====
print_step "[6/7] 准备前端环境..."
cd frontend

if [ ! -f "package.json" ]; then
    print_error "未找到 frontend/package.json"
    exit 1
fi

# 检查是否需要 npm install
PKG_HASH=$(md5sum package.json 2>/dev/null | awk '{print $1}')
INSTALLED_PKG_HASH=""
if [ -f "node_modules/.pkg_hash" ]; then
    INSTALLED_PKG_HASH=$(cat node_modules/.pkg_hash)
fi

if [ ! -d "node_modules" ] || [ "$PKG_HASH" != "$INSTALLED_PKG_HASH" ]; then
    print_info "安装前端依赖..."
    npm install
    echo "$PKG_HASH" > node_modules/.pkg_hash
    print_ok "前端依赖安装完成"
else
    print_ok "前端依赖已是最新"
fi

# 检查是否需要重新 build
NEED_BUILD=false
if [ ! -d ".next" ]; then
    print_info "首次构建前端..."
    NEED_BUILD=true
else
    # 检查源码是否比 .next 新
    SRC_NEWER=$(find . -path ./node_modules -prune -o -path ./.next -prune -o -type f -newer .next/BUILD_ID -print -quit 2>/dev/null || true)
    if [ -n "$SRC_NEWER" ]; then
        print_info "前端源码有更新，需要重新构建..."
        NEED_BUILD=true
    fi
fi

if [ "$NEED_BUILD" = true ]; then
    print_info "构建前端（Next.js 生产构建）..."
    npm run build
    print_ok "前端构建完成"
else
    print_ok "前端构建已是最新"
fi

cd "$PROJECT_ROOT"

# ===== 7. 创建必要目录 =====
print_step "[7/7] 创建必要目录..."
mkdir -p data/uploads data/tasks data/knowledge_files data/memory data/venvs \
         data/checkpoints data/langgraph_results outputs reading global_references
print_ok "目录结构已就绪"

# ===== 8. 检查环境配置 =====
print_step "检查环境配置..."

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

# 检查 API Key / Provider 配置
ENV_CONFIGURED=false
if [ -f ".env" ]; then
    if grep -qE "API_KEY=sk-|API_KEY=AK-|OPENAI_API_KEY=sk-|ANTHROPIC_API_KEY=sk-" .env 2>/dev/null; then
        ENV_CONFIGURED=true
        print_ok "已检测到 API Key 配置"
    elif grep -qE "your_api_key_here|YOUR_API_KEY|placeholder|changeme" .env 2>/dev/null; then
        print_warn ".env 中存在未修改的占位符 API Key"
    fi
fi

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
    echo
    echo "  支持的 Provider: OpenAI, Anthropic, 阿里百炼, 硅基流动, 智谱, DeepSeek, Ollama, OpenRouter..."
    echo
    read -p "按 Enter 继续启动（系统将使用默认配置，可能无法调用 LLM）..." </dev/tty
fi

# ===== 9. 启动服务 =====
print_step "启动服务..."
echo
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  服务启动中...                                                    ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo

# 保存端口配置到临时文件
cat > .ports.json <<EOF
{
  "backend_port": $BACKEND_PORT,
  "frontend_port": $FRONTEND_PORT
}
EOF

# 清理函数
cleanup() {
    echo
    print_info "正在停止服务..."
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

# 启动后端（先启动，因为前端 SSR 需要后端 /info 接口）
print_info "启动后端服务（端口 $BACKEND_PORT）..."
source .venv/bin/activate
cd backend
nohup python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port $BACKEND_PORT \
    --no-access-log \
    > /tmp/backend.log 2>&1 &
BACKEND_PID=$!
cd "$PROJECT_ROOT"

# 等待后端就绪
print_info "等待后端就绪..."
for i in $(seq 1 30); do
    sleep 0.5
    if curl -sS --max-time 1 "http://localhost:${BACKEND_PORT}/api/v1/info" >/dev/null 2>&1; then
        print_ok "后端启动成功 (PID=$BACKEND_PID, port=$BACKEND_PORT)"
        break
    fi
    if [ "$i" -eq 30 ]; then
        print_error "后端启动超时（15s），查看日志:"
        tail -20 /tmp/backend.log 2>/dev/null || echo "无日志"
        exit 1
    fi
done

# 启动前端（生产模式 next start）
print_info "启动前端服务（端口 $FRONTEND_PORT，生产模式）..."
cd frontend
npm run start -- --port $FRONTEND_PORT > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!
cd "$PROJECT_ROOT"

# 等待前端就绪
print_info "等待前端就绪..."
for i in $(seq 1 30); do
    sleep 0.5
    if curl -sS --max-time 1 "http://localhost:${FRONTEND_PORT}" >/dev/null 2>&1; then
        print_ok "前端启动成功 (PID=$FRONTEND_PID, port=$FRONTEND_PORT)"
        break
    fi
    if [ "$i" -eq 30 ]; then
        print_warn "前端启动可能仍在进行中..."
    fi
done

# ===== 10. 启动完成提示 =====
echo
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✅ 服务启动完成！                                                ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  🌐 前端界面: http://localhost:$FRONTEND_PORT                      ${NC}"
echo -e "${GREEN}║  🔌 后端 API:  http://localhost:$BACKEND_PORT/api/v1               ${NC}"
echo -e "${GREEN}║  📚 API 文档:  http://localhost:$BACKEND_PORT/docs                 ${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo
echo -e "${CYAN}使用说明：${NC}"
echo "  1. 打开浏览器访问 http://localhost:$FRONTEND_PORT"
echo "  2. 选择论文模板（NeurIPS / ACM / IEEE / Springer / CUMCM）"
echo "  3. 输入研究题目或问题描述"
echo "  4. 点击提交，系统自动完成：分析→建模→求解→实验→论文→评议"
echo "  5. 在「PDF」Tab 下载 Camera-Ready 投稿包"
echo
echo -e "${YELLOW}按 Ctrl+C 停止所有服务${NC}"
echo

# 等待进程
wait $BACKEND_PID $FRONTEND_PID
