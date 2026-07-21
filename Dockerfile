# 数学建模多Agent系统 - 根目录 Dockerfile
FROM python:3.11-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-xetex \
    texlive-lang-chinese \
    fonts-noto-cjk \
    util-linux \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY backend/ config/ src/

# 工作目录设为 backend
WORKDIR /app/backend

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
