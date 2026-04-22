# 数学建模多Agent系统 - Dockerfile
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（LaTeX编译 + Node.js + 其他工具）
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    # LaTeX 编译工具（用于生成PDF论文）
    texlive-latex-base \
    texlive-latex-extra \
    texlive-xetex \
    fonts-wqy-microhei \
    # Node.js（用于运行 npx MCP 工具）
    nodejs \
    npm \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据目录（支持 Docker Volume 挂载）
RUN mkdir -p /app/backend/data/uploads \
             /app/backend/data/tasks \
             /app/output/papers \
             /app/output/code \
             /app/output/figures

# 暴露端口
EXPOSE 8000

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
