#!/bin/bash
# 本地 CI 脚本 - 运行与远端相同的检查
# 用法: ./scripts/local_ci.sh

set -e

echo "=========================================="
echo "本地 CI 检查开始"
echo "=========================================="

# 获取项目根目录
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# 使用 backend/.venv 中的 Python
PYTHON=backend/.venv/bin/python

# 1. Ruff check（只检查修改的文件）
echo ""
echo "1/4 Ruff check..."
CHANGED_PY_FILES=$(git diff --name-only --diff-filter=ACMRT HEAD~1 HEAD | grep -E '\.py$' || true)
if [ -n "$CHANGED_PY_FILES" ]; then
    $PYTHON -m ruff check $CHANGED_PY_FILES --select=E,F,W --ignore=E501 || {
        echo "❌ Ruff check 失败"
        exit 1
    }
    echo "✅ Ruff check 通过"
else
    echo "⏭️ 没有修改的 Python 文件，跳过 ruff"
fi

# 2. Mypy 类型检查（只检查修改的文件）
echo ""
echo "2/4 Mypy 类型检查..."
CHANGED_FILES=$(git diff --name-only --diff-filter=ACMRT HEAD~1 HEAD | grep -E '^backend/apps/.*\.py$' | grep -Ev '/__init__\.py$' | sed 's|^backend/||' || true)
if [ -n "$CHANGED_FILES" ]; then
    cd backend
    ../$PYTHON -m mypy --config-file=mypy.ini --follow-imports=silent $CHANGED_FILES 2>&1 || {
        echo "⚠️ Mypy 类型检查有警告（继续执行）"
        cd "$PROJECT_ROOT"
    }
    cd "$PROJECT_ROOT"
    echo "✅ Mypy 类型检查完成"
else
    echo "⏭️ 没有修改的 Python 文件，跳过 mypy"
fi

# 3. 单元测试（快速模式）
echo ""
echo "3/4 单元测试..."
cd "$PROJECT_ROOT/backend/apiSystem"
$PROJECT_ROOT/$PYTHON -m pytest tests/ci/unit/ -x -q --timeout=60 --no-header || {
    echo "❌ 单元测试失败"
    exit 1
}
echo "✅ 单元测试通过"

# 4. 覆盖率检查（可选）
echo ""
echo "4/4 覆盖率检查..."
$PROJECT_ROOT/$PYTHON -m pytest tests/ci/unit/ --cov=apps --cov-report=term-missing --cov-fail-under=80 -q --no-header 2>&1 | tail -20 || {
    echo "⚠️ 覆盖率检查完成（可能低于 80%）"
}

echo ""
echo "=========================================="
echo "✅ 本地 CI 检查完成"
echo "=========================================="
