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

echo "Running migrations..."
uv run python manage.py migrate --noinput

echo "Collecting static files..."
uv run python manage.py collectstatic --noinput

echo "Starting server..."
exec uv run python manage.py runserver 0.0.0.0:8002
