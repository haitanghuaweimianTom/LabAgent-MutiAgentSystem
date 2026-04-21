@echo off
REM 数学建模多Agent系统 - 快速启动脚本
REM 用法: 双击 start.bat 或在命令行执行

cd /d "%~dp0"
echo ========================================
echo   数学建模多Agent系统 启动器
echo ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

REM 检查后端依赖
echo [1/3] 检查后端依赖...
cd backend
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo [INFO] 安装后端依赖（首次运行）...
    pip install -r requirements.txt -q
)

REM 创建必要目录
if not exist "data\uploads" mkdir "data\uploads"
if not exist "data\tasks" mkdir "data\tasks"
if not exist "..\output\papers" mkdir "..\output\papers"
if not exist "..\output\code" mkdir "..\output\code"
if not exist "..\output\figures" mkdir "..\output\figures"

REM 检查 .env
if not exist ".env" (
    if exist "..\.env.example" (
        copy "..\.env.example" ".env"
        echo [WARN] 已创建 .env，请编辑填写 MINIMAX_API_KEY
    )
)

echo [2/3] 启动后端服务...
echo.
echo 访问地址:
echo   - API文档: http://localhost:8000/docs
echo   - 健康检查: http://localhost:8000/health
echo.
echo 按 Ctrl+C 停止服务
echo.
uvicorn app.main:app --reload --port 8000 --host 127.0.0.1
