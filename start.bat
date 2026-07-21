@echo off
REM 数学建模多Agent系统 - 一键启动脚本（Windows）
REM 用法：双击 start.bat 或在命令行执行
REM 功能：检测环境、创建conda/venv环境、安装前后端依赖、build前端、启动服务
REM 设计原则：对无技术基础用户友好，双击即可运行，一切自动化

cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ╔══════════════════════════════════════════════════════════════════╗
echo ║  多智能体协作论文生产系统 启动器                                  ║
echo ║  版本: v8.2.0 | 全自动论文产线 | 数据驱动+知识库+RAG            ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.

REM ===== 1. 检查 Python =====
echo ▶ [1/8] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 Python。请先安装 Python 3.9+
    echo   访问: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2 delims=. " %%a in ('python --version 2^>^&1') do set PY_MAJOR=%%a
for /f "tokens=3 delims=. " %%a in ('python --version 2^>^&1') do set PY_MINOR=%%a
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
echo ▶ [2/8] 检查 Node.js 环境...
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 Node.js。请先安装 Node.js 18+
    echo   访问: https://nodejs.org/
    pause
    exit /b 1
)
for /f "tokens=1 delims=v. " %%a in ('node --version 2^>^&1') do set NODE_MAJOR=%%a
if %NODE_MAJOR% LSS 18 (
    echo [ERROR] Node.js 版本过低，需要 18+。当前: %NODE_MAJOR%
    pause
    exit /b 1
)
echo [OK] Node.js %NODE_MAJOR%

npm --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 npm。请重新安装 Node.js
    pause
    exit /b 1
)
echo [OK] npm

REM ===== 3. 选择 Python 环境（conda / venv） =====
echo ▶ [3/8] 配置 Python 环境...

set USE_CONDA=false
set CONDA_ENV_NAME=

REM 检测 conda 是否可用
conda --version >nul 2>&1
if not errorlevel 1 (
    echo 检测到 conda，可用环境：
    conda env list 2>nul | findstr /V "#" | findstr /V "^$"
    echo.

    REM 读取缓存的环境名
    set CACHE_FILE=.conda_env_cache
    set LAST_ENV=
    if exist "!CACHE_FILE!" (
        set /p LAST_ENV=<"!CACHE_FILE!"
    )

    if not "!LAST_ENV!"=="" (
        echo   上次使用的环境: !LAST_ENV!
        set /p INPUT_ENV="  按 Enter 使用上次环境，或输入新的环境名: "
        if "!INPUT_ENV!"=="" (
            set CONDA_ENV_NAME=!LAST_ENV!
        ) else (
            set CONDA_ENV_NAME=!INPUT_ENV!
        )
    ) else (
        set /p CONDA_ENV_NAME="  请输入 conda 环境名（直接回车则使用 venv）: "
    )

    if not "!CONDA_ENV_NAME!"=="" (
        REM 检查环境是否存在
        conda env list 2>nul | findstr /C:"!CONDA_ENV_NAME!" >nul
        if not errorlevel 1 (
            echo [INFO] 激活已有 conda 环境: !CONDA_ENV_NAME!
            call conda activate !CONDA_ENV_NAME!
            set USE_CONDA=true
            echo !CONDA_ENV_NAME! > "!CACHE_FILE!"
            echo [OK] conda 环境 !CONDA_ENV_NAME! 已激活
        ) else (
            echo   conda 环境 !CONDA_ENV_NAME! 不存在。
            set /p CREATE_ENV="  是否创建该环境？(Y/n): "
            if "!CREATE_ENV!"=="" set CREATE_ENV=Y
            if /I "!CREATE_ENV!"=="Y" (
                echo [INFO] 创建 conda 环境: !CONDA_ENV_NAME!（Python 3.11）...
                conda create -n !CONDA_ENV_NAME! python=3.11 -y
                call conda activate !CONDA_ENV_NAME!
                set USE_CONDA=true
                echo !CONDA_ENV_NAME! > "!CACHE_FILE!"
                echo [OK] conda 环境 !CONDA_ENV_NAME! 创建并激活成功
            ) else (
                echo [WARN] 跳过 conda，将使用 venv
            )
        )
    )
) else (
    echo [INFO] 未检测到 conda，将使用 venv
)

REM 如果不用 conda，使用 venv
if "!USE_CONDA!"=="false" (
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
    call .venv\Scripts\activate.bat
)

REM ===== 4. 安装后端依赖 =====
echo ▶ [4/8] 安装后端依赖...

python -m pip install -q --upgrade pip 2>nul

if not exist "backend\requirements.txt" (
    echo [ERROR] 未找到 backend\requirements.txt
    pause
    exit /b 1
)

REM 检查是否需要重新安装
python -c "import hashlib; print(hashlib.md5(open('backend/requirements.txt','rb').read()).hexdigest())" > .req_hash.tmp 2>nul
set /p REQ_HASH=<.req_hash.tmp
del .req_hash.tmp 2>nul

if "!USE_CONDA!"=="true" (
    set HASH_FILE=.conda_!CONDA_ENV_NAME!_req_hash
) else (
    set HASH_FILE=.venv\.req_hash
)

set INSTALLED_HASH=
if exist "!HASH_FILE!" (
    set /p INSTALLED_HASH=<"!HASH_FILE!"
)

if not "!REQ_HASH!"=="!INSTALLED_HASH!" (
    echo [INFO] 安装/更新后端依赖...
    python -m pip install -q -r backend\requirements.txt
    if errorlevel 1 (
        echo [WARN] 部分依赖安装失败，尝试逐个安装...
        for /f "usebackq tokens=*" %%l in ("backend\requirements.txt") do (
            set line=%%l
            if not "!line:~0,1!"=="#" if not "!line!"=="" (
                python -m pip install -q "!line!" 2>nul || echo [WARN] 跳过: !line!
            )
        )
    )
    echo !REQ_HASH! > "!HASH_FILE!"
    echo [OK] 后端依赖安装完成
) else (
    echo [OK] 后端依赖已是最新
)

REM 运行时验证关键依赖
echo [INFO] 验证关键依赖...
python -c "import importlib; [importlib.import_module(p) for p in ['fastapi','uvicorn','pydantic','httpx','langgraph']]" 2>nul
if errorlevel 1 (
    echo [WARN] 检测到缺失依赖，自动安装...
    python -m pip install -q -r backend\requirements.txt
    echo [OK] 缺失依赖已补装
)

REM ===== 5. 检查端口 & 停止旧服务 =====
echo ▶ [5/8] 检查端口 ^& 停止旧服务...
set BACKEND_PORT=8001
set FRONTEND_PORT=3000

REM 停止后端
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT%" ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1

REM 停止前端
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT%" ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1

echo [OK] 已清理旧服务

REM ===== 6. 安装前端依赖 ^& Build =====
echo ▶ [6/8] 准备前端环境...
cd frontend

if not exist "package.json" (
    echo [ERROR] 未找到 frontend\package.json
    pause
    exit /b 1
)

python -c "import hashlib; print(hashlib.md5(open('package.json','rb').read()).hexdigest())" > .pkg_hash.tmp 2>nul
set /p PKG_HASH=<.pkg_hash.tmp
del .pkg_hash.tmp 2>nul

set INSTALLED_PKG_HASH=
if exist "node_modules\.pkg_hash" (
    set /p INSTALLED_PKG_HASH=<node_modules\.pkg_hash
)

if not exist "node_modules" (
    echo [INFO] 首次安装前端依赖...
    npm install
    if errorlevel 1 (
        echo [ERROR] 前端依赖安装失败
        pause
        exit /b 1
    )
    echo %PKG_HASH% > node_modules\.pkg_hash
    echo [OK] 前端依赖安装完成
) else if not "%PKG_HASH%"=="%INSTALLED_PKG_HASH%" (
    echo [INFO] package.json 已更新，重新安装前端依赖...
    npm install
    if errorlevel 1 (
        echo [ERROR] 前端依赖安装失败
        pause
        exit /b 1
    )
    echo %PKG_HASH% > node_modules\.pkg_hash
    echo [OK] 前端依赖更新完成
) else (
    echo [OK] 前端依赖已是最新
)

set NEED_BUILD=false
if not exist ".next" set NEED_BUILD=true
if not exist ".next\BUILD_ID" set NEED_BUILD=true

if "%NEED_BUILD%"=="true" (
    echo [INFO] 构建前端...
    npm run build
    if errorlevel 1 (
        echo [ERROR] 前端构建失败
        pause
        exit /b 1
    )
    echo [OK] 前端构建完成
) else (
    echo [OK] 前端构建已是最新
)

cd ..

REM ===== 7. 创建必要目录 =====
echo ▶ [7/8] 创建必要目录...
if not exist "data\uploads" mkdir "data\uploads"
if not exist "data\tasks" mkdir "data\tasks"
if not exist "data\knowledge_files" mkdir "data\knowledge_files"
if not exist "data\memory" mkdir "data\memory"
if not exist "data\venvs" mkdir "data\venvs"
if not exist "data\checkpoints" mkdir "data\checkpoints"
if not exist "data\langgraph_results" mkdir "data\langgraph_results"
if not exist "outputs" mkdir "outputs"
if not exist "reading" mkdir "reading"
if not exist "global_references" mkdir "global_references"
echo [OK] 目录结构已就绪

REM ===== 8. 检查环境配置 =====
echo ▶ [8/8] 检查环境配置...

if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" .env >nul
        echo [WARN] .env 已自动创建
    )
)

if not exist "backend\.env" (
    if exist "backend\.env.example" (
        copy "backend\.env.example" "backend\.env" >nul
    ) else if exist ".env" (
        copy ".env" "backend\.env" >nul
    )
)

set ENV_CONFIGURED=false
if exist "backend\custom_providers.json" (
    python -c "import json; data=json.load(open('backend/custom_providers.json')); print(len(data.get('providers', [])))" > .provider_count.tmp 2>nul
    if not errorlevel 1 (
        set /p PROVIDER_COUNT=<.provider_count.tmp
        del .provider_count.tmp 2>nul
        if !PROVIDER_COUNT! GTR 0 (
            echo [OK] 已配置 !PROVIDER_COUNT! 个 LLM Provider
            set ENV_CONFIGURED=true
        )
    )
)

if "!ENV_CONFIGURED!"=="false" (
    echo.
    echo [WARN] 尚未配置 LLM API Key！
    echo   启动后请访问 http://localhost:%FRONTEND_PORT% - 设置 - 添加 Provider
    echo.
    pause
)

REM ===== 启动服务 =====
echo.
echo ╔══════════════════════════════════════════════════════════════════╗
echo ║  服务启动中...                                                    ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.

REM 启动后端
echo [INFO] 启动后端（端口 %BACKEND_PORT%）...
start "Backend Server" cmd /k "cd /d %CD% && if "!USE_CONDA!"=="true" (call conda activate !CONDA_ENV_NAME!) else (call .venv\Scripts\activate.bat) && cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --no-access-log"

timeout /t 4 /nobreak >nul

set BACKEND_READY=false
for /l %%i in (1,1,10) do (
    curl -sS --max-time 1 "http://localhost:%BACKEND_PORT%/api/v1/info" >nul 2>&1
    if not errorlevel 1 (
        set BACKEND_READY=true
        echo [OK] 后端启动成功（端口 %BACKEND_PORT%）
        goto backend_ready
    )
    timeout /t 1 /nobreak >nul
)
:backend_ready
if "%BACKEND_READY%"=="false" echo [WARN] 后端启动可能仍在进行中...

REM 启动前端
echo [INFO] 启动前端（端口 %FRONTEND_PORT%）...
start "Frontend Server" cmd /k "cd /d %CD%\frontend && npm run start -- --port %FRONTEND_PORT%"

timeout /t 3 /nobreak >nul

set FRONTEND_READY=false
for /l %%i in (1,1,10) do (
    curl -sS --max-time 1 "http://localhost:%FRONTEND_PORT%" >nul 2>&1
    if not errorlevel 1 (
        set FRONTEND_READY=true
        echo [OK] 前端启动成功（端口 %FRONTEND_PORT%）
        goto frontend_ready
    )
    timeout /t 1 /nobreak >nul
)
:frontend_ready
if "%FRONTEND_READY%"=="false" echo [WARN] 前端可能仍在启动中...

REM 完成提示
echo.
echo ╔══════════════════════════════════════════════════════════════════╗
echo ║  ✅ 服务启动完成！                                                ║
echo ╠══════════════════════════════════════════════════════════════════╣
echo ║  前端界面: http://localhost:%FRONTEND_PORT%                      ║
echo ║  后端 API: http://localhost:%BACKEND_PORT%/api/v1                ║
echo ║  API 文档: http://localhost:%BACKEND_PORT%/docs                  ║
if "!USE_CONDA!"=="true" echo ║  Conda 环境: !CONDA_ENV_NAME!                                     ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.
echo 按任意键停止所有服务...
pause >nul

REM 停止服务
echo.
echo [INFO] 正在停止服务...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT%" ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT%" ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
echo [OK] 服务已停止

endlocal
