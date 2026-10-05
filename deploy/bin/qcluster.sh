#!/usr/bin/env bash
# 公网任务队列入口：生产口径运行 Django-Q（由 launchd 托管）。
# 公网触发的异步任务（文书下载/识别、短信等）不再依赖开发终端里的 qcluster。
#
# 运行时位置：同 gunicorn.sh（install.sh 复制到 Application Support）。
set -euo pipefail

RUNTIME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=../env/prod.env
source "$RUNTIME/env/prod.env"

cd "$FACHUAN_REPO/backend/apiSystem"
exec "$FACHUAN_REPO/backend/.venv/bin/python" manage.py qcluster
