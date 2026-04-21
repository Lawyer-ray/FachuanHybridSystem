FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

# 替换为阿里云镜像源（解决国内网络问题）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources

# 基础工具 + 字体 + xvfb（Playwright 系统依赖由 install-deps 自动安装）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    fonts-liberation fonts-noto-color-emoji \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 安装 Python 依赖（利用 layer 缓存）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 安装 Playwright chromium 及其系统依赖（用 install-deps 自动补全，避免手动维护依赖列表）
RUN uv run playwright install chromium \
    && uv run playwright install-deps chromium

# 复制项目代码
COPY . .

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8002

ENTRYPOINT ["/docker-entrypoint.sh"]
