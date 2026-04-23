FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/

WORKDIR /app

# 替换为阿里云镜像源（解决国内网络问题）
RUN sed -i 's|deb.debian.org|mirrors.cloud.tencent.com|g' /etc/apt/sources.list.d/debian.sources

# 基础工具 + 字体 + xvfb（Playwright 系统依赖由 install-deps 自动安装）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    fonts-liberation fonts-noto-color-emoji \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv（pip 方式，避免 astral.sh/ghcr.io 国内无法访问）
RUN pip install --no-cache-dir uv -i https://mirrors.cloud.tencent.com/pypi/simple/

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
