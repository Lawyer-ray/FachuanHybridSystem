#!/usr/bin/env bash
# ci-local.sh — 本地 CI 镜像，与 GitHub Actions 完全对齐
#
# 用法:
#   ./scripts/ci-local.sh              # 默认 --quick（不需要数据库）
#   ./scripts/ci-local.sh --quick      # 快速检查：lint + typecheck + frontend build
#   ./scripts/ci-local.sh --full       # 完整检查：quick + 测试 + 覆盖率 + smoke
#   ./scripts/ci-local.sh --frontend   # 仅前端
#   ./scripts/ci-local.sh --backend    # 仅后端
#
# 对照表（本脚本 → GitHub CI job）：
#   [1]  security-guard       → backend-security-guard
#   [2]  repository-hygiene   → backend (Repository hygiene step)
#   [3]  compileall           → backend (Compile Python step)
#   [4]  pre-commit           → backend (Pre-commit step)
#   [5]  ruff-changed         → backend (Lint ruff changed files)
#   [6]  ruff-full            → backend-ruff-full / backend (core + apiSystem)
#   [7]  mypy-changed         → backend (Type check mypy changed files)
#   [8]  mypy-curated         → backend (Type check mypy curated gate)
#   [9]  mypy-strict          → backend-mypy-strict
#   [10] mypy-extra           → backend-mypy (extra gate)
#   [11] structure-smoke      → backend (Tests collection smoke)
#   [12] unit-tests           → backend (Tests unit)
#   [13] smoke-check          → backend (Smoke check minimal)
#   [14] pip-audit            → backend (Dependency audit)
#   [15] bandit               → backend (Static security scan)
#   [16] unit-coverage        → backend-unit-coverage (≥85%)
#   [17] integration-smoke    → backend-integration-smoke
#   [18] property-smoke       → backend-property-smoke
#   [19] apps-coverage        → backend-coverage (≥25%)
#   [20] tsc                  → frontend (Type check)
#   [21] eslint               → frontend (Lint)
#   [22] vite-build           → frontend (Build)

set -euo pipefail

# ── 颜色 ───────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── 参数解析 ───────────────────────────────────────────────────
MODE="quick"
RUN_BACKEND=true
RUN_FRONTEND=true

for arg in "$@"; do
  case "$arg" in
    --full)    MODE="full" ;;
    --quick)   MODE="quick" ;;
    --backend) RUN_FRONTEND=false ;;
    --frontend) RUN_BACKEND=false ;;
    -h|--help)
      echo "用法: $0 [--quick|--full|--backend|--frontend]"
      echo ""
      echo "  --quick      快速检查（默认，不需要数据库）"
      echo "  --full       完整检查（需要 PostgreSQL）"
      echo "  --backend    仅后端检查"
      echo "  --frontend   仅前端检查"
      exit 0
      ;;
    *)
      echo "未知参数: $arg（使用 --help 查看帮助）"
      exit 1
      ;;
  esac
done

# ── 路径 ───────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

# ── 计数器 ─────────────────────────────────────────────────────
PASSED=0
FAILED=0
SKIPPED=0
FAILURES=()

pass()  { ((PASSED++)); echo -e "  ${GREEN}✓${NC} $1"; }
fail()  { ((FAILED++)); FAILURES+=("$1"); echo -e "  ${RED}✗${NC} $1"; }
skip()  { ((SKIPPED++)); echo -e "  ${YELLOW}⊘${NC} $1（跳过）"; }
header(){ echo -e "\n${CYAN}━━━ [$1] $2 ━━━${NC}"; }

# ── 计算 merge-base（对齐 CI 的 diff 策略）────────────────────
# GitHub CI 用 origin/main 作为 PR 基准，本地也用 main 以保持一致
compute_base() {
  local base=""
  local current_branch
  current_branch=$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
  if [ "$current_branch" = "main" ] || [ "$current_branch" = "master" ]; then
    # 在主分支上，用 HEAD~1
    base="HEAD~1"
  else
    # 在 feature 分支上，用 main（与 GitHub CI 的 GITHUB_BASE_REF 一致）
    base="main"
  fi
  git -C "$ROOT_DIR" merge-base HEAD "$base" 2>/dev/null || echo ""
}

BASE_MERGE=$(compute_base)

# ── DB 环境变量（full 模式需要）────────────────────────────────
export DJANGO_DEBUG=1
export DB_ENGINE=postgresql
export TEST_DB_ENGINE=postgresql
export TEST_DB_NAME="${TEST_DB_NAME:-fachuan_ci_test}"
export TEST_DB_USER="${TEST_DB_USER:-postgres}"
export TEST_DB_PASSWORD="${TEST_DB_PASSWORD:-postgres}"
export TEST_DB_HOST="${TEST_DB_HOST:-127.0.0.1}"
export TEST_DB_PORT="${TEST_DB_PORT:-5432}"
export DB_NAME="$TEST_DB_NAME"
export DB_USER="$TEST_DB_USER"
export DB_PASSWORD="$TEST_DB_PASSWORD"
export DB_HOST="$TEST_DB_HOST"
export DB_PORT="$TEST_DB_PORT"
export PYTHONPATH="apiSystem:."
export HYPOTHESIS_PROFILE=default

BACKEND_PYTHON="$BACKEND_DIR/.venv/bin/python"
BACKEND_PYTEST="$BACKEND_DIR/.venv/bin/pytest"

# ============================================================
#  后端检查
# ============================================================
if [ "$RUN_BACKEND" = true ]; then
  echo -e "\n${CYAN}╔══════════════════════════════════════════════╗${NC}"
  echo -e "${CYAN}║          后端 CI 检查 ($MODE 模式)           ║${NC}"
  echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"

  cd "$BACKEND_DIR"

  # [1] Security guard（对齐 backend-security-guard）
  header "1/22" "敏感信息扫描 (security guard)"
  if [ -n "$BASE_MERGE" ]; then
    if $BACKEND_PYTHON devtools/security_guard.py --check sensitive --mode range --base "$BASE_MERGE" --head HEAD 2>&1; then
      pass "security-guard"
    else
      fail "security-guard"
    fi
  else
    skip "security-guard（无基准 commit）"
  fi

  # [2] Repository hygiene（对齐 backend job 的 Repository hygiene step）
  header "2/22" "仓库卫生检查 (repository hygiene)"
  _hygiene_ok=true

  banned=$(git -C "$ROOT_DIR" ls-files | grep -E '(^|/)(\.DS_Store|__pycache__/|[^/]+\.pyc)$' || true)
  if [ -n "$banned" ]; then
    echo -e "  ${RED}发现禁止追踪的文件:${NC}"; echo "$banned" | sed 's/^/    /'
    _hygiene_ok=false
  fi

  env_tracked=$(git -C "$ROOT_DIR" ls-files | grep -E '(^|/)\.env(\.[^/]+)?$' | grep -v -E '(^|/)\.env\.example$' || true)
  if [ -n "$env_tracked" ]; then
    echo -e "  ${RED}发现已追踪的 .env 文件:${NC}"; echo "$env_tracked" | sed 's/^/    /'
    _hygiene_ok=false
  fi

  media_tracked=$(git -C "$ROOT_DIR" ls-files backend/media backend/apiSystem/media 2>/dev/null | grep -v '\.gitkeep$' || true)
  if [ -n "$media_tracked" ]; then
    echo -e "  ${RED}发现已追踪的 media 文件:${NC}"; echo "$media_tracked" | sed 's/^/    /'
    _hygiene_ok=false
  fi

  venv_tracked=$(git -C "$ROOT_DIR" ls-files | grep -E '^(backend/)?(\.venv|venv(311|312)?)/' || true)
  if [ -n "$venv_tracked" ]; then
    echo -e "  ${RED}发现已追踪的虚拟环境文件:${NC}"; echo "$venv_tracked" | sed 's/^/    /'
    _hygiene_ok=false
  fi

  forbidden_binary=$(git -C "$ROOT_DIR" ls-files | grep -Ei '^(backend/(apps|apiSystem|scripts)/|scripts/).*\.(onnx|mp4|zip)$' || true)
  if [ -n "$forbidden_binary" ]; then
    echo -e "  ${RED}发现禁止追踪的二进制文件:${NC}"; echo "$forbidden_binary" | sed 's/^/    /'
    _hygiene_ok=false
  fi

  if $_hygiene_ok; then pass "repository-hygiene"; else fail "repository-hygiene"; fi

  # [3] Compile Python（对齐 backend job 的 Compile Python step）
  header "3/22" "Python 编译检查 (compileall)"
  if $BACKEND_PYTHON -m compileall -q apps apiSystem 2>&1; then
    pass "compileall"
  else
    fail "compileall"
  fi

  # [4] Pre-commit（对齐 backend job 的 Pre-commit step）
  header "4/22" "Pre-commit hooks (changed files)"
  if [ -n "$BASE_MERGE" ]; then
    pre_files=$(git -C "$ROOT_DIR" diff --name-only --diff-filter=ACMRT "$BASE_MERGE" HEAD | grep -E '^backend/' | sed 's|^backend/||' || true)
    if [ -z "$pre_files" ]; then
      skip "pre-commit（无变更文件）"
    else
      # shellcheck disable=SC2086
      if $BACKEND_PYTHON -m pre_commit run --files $pre_files 2>&1; then
        pass "pre-commit"
      else
        fail "pre-commit"
      fi
    fi
  else
    skip "pre-commit（无基准 commit）"
  fi

  # [5] Ruff changed files（对齐 backend job 的 Lint ruff changed files step）
  header "5/22" "Ruff 检查 (changed files)"
  if [ -n "$BASE_MERGE" ]; then
    ruff_changed=$(git -C "$ROOT_DIR" diff --name-only --diff-filter=ACMRT "$BASE_MERGE" HEAD \
      | grep -E '^backend/apps/.*\.py$' | sed 's|^backend/||' || true)
    if [ -z "$ruff_changed" ]; then
      skip "ruff-changed（无变更文件）"
    else
      # shellcheck disable=SC2086
      if $BACKEND_PYTHON -m ruff check $ruff_changed --config ruff.toml 2>&1; then
        pass "ruff-changed"
      else
        fail "ruff-changed"
      fi
    fi
  else
    skip "ruff-changed（无基准 commit）"
  fi

  # [6] Ruff full（对齐 backend-ruff-full job + backend job 的 core + apiSystem step）
  header "6/22" "Ruff 检查 (core + apiSystem 全量)"
  if $BACKEND_PYTHON -m ruff check apps/core apiSystem --config ruff.toml 2>&1; then
    pass "ruff-full"
  else
    fail "ruff-full"
  fi

  # [7] Mypy changed files（对齐 backend job 的 Type check mypy changed files step）
  header "7/22" "Mypy 检查 (changed files)"
  if [ -n "$BASE_MERGE" ]; then
    mypy_changed=$(git -C "$ROOT_DIR" diff --name-only --diff-filter=ACMRT "$BASE_MERGE" HEAD \
      | grep -E '^backend/apps/.*\.py$' | grep -Ev '/__init__\.py$' | sed 's|^backend/||' || true)
    if [ -z "$mypy_changed" ]; then
      skip "mypy-changed（无变更文件）"
    else
      # shellcheck disable=SC2086
      if PYTHONPATH=apiSystem:. $BACKEND_PYTHON -m mypy --config-file=mypy.ini --follow-imports=silent $mypy_changed 2>&1; then
        pass "mypy-changed"
      else
        fail "mypy-changed"
      fi
    fi
  else
    skip "mypy-changed（无基准 commit）"
  fi

  # [8] Mypy curated gate（对齐 backend job 的 Type check mypy curated gate step）
  header "8/22" "Mypy 检查 (curated gate)"
  MYPY_CURATED=(
    apps/core/services/wiring.py
    apps/core/protocols/common_protocols.py
    apps/core/dto/auth.py
    apps/core/infrastructure/throttling.py
    apps/core/exceptions/handlers.py
    apiSystem/apiSystem/api.py
    apps/workbench/services/chat_service.py
  )
  if PYTHONPATH=apiSystem:. $BACKEND_PYTHON -m mypy --config-file=mypy.ini --follow-imports=silent "${MYPY_CURATED[@]}" 2>&1; then
    pass "mypy-curated"
  else
    fail "mypy-curated"
  fi

  if [ "$MODE" = "full" ]; then
    # [9] Mypy strict gate（对齐 backend-mypy-strict job）
    header "9/22" "Mypy 检查 (strict gate)"
    MYPY_STRICT=(
      "${MYPY_CURATED[@]}"
      apps/organization/services/access/organization_access_policy.py
    )
    if PYTHONPATH=apiSystem:. $BACKEND_PYTHON -m mypy --config-file=mypy.ini --follow-imports=silent "${MYPY_STRICT[@]}" 2>&1; then
      pass "mypy-strict"
    else
      fail "mypy-strict"
    fi

    # [10] Mypy extra gate（对齐 backend-mypy job）
    header "10/22" "Mypy 检查 (extra gate)"
    MYPY_EXTRA=(
      apps/core/security/auth.py
      apps/core/infrastructure/throttling.py
      apps/core/infrastructure/cache.py
      apps/core/middleware/request_id.py
      apps/core/middleware/security.py
      apps/organization/services/auth/auth_service.py
      apps/automation/services/token/cache_manager.py
      apps/automation/utils/logging_mixins/common.py
    )
    if PYTHONPATH=apiSystem:. $BACKEND_PYTHON -m mypy --config-file=mypy.ini --follow-imports=silent "${MYPY_EXTRA[@]}" 2>&1; then
      pass "mypy-extra"
    else
      fail "mypy-extra"
    fi

    # [11] Structure smoke（对齐 backend job 的 Tests collection smoke step）
    header "11/22" "结构测试 (structure smoke)"
    if $BACKEND_PYTEST -c pytest.ini --no-cov --collect-only -q tests/ci/structure/ 2>&1; then
      pass "structure-smoke"
    else
      fail "structure-smoke"
    fi

    # [12] Unit tests（对齐 backend job 的 Tests unit step）
    header "12/22" "单元测试 (unit)"
    if $BACKEND_PYTEST -c pytest.ini --no-cov -q tests/ci/unit/ 2>&1; then
      pass "unit-tests"
    else
      fail "unit-tests"
    fi

    # [13] Smoke check（对齐 backend job 的 Smoke check step）
    header "13/22" "Smoke check (minimal)"
    if $BACKEND_PYTHON apiSystem/manage.py smoke_check --skip-admin --skip-websocket --skip-q 2>&1; then
      pass "smoke-check"
    else
      fail "smoke-check"
    fi
  else
    skip "structure-smoke（需要 --full）"
    skip "unit-tests（需要 --full）"
    skip "smoke-check（需要 --full）"
    skip "mypy-strict（需要 --full）"
    skip "mypy-extra（需要 --full）"
  fi

  # [14] pip-audit（对齐 backend job 的 Dependency audit step）
  header "14/22" "依赖安全审计 (pip-audit)"
  if $BACKEND_PYTHON -m pip_audit --ignore-vuln CVE-2026-3219 --ignore-vuln CVE-2026-6357 --ignore-vuln CVE-2026-42304 --ignore-vuln CVE-2026-46678 --ignore-vuln PYSEC-2026-89 --ignore-vuln PYSEC-2026-161 --ignore-vuln PYSEC-2025-183 2>&1; then
    pass "pip-audit"
  else
    fail "pip-audit"
  fi

  # [15] Bandit（对齐 backend job 的 Static security scan step）
  header "15/22" "静态安全扫描 (bandit)"
  if $BACKEND_PYTHON -m bandit -r apps -q -lll -x "*/migrations/*,*/static/*,*/staticfiles/*,*/media/*,*/venv*/*,*/htmlcov/*" 2>&1; then
    pass "bandit"
  else
    fail "bandit"
  fi

  if [ "$MODE" = "full" ]; then
    # [16] Unit coverage（对齐 backend-unit-coverage job）
    header "16/22" "单元测试覆盖率 (≥85%)"
    if $BACKEND_PYTEST -c pytest.ini -q -o addopts="" \
      --reuse-db --import-mode=importlib \
      --cov=apps.cases.services.case.case_admin_export_bridge \
      --cov=apps.cases.services.case.case_contract_export_bridge \
      --cov=apps.contracts.services.contract.admin_workflows.clone_workflow \
      --cov=apps.client.services.text_parser \
      --cov=apps.enterprise_data.services.clients.api_key_pool \
      --cov-report=term-missing --cov-fail-under=85 \
      tests/ci/unit/ 2>&1; then
      pass "unit-coverage"
    else
      fail "unit-coverage"
    fi

    # [17] Integration smoke（对齐 backend-integration-smoke job）
    header "17/22" "集成测试 (integration smoke)"
    if $BACKEND_PYTEST -c pytest.ini --no-cov -q tests/ci/integration/ 2>&1; then
      pass "integration-smoke"
    else
      fail "integration-smoke"
    fi

    # [18] Property smoke（对齐 backend-property-smoke job）
    header "18/22" "Property-based 测试"
    if HYPOTHESIS_PROFILE=default $BACKEND_PYTEST -c pytest.ini --no-cov -q tests/ci/property/ 2>&1; then
      pass "property-smoke"
    else
      fail "property-smoke"
    fi

    # [19] Apps coverage（对齐 backend-coverage job）
    header "19/22" "全局覆盖率基线 (≥25%)"
    if $BACKEND_PYTEST -c pytest.ini -o addopts="" \
      --reuse-db --import-mode=importlib \
      --cov=apps \
      --cov-report=term-missing --cov-fail-under=25 \
      -q tests/ci/unit/ 2>&1; then
      pass "apps-coverage"
    else
      fail "apps-coverage"
    fi
  else
    skip "unit-coverage（需要 --full）"
    skip "integration-smoke（需要 --full）"
    skip "property-smoke（需要 --full）"
    skip "apps-coverage（需要 --full）"
  fi

  cd "$ROOT_DIR"
fi

# ============================================================
#  前端检查
# ============================================================
if [ "$RUN_FRONTEND" = true ]; then
  echo -e "\n${CYAN}╔══════════════════════════════════════════════╗${NC}"
  echo -e "${CYAN}║          前端 CI 检查                        ║${NC}"
  echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"

  cd "$FRONTEND_DIR"

  # 确保依赖已安装
  if [ ! -d "node_modules" ]; then
    echo -e "  ${YELLOW}安装前端依赖...${NC}"
    pnpm install --frozen-lockfile 2>&1
  fi

  # [20] TypeScript 检查（对齐 frontend job 的 Type check step）
  header "20/22" "TypeScript 类型检查 (tsc)"
  if pnpm exec tsc --project tsconfig.app.json --noEmit 2>&1; then
    pass "tsc"
  else
    fail "tsc"
  fi

  # [21] ESLint 检查（对齐 frontend job 的 Lint step）
  header "21/22" "ESLint 检查"
  if pnpm lint 2>&1; then
    pass "eslint"
  else
    fail "eslint"
  fi

  # [22] Vite 构建（对齐 frontend job 的 Build step）
  header "22/22" "Vite 生产构建"
  if pnpm build 2>&1; then
    pass "vite-build"
  else
    fail "vite-build"
  fi

  cd "$ROOT_DIR"
fi

# ============================================================
#  汇总
# ============================================================
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${GREEN}通过: ${PASSED}${NC}  ${RED}失败: ${FAILED}${NC}  ${YELLOW}跳过: ${SKIPPED}${NC}"

if [ "$FAILED" -gt 0 ]; then
  echo ""
  echo -e "  ${RED}失败项:${NC}"
  for item in "${FAILURES[@]}"; do
    echo -e "    ${RED}✗${NC} $item"
  done
  echo ""
  exit 1
fi

echo ""
echo -e "  ${GREEN}全部通过!${NC}"
exit 0
