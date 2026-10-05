#!/usr/bin/env bash
# 发布公网栈（app.xlaw.top）：
#   1. 前端构建 → frontend/dist
#   2. 同步 dist → 运行时目录（~/Library/Application Support/FachuanHybridSystem，
#      TCC 约束下 nginx 只读运行时副本）——nginx 直接读盘，发布即生效
#   3. collectstatic → STATIC_ROOT（当前未对外，为未来 admin 暴露预置）
# 后端代码更新后需另跑: make prod-restart（launchctl kickstart gunicorn）
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="$HOME/Library/Application Support/FachuanHybridSystem"

echo "==> [1/3] 前端构建 (pnpm build)"
cd "$REPO/frontend"
pnpm build

echo "==> [2/3] 同步 dist → 运行时目录"
mkdir -p "$RUNTIME"
rsync -a --delete "$REPO/frontend/dist/" "$RUNTIME/dist/"

echo "==> [3/3] collectstatic"
cd "$REPO/backend"
./.venv/bin/python apiSystem/manage.py collectstatic --noinput

echo ""
echo "发布完成。后端代码若有改动，执行: make prod-restart"
