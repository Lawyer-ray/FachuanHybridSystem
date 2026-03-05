#!/bin/sh
set -e

cd /app/apiSystem

echo "Running migrations..."
uv run python manage.py migrate --noinput

echo "Collecting static files..."
uv run python manage.py collectstatic --noinput

echo "Starting server..."
exec uv run python manage.py runserver 0.0.0.0:8002
