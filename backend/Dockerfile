FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

# 替换为阿里云镜像源（解决国内网络问题）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources

# Playwright chromium 所需的系统依赖 + curl（一次性安装，避免 --with-deps 网络不稳定）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 \
    libcups2t64 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2t64 libxshmfence1 \
    fonts-liberation fonts-noto-color-emoji \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 安装 Python 依赖（利用 layer 缓存）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 安装 Playwright chromium（系统依赖已手动安装，无需 --with-deps）
RUN uv run playwright install chromium

# 复制项目代码
COPY . .

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8002

ENTRYPOINT ["/docker-entrypoint.sh"]
