FROM python:3.12-slim

ARG INSTALL_FULL_DEPS=true

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 安装 Python 依赖
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 安装 Playwright 浏览器（仅 INSTALL_FULL_DEPS=true 时）
RUN if [ "$INSTALL_FULL_DEPS" = "true" ]; then \
        uv run playwright install --with-deps chromium; \
    fi

# 复制项目代码
COPY . .

WORKDIR /app/apiSystem

EXPOSE 8002

CMD ["uv", "run", "uvicorn", "apiSystem.asgi:application", "--host", "0.0.0.0", "--port", "8002"]
