@echo off
REM 数学建模多Agent系统 - 一键启动脚本（Windows）
REM 用法：双击 start.bat 或在命令行执行
REM 功能：检测环境、创建虚拟环境、安装前后端依赖、build前端、检测/重启前后端、启动服务
REM 设计原则：对无技术基础用户友好，双击即可运行，一切自动化

cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ╔══════════════════════════════════════════════════════════════════╗
echo ║  多智能体协作论文生产系统 启动器                                  ║
echo ║  版本: v5.3.0 | 全自动论文产线 | 数据驱动+知识库+RAG            ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.

REM ===== 1. 检查 Python =====
echo ▶ [1/7] 检查 Python 环境...
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
echo ▶ [2/7] 检查 Node.js 环境...
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

REM ===== 3. 检查端口 & 检测已运行服务 =====
echo ▶ [3/7] 检查端口占用 & 检测已运行服务...
set BACKEND_PORT=8000
set FRONTEND_PORT=3000
set BACKEND_RUNNING=false
set FRONTEND_RUNNING=false

REM 检测后端是否已运行
curl -sS --max-time 1 "http://localhost:%BACKEND_PORT%/api/v1/info" >nul 2>&1
if not errorlevel 1 (
    echo [WARN] 后端已在端口 %BACKEND_PORT% 运行
    set BACKEND_RUNNING=true
)

REM 检测前端是否已运行
curl -sS --max-time 1 "http://localhost:%FRONTEND_PORT%" >nul 2>&1
if not errorlevel 1 (
    echo [WARN] 前端已在端口 %FRONTEND_PORT% 运行
    set FRONTEND_RUNNING=true
)

if "%BACKEND_RUNNING%"=="true" if "%FRONTEND_RUNNING%"=="true" (
    echo [WARN] 检测到前后端均已运行，将重新启动...
)

REM 检查端口占用（自动寻找可用端口）
:check_backend_port
netstat -ano | findstr ":%BACKEND_PORT%" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    if "%BACKEND_RUNNING%"=="true" if %BACKEND_PORT% EQU 8000 goto backend_port_done
    set /a BACKEND_PORT+=1
    goto check_backend_port
)
:backend_port_done

:check_frontend_port
netstat -ano | findstr ":%FRONTEND_PORT%" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    if "%FRONTEND_RUNNING%"=="true" if %FRONTEND_PORT% EQU 3000 goto frontend_port_done
    set /a FRONTEND_PORT+=1
    goto check_frontend_port
)
:frontend_port_done

if not %BACKEND_PORT% EQU 8000 (
    echo [WARN] 端口 8000 被占用，后端将使用端口 %BACKEND_PORT%
)
if not %FRONTEND_PORT% EQU 3000 (
    echo [WARN] 端口 3000 被占用，前端将使用端口 %FRONTEND_PORT%
)

REM ===== 4. 停止已运行服务 =====
echo ▶ [4/7] 停止已运行服务（如有）...

REM 停止后端
taskkill /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq *uvicorn*" /F >nul 2>&1
taskkill /FI "IMAGENAME eq python.exe" /FI "COMMANDLINE eq *uvicorn*" /F >nul 2>&1

REM 更可靠的方式：通过端口查找进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT%" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)

REM 停止前端
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT%" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)

REM 额外清理：停止所有 node 进程（如果它们占用目标端口）
taskkill /FI "IMAGENAME eq node.exe" /F >nul 2>&1
timeout /t 2 /nobreak >nul

echo [OK] 已清理旧服务

REM ===== 5. 创建虚拟环境 & 安装后端依赖 =====
echo ▶ [5/7] 准备后端环境...

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
python -m pip install -q --upgrade pip

if not exist "backend\requirements.txt" (
    echo [ERROR] 未找到 backend\requirements.txt
    pause
    exit /b 1
)

REM 检查是否需要重新安装
python -c "import hashlib; print(hashlib.md5(open('backend/requirements.txt','rb').read()).hexdigest())" > .req_hash.tmp 2>nul
set /p REQ_HASH=<.req_hash.tmp
del .req_hash.tmp 2>nul

set INSTALLED_HASH=
if exist ".venv\.req_hash" (
    set /p INSTALLED_HASH=<.venv\.req_hash
)

if not "%REQ_HASH%"=="%INSTALLED_HASH%" (
    echo [INFO] 安装/更新后端依赖...
    python -m pip install -q -r backend\requirements.txt
    if errorlevel 1 (
        echo [ERROR] 后端依赖安装失败
        pause
        exit /b 1
    )
    echo %REQ_HASH% > .venv\.req_hash
    echo [OK] 后端依赖安装完成
) else (
    echo [OK] 后端依赖已是最新
)

REM ===== 6. 安装前端依赖 & Build =====
echo ▶ [6/7] 准备前端环境...
cd frontend

if not exist "package.json" (
    echo [ERROR] 未找到 frontend\package.json
    pause
    exit /b 1
)

REM 检查是否需要 npm install
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

REM 检查是否需要重新 build
set NEED_BUILD=false
if not exist ".next" (
    echo [INFO] 首次构建前端...
    set NEED_BUILD=true
) else (
    REM 检查是否有源码文件比 .next\BUILD_ID 新
    for /f %%a in ('dir /s /b /o:-d *.tsx *.ts *.css *.json 2^>nul ^| findstr /V "node_modules" ^| findstr /V ".next" ^| head -1') do (
        REM 简化：如果有源码文件，就重新 build（Windows 批处理文件时间比较较复杂）
        REM 实际上，我们用另一种方式：检查 .next 目录是否存在且非空
        if not exist ".next\BUILD_ID" (
            set NEED_BUILD=true
        )
    )
)

if "%NEED_BUILD%"=="true" (
    echo [INFO] 构建前端（Next.js 生产构建）...
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
echo ▶ [7/7] 创建必要目录...
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
echo ▶ 检查环境配置...

REM 创建 .env（如果不存在）
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [WARN] .env 已自动创建（从 .env.example 复制）
    ) else (
        echo [WARN] .env 和 .env.example 都不存在，将使用默认配置
    )
)

REM 创建 backend\.env（如果不存在）
if not exist "backend\.env" (
    if exist "backend\.env.example" (
        copy "backend\.env.example" "backend\.env" >nul
        echo [OK] backend\.env 已自动创建
    ) else if exist ".env" (
        copy ".env" "backend\.env" >nul
        echo [OK] backend\.env 已自动创建（从 .env 复制）
    )
)

REM 检查 API Key / Provider 配置
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
    echo.
    echo 支持的 Provider: OpenAI, Anthropic, 阿里百炼, 硅基流动, 智谱, DeepSeek, Ollama, OpenRouter...
    echo.
    pause
)

REM ===== 9. 保存端口配置 =====
echo { > .ports.json
echo   "backend_port": %BACKEND_PORT%, >> .ports.json
echo   "frontend_port": %FRONTEND_PORT% >> .ports.json
echo } >> .ports.json

REM ===== 10. 启动服务 =====
echo ▶ 启动服务...
echo.
echo ╔══════════════════════════════════════════════════════════════════╗
echo ║  服务启动中...                                                    ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.

REM 启动后端（在新窗口中，方便用户查看日志）
echo [INFO] 启动后端服务（端口 %BACKEND_PORT%）...
start "Backend Server" cmd /k "cd /d %CD% && call .venv\Scripts\activate.bat && cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --no-access-log"

REM 等待后端启动
timeout /t 4 /nobreak >nul

REM 验证后端是否就绪
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
if "%BACKEND_READY%"=="false" (
    echo [WARN] 后端启动可能仍在进行中...
)

REM 启动前端（在新窗口中）
echo [INFO] 启动前端服务（端口 %FRONTEND_PORT%，生产模式）...
start "Frontend Server" cmd /k "cd /d %CD%\frontend && npm run start -- --port %FRONTEND_PORT%"

REM 等待前端启动
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
if "%FRONTEND_READY%"=="false" (
    echo [WARN] 前端启动可能仍在进行中...
)

REM ===== 11. 启动完成提示 =====
echo.
echo ╔══════════════════════════════════════════════════════════════════╗
echo ║  服务启动完成！访问地址：                                        ║
echo ╠══════════════════════════════════════════════════════════════════╣
echo ║  前端界面: http://localhost:%FRONTEND_PORT%                      ║
echo ║  后端 API: http://localhost:%BACKEND_PORT%/api/v1                ║
echo ║  API 文档: http://localhost:%BACKEND_PORT%/docs                  ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.
echo 使用说明：
echo   1. 打开浏览器访问 http://localhost:%FRONTEND_PORT%
echo   2. 选择论文模板（NeurIPS / ACM / IEEE / Springer / CUMCM）
echo   3. 输入研究题目或问题描述
echo   4. 点击提交，系统自动完成：分析→建模→求解→实验→论文→评议
echo   5. 在「PDF」Tab 下载 Camera-Ready 投稿包
echo.
echo 关闭此窗口即可停止所有服务（或按任意键）
echo.

pause >nul

REM 停止服务
echo.
echo [INFO] 正在停止服务...
taskkill /FI "WINDOWTITLE eq Backend Server" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Frontend Server" /F >nul 2>&1
REM 兜底：清理端口占用进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT%" ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT%" ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
del .ports.json 2>nul
echo [OK] 服务已停止

endlocal
