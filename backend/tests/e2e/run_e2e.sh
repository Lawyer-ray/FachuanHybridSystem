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
# **必须同时设 DB_ENGINE**：settings.py:240 的默认值是 postgresql，只设 DATABASE_PATH
# （settings.py:260 仅在 DB_ENGINE 为 sqlite* 时才读它）会被静默忽略，整套 e2e 会连到
# PostgreSQL 的 test_fachuan_dev 上跑 —— 违反「禁止用真实数据库跑测试」的红线
# （2026-11-24 端到端实测：teardown 报 `database "test_fachuan_dev" is being accessed`）。
export DB_ENGINE=sqlite
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

# 解释器解析：优先 $PYTHON，其次仓库 .venv，最后退回 python3。
# 原来硬编码 .venv/bin/python，在 git worktree（.venv 是 gitignored、不会检出）里会直接
# `No such file or directory`，让人误以为是测试失败（2026-11-24 实测浪费了一轮排查）。
PYTHON_BIN="${PYTHON:-$BACKEND_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON_FALLBACK:-python3}"
  echo "▶ pre-e2e: $BACKEND_DIR/.venv/bin/python 不存在，改用 $PYTHON_BIN" >&2
fi

exec "$PYTHON_BIN" -m pytest tests/e2e/ "${PYTEST_ARGS[@]}"
