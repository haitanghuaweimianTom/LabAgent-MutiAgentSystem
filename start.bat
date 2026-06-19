@echo off
REM 数学建模多Agent系统 - 一键启动脚本（Windows）
REM 用法：双击 start.bat 或在命令行执行
REM 功能：检测环境、创建虚拟环境、安装前后端依赖、启动服务
REM 设计原则：对无技术基础用户友好，每一步都有明确提示和自动修复

cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ========================================
echo   多智能体协作论文生产系统 启动器
echo   版本: v3.1 ^| 全自动论文产线
echo ========================================
echo.

REM ===== 1. 检查 Python =====
echo [INFO] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 Python。请先安装 Python 3.9+
    echo   访问: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2 delims=. " %%a in ('python --version 2>^&1') do set PY_MAJOR=%%a
for /f "tokens=3 delims=. " %%a in ('python --version 2>^&1') do set PY_MINOR=%%a
if %PY_MAJOR% LSS 3 (
    echo [ERROR] Python 版本过低，需要 3.9+。当前: %PY_MAJOR%.%PY_MINOR%
    pause
    exit /b 1
)
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 9 (
    echo [ERROR] Python 版本过低，需要 3.9+。当前: %PY_MAJOR%.%PY_MINOR%
    pause
    exit /b 1
)
echo [OK] Python %PY_MAJOR%.%PY_MINOR%

REM ===== 2. 检查 Node.js =====
echo [INFO] 检查 Node.js 环境...
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 Node.js。请先安装 Node.js 18+
    echo   访问: https://nodejs.org/
    pause
    exit /b 1
)
for /f "tokens=1 delims=v. " %%a in ('node --version 2>^&1') do set NODE_MAJOR=%%a
if %NODE_MAJOR% LSS 18 (
    echo [ERROR] Node.js 版本过低，需要 18+。当前: %NODE_MAJOR%
    pause
    exit /b 1
)
echo [OK] Node.js %NODE_MAJOR%

REM ===== 3. 检查 npm =====
echo [INFO] 检查 npm...
npm --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 npm。请重新安装 Node.js（npm 通常随 Node.js 一起安装）
    pause
    exit /b 1
)
echo [OK] npm

REM ===== 4. 检查端口占用 =====
echo [INFO] 检查端口占用...
set BACKEND_PORT=8000
set FRONTEND_PORT=3000

REM 检查端口 8000
:check_backend_port
netstat -ano | findstr ":%BACKEND_PORT%" >nul 2>&1
if not errorlevel 1 (
    set /a BACKEND_PORT+=1
    goto check_backend_port
)

REM 检查端口 3000
:check_frontend_port
netstat -ano | findstr ":%FRONTEND_PORT%" >nul 2>&1
if not errorlevel 1 (
    set /a FRONTEND_PORT+=1
    goto check_frontend_port
)

if not "%BACKEND_PORT%"=="8000" (
    echo [WARN] 端口 8000 被占用，后端将使用端口 %BACKEND_PORT%
)
if not "%FRONTEND_PORT%"=="3000" (
    echo [WARN] 端口 3000 被占用，前端将使用端口 %FRONTEND_PORT%
)

REM ===== 5. 创建虚拟环境 =====
if not exist ".venv" (
    echo [INFO] 创建 Python 虚拟环境 .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo [OK] 虚拟环境创建完成
) else (
    echo [OK] 虚拟环境已存在
)

REM ===== 6. 安装后端依赖 =====
echo [1/5] 检查并安装后端依赖...
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
python -m pip install -q -r backend\requirements.txt
if errorlevel 1 (
    echo [ERROR] 后端依赖安装失败
    pause
    exit /b 1
)
echo [OK] 后端依赖已就绪

REM ===== 7. 安装前端依赖 =====
echo [2/5] 检查并安装前端依赖...
cd frontend
if not exist "node_modules" (
    echo [INFO] 首次安装前端依赖，可能需要 2-3 分钟...
    npm install
    if errorlevel 1 (
        echo [ERROR] 前端依赖安装失败
        pause
        exit /b 1
    )
    echo [OK] 前端依赖安装完成
) else (
    echo [OK] 前端依赖已安装
)
cd ..

REM ===== 8. 创建必要目录 =====
echo [3/5] 创建必要目录...
if not exist "data\uploads" mkdir "data\uploads"
if not exist "data\tasks" mkdir "data\tasks"
if not exist "data\knowledge_files" mkdir "data\knowledge_files"
if not exist "data\memory" mkdir "data\memory"
if not exist "data\venvs" mkdir "data\venvs"
if not exist "data\checkpoints" mkdir "data\checkpoints"
if not exist "data\langgraph_results" mkdir "data\langgraph_results"
echo [OK] 目录结构已就绪

REM ===== 9. 检查环境配置 =====
echo [4/5] 检查环境配置...

REM 创建 .env（如果不存在）
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [WARN] .env 已自动创建（从 .env.example 复制）
    ) else (
        echo [WARN] .env 和 .env.example 都不存在，将使用默认配置
    )
)

REM 创建 backend/.env（如果不存在）
if not exist "backend\.env" (
    if exist "backend\.env.example" (
        copy "backend\.env.example" "backend\.env" >nul
        echo [OK] backend\.env 已自动创建
    ) else if exist ".env" (
        copy ".env" "backend\.env" >nul
        echo [OK] backend\.env 已自动创建（从 .env 复制）
    )
)

REM 检查 API Key 配置
set ENV_CONFIGURED=false
if exist ".env" (
    findstr /R "API_KEY=sk- API_KEY=AK- OPENAI_API_KEY=sk- ANTHROPIC_API_KEY=sk-" .env >nul 2>&1
    if not errorlevel 1 (
        set ENV_CONFIGURED=true
        echo [OK] 已检测到 API Key 配置
    ) else (
        findstr /R "your_api_key_here YOUR_API_KEY placeholder changeme" .env >nul 2>&1
        if not errorlevel 1 (
            echo [WARN] .env 中存在未修改的占位符 API Key
        )
    )
)

REM 检查 custom_providers.json
if exist "backend\custom_providers.json" (
    python -c "import json; data=json.load(open('backend/custom_providers.json')); print(len(data.get('providers', [])))" > .provider_count.tmp 2>nul
    if not errorlevel 1 (
        set /p PROVIDER_COUNT=<.provider_count.tmp
        del .provider_count.tmp 2>nul
        if %PROVIDER_COUNT% GTR 0 (
            echo [OK] 已配置 %PROVIDER_COUNT% 个 LLM Provider
            set ENV_CONFIGURED=true
        )
    )
)

if "%ENV_CONFIGURED%"=="false" (
    echo.
    echo [WARN] 尚未配置 LLM API Key！
    echo.
    echo 系统需要至少一个 LLM Provider 才能运行。请按以下步骤配置：
    echo.
    echo 方法 1（推荐）: 通过前端设置界面
    echo   1. 启动后访问 http://localhost:%FRONTEND_PORT%
    echo   2. 点击「设置」Tab -^> 添加 Provider
    echo   3. 选择你的 Provider（OpenAI / Anthropic / 阿里百炼 / 硅基流动 / DeepSeek 等）
    echo   4. 填写 API Key 和模型名称
    echo.
    echo 方法 2: 手动编辑 .env
    echo   编辑 .env 文件，填写你的 API Key:
    echo     API_KEY=sk-...
    echo     或 OPENAI_API_KEY=sk-...
    echo     或 ANTHROPIC_API_KEY=sk-...
    echo.
    echo 支持的 Provider: OpenAI, Anthropic, 阿里百炼, 硅基流动, 智谱, DeepSeek, Ollama, OpenRouter...
    echo.
    pause
)

REM ===== 10. 启动服务 =====
echo [5/5] 启动服务...
echo.
echo ========================================
echo   服务启动完成！访问地址：
echo   - 前端界面: http://localhost:%FRONTEND_PORT%
echo   - 后端 API: http://localhost:%BACKEND_PORT%/api/v1
echo   - API 文档: http://localhost:%BACKEND_PORT%/docs
echo ========================================
echo.
echo 使用说明：
echo   1. 打开 http://localhost:%FRONTEND_PORT%
echo   2. 选择论文模板（NeurIPS / ACM / IEEE / Springer / CUMCM）
echo   3. 输入研究题目或问题描述
echo   4. 点击提交，系统自动完成：分析→建模→求解→实验→论文→评议
echo   5. 在「PDF」Tab 下载 Camera-Ready 投稿包
echo.
echo 关闭此窗口即可停止服务
echo.

REM 保存端口配置
echo { > .ports.json
echo   "backend_port": %BACKEND_PORT%, >> .ports.json
echo   "frontend_port": %FRONTEND_PORT% >> .ports.json
echo } >> .ports.json

REM 启动后端（在新窗口中，方便用户查看日志）
start "Backend Server" cmd /k "cd /d %CD% && call .venv\Scripts\activate.bat && cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload"

REM 等待后端启动
timeout /t 3 /nobreak >nul

REM 启动前端（在新窗口中）
start "Frontend Server" cmd /k "cd /d %CD%\frontend && npm run dev -- --port %FRONTEND_PORT%"

REM 等待用户按任意键停止
echo.
echo 按任意键停止所有服务...
pause >nul

REM 停止服务
echo.
echo [INFO] 正在停止服务...
taskkill /FI "WINDOWTITLE eq Backend Server" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Frontend Server" /F >nul 2>&1
del .ports.json 2>nul
echo [OK] 服务已停止

endlocal
