FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_INDEX_URL=https://pypi.org/simple/ \
    TZ=Asia/Shanghai

WORKDIR /app

# 设置时区为上海（解决容器默认 UTC 导致时间偏差）
RUN ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && echo "Asia/Shanghai" > /etc/timezone

# 替换为清华镜像源（解决国内网络问题）
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources

# 基础工具 + 字体 + xvfb + OpenCV 依赖（CloakBrowser 系统依赖）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    fonts-liberation fonts-noto-color-emoji \
    xvfb \
    libgl1 libglib2.0-0t64 \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv（pip 方式，避免 astral.sh/ghcr.io 国内无法访问）
RUN pip install --no-cache-dir uv -i https://pypi.org/simple/

# 安装 Python 依赖（利用 layer 缓存）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 安装 CloakBrowser 浏览器二进制（替代 Playwright chromium，内置 C++ 级反检测）
RUN uv run python -m cloakbrowser install

# 自动安装 Chromium 所需的系统库（libnspr4 等 NSS 套件）
RUN uv run playwright install-deps chromium

# 复制项目代码
COPY . .

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8002

ENTRYPOINT ["/docker-entrypoint.sh"]
