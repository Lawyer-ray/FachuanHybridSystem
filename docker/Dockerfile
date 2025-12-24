# ============================================================
# 法穿案件管理系统 - 生产环境 Dockerfile
# ============================================================
# 多阶段构建：优化镜像大小
# 基础镜像：Python 3.11-slim
# ============================================================

# Stage 1: Builder - 安装 Python 依赖
FROM python:3.11-slim AS builder

WORKDIR /build

# 安装构建依赖（添加重试机制应对网络问题）
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt \
    for i in 1 2 3; do \
        apt-get update && apt-get install -y --no-install-recommends \
            build-essential \
        && break || sleep 5; \
    done

# 复制依赖文件
COPY backend/requirements.txt .

# 创建虚拟环境并安装依赖
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ============================================================
# Stage 2: Runtime - 最终运行镜像
# ============================================================
FROM python:3.11-slim AS runtime

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:$PATH" \
    APP_VERSION="1.0.0"

# 安装运行时依赖和 Playwright 系统依赖（添加重试机制）
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt \
    for i in 1 2 3; do \
        apt-get update && apt-get install -y --no-install-recommends \
            # Playwright 浏览器依赖
            libglib2.0-0 \
            libnss3 \
            libnspr4 \
            libdbus-1-3 \
            libatk1.0-0 \
            libatk-bridge2.0-0 \
            libcups2 \
            libdrm2 \
            libxkbcommon0 \
            libxcomposite1 \
            libxdamage1 \
            libxfixes3 \
            libxrandr2 \
            libgbm1 \
            libpango-1.0-0 \
            libcairo2 \
            libasound2 \
            libatspi2.0-0 \
            libxshmfence1 \
            # OpenCV 依赖
            libgl1 \
            libglib2.0-0 \
            # 其他工具
            curl \
            redis-tools \
        && break || sleep 5; \
    done

# 创建非 root 用户 (安全最佳实践)
RUN groupadd -r appgroup && \
    useradd -r -g appgroup -d /app -s /sbin/nologin appuser

WORKDIR /app

# 从 builder 阶段复制虚拟环境
COPY --from=builder /opt/venv /opt/venv

# 复制应用代码
COPY backend/ .

# 安装 Playwright 浏览器 (Chromium)
# 注意：playwright install-deps 需要 root 权限和网络访问
# 如果网络不稳定，可以只安装浏览器，系统依赖已在上面安装
RUN playwright install chromium || echo "Playwright browser installation completed with warnings"

# 创建数据目录并设置权限
RUN mkdir -p /app/data /app/media /app/logs /app/staticfiles && \
    chown -R appuser:appgroup /app

# 复制入口脚本和 Gunicorn 配置
COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/gunicorn.conf.py /app/gunicorn.conf.py
RUN chmod +x /entrypoint.sh

# 切换到非 root 用户
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# 入口点和默认命令（使用配置文件）
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "apiSystem.wsgi:application", "--config", "/app/gunicorn.conf.py"]
