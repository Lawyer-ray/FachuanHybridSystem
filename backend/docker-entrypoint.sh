#!/bin/sh
set -e

cd /app/apiSystem

# ──────────────────────────────────────────────
# 1. 等待 PostgreSQL 就绪
# ──────────────────────────────────────────────
if [ "${DB_ENGINE:-postgresql}" = "postgres" ] || \
   [ "${DB_ENGINE:-postgresql}" = "postgresql" ] || \
   [ "${DB_ENGINE:-postgresql}" = "django.db.backends.postgresql" ]; then
  echo "【启动】等待 PostgreSQL..."
  uv run python - <<'PY'
import os, time, psycopg

host = os.environ.get("DB_HOST", "postgres")
port = int(os.environ.get("DB_PORT", "5432"))
name = os.environ.get("DB_NAME", "fachuan_dev")
user = os.environ.get("DB_USER", "postgres")
password = os.environ.get("DB_PASSWORD", "postgres")

deadline = time.time() + 60
while True:
    try:
        with psycopg.connect(host=host, port=port, dbname=name, user=user, password=password, connect_timeout=5):
            break
    except Exception:
        if time.time() >= deadline:
            print("❌ PostgreSQL 连接超时")
            raise
        time.sleep(2)
PY
  echo "✅ PostgreSQL 就绪"
fi

# ──────────────────────────────────────────────
# 2. 等待 Valkey/Redis 就绪
# ──────────────────────────────────────────────
if [ -n "${REDIS_URL:-}" ]; then
  echo "【启动】等待 Valkey/Redis..."
  uv run python - <<'PY'
import os, time, socket
from urllib.parse import urlparse

redis_url = os.environ.get("REDIS_URL", "")
parsed = urlparse(redis_url)
host = parsed.hostname or "redis"
port = parsed.port or 6379

deadline = time.time() + 60
while True:
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.sendall(b"PING\r\n")
        resp = sock.recv(1024)
        sock.close()
        if b"PONG" in resp or b"+PONG" in resp:
            break
    except Exception:
        if time.time() >= deadline:
            print("❌ Redis 连接超时")
            raise
        time.sleep(2)
PY
  echo "✅ Valkey/Redis 就绪"
fi

# ──────────────────────────────────────────────
# 3. 数据库迁移 & 静态文件收集
# ──────────────────────────────────────────────
echo "【启动】执行数据库迁移..."
uv run python manage.py migrate --noinput

echo "【启动】收集静态文件..."
uv run python manage.py collectstatic --noinput

# ──────────────────────────────────────────────
# 4. 启动服务器（开发/生产自动切换）
# ──────────────────────────────────────────────
#
#   切换规则（按优先级）：
#     1) 环境变量 DJANGO_DEBUG=true/false 显式指定
#     2) 默认按开发模式（runserver）启动
#
#   生产方案：Gunicorn + UvicornWorker —— 适用于 < 100 用户
#   - UvicornWorker 兼容 django-channels WebSocket
#   - 4 个 worker 进程，每 1000 次请求自动回收（防内存泄漏）
#   - 日志输出到 stdout（兼容 Docker 日志收集）
#
DJANGO_DEBUG_VAL=$(echo "${DJANGO_DEBUG:-true}" | tr '[:upper:]' '[:lower:]')

if [ "$DJANGO_DEBUG_VAL" = "true" ] || [ "$DJANGO_DEBUG_VAL" = "1" ]; then
  # ── 开发模式 ──
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  模式：开发模式（Development）"
  echo "  服务器：Django runserver（自动热重载）"
  echo "  端口：8002"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  exec uv run python manage.py runserver --insecure 0.0.0.0:8002

else
  # ── 生产模式 ──
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  模式：生产模式（Production）"
  echo "  服务器：Gunicorn + UvicornWorker"
  echo "  Workers：4（适合 < 100 用户）"
  echo "  端口：8002"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  # 可通过环境变量 GUNICORN_WORKERS 覆盖 Worker 数量
  WORKERS="${GUNICORN_WORKERS:-4}"

  exec uv run gunicorn apiSystem.asgi:application \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "$WORKERS" \
    --bind 0.0.0.0:8002 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --timeout 120 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile -
fi
