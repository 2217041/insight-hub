# FastAPI 镜像
# 关键点：
# 1. 用 slim 基础镜像，且 pip 换国内源（否则构建卡在下载）
# 2. 先 COPY requirements.txt 再 COPY 代码 —— 利用层缓存，改代码不用重装依赖
# 3. 非 root 用户运行
# 4. 不加 --reload，生产环境要的是稳定不是热更

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 国内构建必须配置镜像源，否则 pip install 会卡在 PyPI
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY main.py ./
COPY migrations ./migrations
COPY alembic.ini ./

# 上传文件与日志目录（生产应挂卷）
RUN mkdir -p /app/data/uploads && \
    useradd -m -u 10001 appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 默认启动 API；worker 通过 compose 覆盖 command 复用同一个镜像
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]