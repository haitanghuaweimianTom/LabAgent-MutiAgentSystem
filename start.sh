#!/usr/bin/env bash
# 数学建模多Agent系统 - 一键启动脚本（Linux / macOS）
# 用法：./start.sh
# 功能：检测环境、创建conda/venv环境、安装前后端依赖、build前端、启动服务
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
    echo -e "${CYAN}║  版本: v5.4.0 | 全自动论文产线 | 数据驱动+知识库+RAG            ║${NC}"
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
print_step "[1/8] 检查 Python 环境..."
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
print_step "[2/8] 检查 Node.js 环境..."
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

# ===== 3. 选择 Python 环境（conda / venv） =====
print_step "[3/8] 配置 Python 环境..."

USE_CONDA=false
CONDA_ENV_NAME=""

# 检测 conda 是否可用
if command -v conda >/dev/null 2>&1; then
    print_info "检测到 conda，可用环境："
    echo
    conda env list 2>/dev/null | grep -v "^#" | grep -v "^$" | awk '{print "  " $1}' | head -20
    echo

    # 读取上次使用的环境名（如果有缓存）
    CACHE_FILE="$PROJECT_ROOT/.conda_env_cache"
    LAST_ENV=""
    if [ -f "$CACHE_FILE" ]; then
        LAST_ENV=$(cat "$CACHE_FILE")
    fi

    if [ -n "$LAST_ENV" ]; then
        echo -e "  上次使用的环境: ${CYAN}$LAST_ENV${NC}"
        read -p "  按 Enter 使用上次环境，或输入新的环境名: " INPUT_ENV </dev/tty
        CONDA_ENV_NAME="${INPUT_ENV:-$LAST_ENV}"
    else
        read -p "  请输入 conda 环境名（直接回车则使用 venv）: " CONDA_ENV_NAME </dev/tty
    fi

    if [ -n "$CONDA_ENV_NAME" ]; then
        # 检查环境是否存在
        if conda env list 2>/dev/null | grep -q "^${CONDA_ENV_NAME} "; then
            print_info "激活已有 conda 环境: $CONDA_ENV_NAME"
            eval "$(conda shell.bash hook 2>/dev/null)"
            conda activate "$CONDA_ENV_NAME"
            USE_CONDA=true
            echo "$CONDA_ENV_NAME" > "$CACHE_FILE"
            print_ok "conda 环境 $CONDA_ENV_NAME 已激活"
        else
            echo -e "  conda 环境 ${YELLOW}$CONDA_ENV_NAME${NC} 不存在。"
            read -p "  是否创建该环境？(Y/n): " CREATE_ENV </dev/tty
            CREATE_ENV="${CREATE_ENV:-Y}"
            if [[ "$CREATE_ENV" =~ ^[Yy]$ ]]; then
                print_info "创建 conda 环境: $CONDA_ENV_NAME（Python 3.11）..."
                conda create -n "$CONDA_ENV_NAME" python=3.11 -y
                eval "$(conda shell.bash hook 2>/dev/null)"
                conda activate "$CONDA_ENV_NAME"
                USE_CONDA=true
                echo "$CONDA_ENV_NAME" > "$CACHE_FILE"
                print_ok "conda 环境 $CONDA_ENV_NAME 创建并激活成功"
            else
                print_warn "跳过 conda，将使用 venv"
            fi
        fi
    fi
else
    print_info "未检测到 conda，将使用 venv"
fi

# 如果不用 conda，使用 venv
if [ "$USE_CONDA" = false ]; then
    if [ ! -d ".venv" ]; then
        print_info "创建 Python 虚拟环境 .venv..."
        $PYTHON_CMD -m venv .venv
        print_ok "虚拟环境创建完成"
    else
        print_ok "虚拟环境已存在"
    fi
    source .venv/bin/activate
fi

# ===== 4. 安装后端依赖（自动检测并安装缺失包） =====
print_step "[4/8] 安装后端依赖..."

python -m pip install -q --upgrade pip 2>/dev/null || true

if [ ! -f "backend/requirements.txt" ]; then
    print_error "未找到 backend/requirements.txt"
    exit 1
fi

# 检查是否需要重新安装
REQ_HASH=$(md5sum backend/requirements.txt 2>/dev/null | awk '{print $1}')
if [ "$USE_CONDA" = true ]; then
    HASH_FILE="$PROJECT_ROOT/.conda_${CONDA_ENV_NAME}_req_hash"
else
    HASH_FILE=".venv/.req_hash"
fi
INSTALLED_HASH=""
if [ -f "$HASH_FILE" ]; then
    INSTALLED_HASH=$(cat "$HASH_FILE")
fi

if [ "$REQ_HASH" != "$INSTALLED_HASH" ]; then
    print_info "安装/更新后端依赖..."
    python -m pip install -q -r backend/requirements.txt || {
        print_warn "部分依赖安装失败，尝试逐个安装..."
        while IFS= read -r line; do
            [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
            pkg=$(echo "$line" | sed 's/[>=<].*//')
            python -m pip install -q "$line" 2>/dev/null || print_warn "跳过: $pkg"
        done < backend/requirements.txt
    }
    echo "$REQ_HASH" > "$HASH_FILE"
    print_ok "后端依赖安装完成"
else
    print_ok "后端依赖已是最新"
fi

# 运行时自动检测并安装缺失包
print_info "验证关键依赖..."
python -c "
import importlib, sys
pkgs = ['fastapi', 'uvicorn', 'pydantic', 'httpx', 'langgraph', 'langchain_core',
        'sentence_transformers', 'sklearn', 'pandas', 'pymupdf4llm', 'mcp']
missing = []
for p in pkgs:
    try: importlib.import_module(p)
    except ImportError: missing.append(p)
if missing:
    print(f'  缺失: {missing}', file=sys.stderr)
    sys.exit(1)
print('  所有关键依赖已就绪')
" 2>/dev/null || {
    print_warn "检测到缺失依赖，自动安装..."
    python -m pip install -q -r backend/requirements.txt
    print_ok "缺失依赖已补装"
}

# ===== 5. 检查端口 & 停止已运行服务 =====
print_step "[5/8] 检查端口 & 停止旧服务..."
BACKEND_PORT=8000
FRONTEND_PORT=3000

# 检测并停止后端
PIDS=$(pgrep -f "uvicorn app.main:app" || true)
if [ -n "$PIDS" ]; then
    print_info "停止旧后端: $PIDS"
    kill -TERM $PIDS 2>/dev/null || true
    sleep 2
    REMAINING=$(pgrep -f "uvicorn app.main:app" || true)
    [ -n "$REMAINING" ] && kill -KILL $REMAINING 2>/dev/null || true
    [ -n "$REMAINING" ] && sleep 1
    if command -v fuser >/dev/null 2>&1; then
        fuser -k ${BACKEND_PORT}/tcp 2>/dev/null || true
    fi
    print_ok "旧后端已停止"
fi

# 检测并停止前端
NEXT_PIDS=$(pgrep -f "next-server" || pgrep -f "next start" || true)
if [ -n "$NEXT_PIDS" ]; then
    print_info "停止旧前端: $NEXT_PIDS"
    kill -TERM $NEXT_PIDS 2>/dev/null || true
    sleep 1
    REMAINING=$(pgrep -f "next-server" || pgrep -f "next start" || true)
    [ -n "$REMAINING" ] && kill -KILL $REMAINING 2>/dev/null || true
    print_ok "旧前端已停止"
fi

# ===== 6. 安装前端依赖 & Build =====
print_step "[6/8] 准备前端环境..."
cd frontend

if [ ! -f "package.json" ]; then
    print_error "未找到 frontend/package.json"
    exit 1
fi

PKG_HASH=$(md5sum package.json 2>/dev/null | awk '{print $1}')
INSTALLED_PKG_HASH=""
[ -f "node_modules/.pkg_hash" ] && INSTALLED_PKG_HASH=$(cat node_modules/.pkg_hash)

if [ ! -d "node_modules" ] || [ "$PKG_HASH" != "$INSTALLED_PKG_HASH" ]; then
    print_info "安装前端依赖..."
    npm install
    echo "$PKG_HASH" > node_modules/.pkg_hash
    print_ok "前端依赖安装完成"
else
    print_ok "前端依赖已是最新"
fi

NEED_BUILD=false
[ ! -d ".next" ] && NEED_BUILD=true
[ ! -f ".next/BUILD_ID" ] && NEED_BUILD=true
if [ "$NEED_BUILD" = false ]; then
    SRC_NEWER=$(find . -path ./node_modules -prune -o -path ./.next -prune -o -type f -newer .next/BUILD_ID -print -quit 2>/dev/null || true)
    [ -n "$SRC_NEWER" ] && NEED_BUILD=true
fi

if [ "$NEED_BUILD" = true ]; then
    print_info "构建前端..."
    npm run build
    print_ok "前端构建完成"
else
    print_ok "前端构建已是最新"
fi

cd "$PROJECT_ROOT"

# ===== 7. 创建必要目录 =====
print_step "[7/8] 创建必要目录..."
mkdir -p data/uploads data/tasks data/knowledge_files data/memory data/venvs \
         data/checkpoints data/langgraph_results outputs reading global_references
print_ok "目录结构已就绪"

# ===== 8. 检查环境配置 =====
print_step "[8/8] 检查环境配置..."

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp ".env.example" ".env"
    print_warn ".env 已自动创建"
fi

if [ ! -f "backend/.env" ]; then
    if [ -f "backend/.env.example" ]; then
        cp "backend/.env.example" "backend/.env"
    elif [ -f ".env" ]; then
        cp ".env" "backend/.env"
    fi
fi

ENV_CONFIGURED=false
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
    echo "  启动后请访问 http://localhost:$FRONTEND_PORT → 设置 → 添加 Provider"
    echo
    read -p "按 Enter 继续启动..." </dev/tty
fi

# ===== 启动服务 =====
echo
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  🚀 服务启动中...                                                ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo

cleanup() {
    echo
    print_info "正在停止服务..."
    [ -n "${BACKEND_PID:-}" ] && kill "$BACKEND_PID" 2>/dev/null && wait "$BACKEND_PID" 2>/dev/null
    [ -n "${FRONTEND_PID:-}" ] && kill "$FRONTEND_PID" 2>/dev/null && wait "$FRONTEND_PID" 2>/dev/null
    print_ok "服务已停止"
    exit 0
}
trap cleanup INT TERM EXIT

# 启动后端
print_info "启动后端（端口 $BACKEND_PORT）..."
cd backend
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --no-access-log > /tmp/backend.log 2>&1 &
BACKEND_PID=$!
cd "$PROJECT_ROOT"

print_info "等待后端就绪..."
for i in $(seq 1 30); do
    sleep 0.5
    if curl -sS --max-time 1 "http://localhost:${BACKEND_PORT}/api/v1/info" >/dev/null 2>&1; then
        print_ok "后端启动成功 (PID=$BACKEND_PID)"
        break
    fi
    [ "$i" -eq 30 ] && { print_error "后端启动超时"; tail -20 /tmp/backend.log; exit 1; }
done

# 启动前端
print_info "启动前端（端口 $FRONTEND_PORT）..."
cd frontend
npm run start -- --port $FRONTEND_PORT > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!
cd "$PROJECT_ROOT"

print_info "等待前端就绪..."
for i in $(seq 1 30); do
    sleep 0.5
    if curl -sS --max-time 1 "http://localhost:${FRONTEND_PORT}" >/dev/null 2>&1; then
        print_ok "前端启动成功 (PID=$FRONTEND_PID)"
        break
    fi
    [ "$i" -eq 30 ] && print_warn "前端可能仍在启动中..."
done

# 完成提示
echo
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✅ 服务启动完成！                                                ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  🌐 前端界面: http://localhost:$FRONTEND_PORT                      ${NC}"
echo -e "${GREEN}║  🔌 后端 API:  http://localhost:$BACKEND_PORT/api/v1               ${NC}"
echo -e "${GREEN}║  📚 API 文档:  http://localhost:$BACKEND_PORT/docs                 ${NC}"
[ "$USE_CONDA" = true ] && echo -e "${GREEN}║  🐍 Conda 环境: $CONDA_ENV_NAME                                     ${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo
echo -e "${YELLOW}按 Ctrl+C 停止所有服务${NC}"
echo

wait $BACKEND_PID $FRONTEND_PID
