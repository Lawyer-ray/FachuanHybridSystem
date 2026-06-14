#!/bin/bash
# Django Admin E2E 测试运行脚本
#
# 用法:
#   ./tests/e2e/run_e2e.sh                    # 运行全部 E2E 测试
#   ./tests/e2e/run_e2e.sh tests/e2e/tests/test_auth.py  # 运行指定文件
#   ./tests/e2e/run_e2e.sh --headed           # 有头模式（调试）
#   ./tests/e2e/run_e2e.sh --smoke            # 只跑冒烟测试

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# E2E 测试使用 SQLite 文件数据库（避免 PostgreSQL 连接争用）
export DATABASE_PATH="$SCRIPT_DIR/e2e_test.sqlite3"
export DJANGO_ALLOW_ASYNC_UNSAFE=true

# 默认参数
PYTEST_ARGS=(
    "-v"
    "--timeout=120"
    "-o" "addopts=--import-mode=importlib --tb=short --timeout=120"
)

# 解析命令行参数
for arg in "$@"; do
    case "$arg" in
        --headed)
            PYTEST_ARGS+=("--headed")
            ;;
        --smoke)
            PYTEST_ARGS+=("-m" "smoke")
            ;;
        --debug)
            PYTEST_ARGS+=("--headed" "-s" "--timeout=0")
            ;;
        *)
            PYTEST_ARGS+=("$arg")
            ;;
    esac
done

cd "$BACKEND_DIR"
exec .venv/bin/python -m pytest tests/e2e/ "${PYTEST_ARGS[@]}"
