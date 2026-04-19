#!/bin/sh
set -e

cd /app/apiSystem

if [ "${DB_ENGINE:-postgresql}" = "postgres" ] || [ "${DB_ENGINE:-postgresql}" = "postgresql" ] || [ "${DB_ENGINE:-postgresql}" = "django.db.backends.postgresql" ]; then
  echo "Waiting for PostgreSQL..."
  uv run python - <<'PY'
import os
import time

import psycopg

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
            raise
        time.sleep(2)
PY
fi

# Redis 连通性检测（当 REDIS_URL 配置了才检测）
if [ -n "${REDIS_URL:-}" ]; then
  echo "Waiting for Redis..."
  uv run python - <<'PY'
import os
import time
from urllib.parse import urlparse

redis_url = os.environ.get("REDIS_URL", "")
parsed = urlparse(redis_url)
host = parsed.hostname or "redis"
port = parsed.port or 6379

deadline = time.time() + 60
while True:
    try:
        import socket
        sock = socket.create_connection((host, port), timeout=5)
        sock.sendall(b"PING\r\n")
        resp = sock.recv(1024)
        sock.close()
        if b"PONG" in resp or b"+PONG" in resp:
            break
    except Exception:
        if time.time() >= deadline:
            raise
        time.sleep(2)
PY
fi

echo "Running migrations..."
uv run python manage.py migrate --noinput

echo "Collecting static files..."
uv run python manage.py collectstatic --noinput

echo "Starting server..."
exec uv run python manage.py runserver 0.0.0.0:8002
