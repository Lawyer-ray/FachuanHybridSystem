#!/bin/bash
set -e

echo "Ensuring numpy compatibility..."
pip install --no-cache-dir "numpy<2" 2>/dev/null || true

# 执行原始entrypoint
exec /app/docker-entrypoint.sh "$@"
