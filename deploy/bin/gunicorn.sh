#!/usr/bin/env bash
# 公网后端入口：加载生产覆盖环境后前台运行 gunicorn（由 launchd 托管）。
#
# 运行时位置：本脚本由 install.sh 复制到
# ~/Library/Application Support/FachuanHybridSystem/bin/（macOS TCC 拦截
# launchd 后台进程读取 ~/Downloads，仓库内的这份是源文件）。
set -euo pipefail

RUNTIME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=../env/prod.env
source "$RUNTIME/env/prod.env"

# 经解释器直接启动（exec 仓库内 .venv/bin/gunicorn 脚本文件会被 TCC 拦截，
# 而符号链接 .venv/bin/python 指向非保护的 homebrew Cellar，exec 畅通；
# 代价是 python 读仓库代码需要一次性的「完全磁盘访问权限」授权）
exec "$FACHUAN_REPO/backend/.venv/bin/python" -m gunicorn \
    apiSystem.asgi:application \
    --config "$RUNTIME/gunicorn.conf.py"
