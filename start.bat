@echo off
REM 数学建模多Agent系统 - 一键启动脚本（Windows）
REM 用法：双击 start.bat 或在命令行执行
REM 功能：检测环境、创建虚拟环境、安装前后端依赖、启动服务

cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ========================================
echo   多智能体协作论文生产系统 启动器
echo ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 Python。请先安装 Python 3.9+ ^(https://www.python.org/^)
    pause
    exit /b 1
)
for /f "tokens=2 delims=. " %%a in ('python --version 2^>^&1') do set PY_MAJOR=%%a
for /f "tokens=3 delims=. " %%a in ('python --version 2^>^&1') do set PY_MINOR=%%a
if %PY_MAJOR% LSS 3 (
    echo [ERROR] Python 版本过低，需要 3.9+。当前：%PY_MAJOR%.%PY_MINOR%
    pause
    exit /b 1
)
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 9 (
    echo [ERROR] Python 版本过低，需要 3.9+。当前：%PY_MAJOR%.%PY_MINOR%
    pause
    exit /b 1
)
echo [OK] Python %PY_MAJOR%.%PY_MINOR%

REM 检查 Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 Node.js。请先安装 Node.js 18+ ^(https://nodejs.org/^)
    pause
    exit /b 1
)
for /f "tokens=1 delims=v. " %%a in ('node --version 2^>^&1') do set NODE_MAJOR=%%a
if %NODE_MAJOR% LSS 18 (
    echo [ERROR] Node.js 版本过低，需要 18+。当前：%NODE_MAJOR%
    pause
    exit /b 1
)
echo [OK] Node.js %NODE_MAJOR%

REM 创建虚拟环境
if not exist ".venv" (
    echo [INFO] 创建 Python 虚拟环境 .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] 创建虚拟环境失败
        pause
        exit /b 1
    )
)

REM 安装后端依赖
echo [1/4] 检查并安装后端依赖...
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
python -m pip install -q -r backend\requirements.txt
if errorlevel 1 (
    echo [ERROR] 后端依赖安装失败
    pause
    exit /b 1
)

REM 安装前端依赖
echo [2/4] 检查并安装前端依赖...
cd frontend
if not exist "node_modules" (
    echo [INFO] 首次安装前端依赖，可能需要几分钟...
    npm install
) else (
    echo [INFO] 前端依赖已安装，跳过
)
cd ..

REM 创建必要目录
echo [3/4] 创建必要目录...
if not exist "data\uploads" mkdir "data\uploads"
if not exist "data\tasks" mkdir "data\tasks"
if not exist "data\knowledge_files" mkdir "data\knowledge_files"
if not exist "data\memory" mkdir "data\memory"

REM 检查 .env
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [WARN] 已从 .env.example 创建 .env，请编辑填写你的 LLM API Key
    ) else (
        echo [WARN] 未找到 .env.example，请手动创建 .env 并配置 API Key
    )
)

REM 启动服务
echo [4/4] 启动服务...
echo.
echo 访问地址：
echo   - 前端：http://localhost:3000
echo   - 后端 API：http://localhost:8000/api/v1
echo   - API 文档：http://localhost:8000/docs
echo.
echo 按 Ctrl+C 或在对应窗口关闭服务
echo.

start "Backend" cmd /k "cd /d %CD% && call .venv\Scripts\activate.bat && cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 2 >nul
start "Frontend" cmd /k "cd /d %CD%\frontend && npm run dev"

endlocal
