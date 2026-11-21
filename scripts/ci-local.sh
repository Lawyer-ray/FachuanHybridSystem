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
#   [0]  guardrails-wired     → frontend-ci / guardrails-wired（护栏通电自检，见 pitfalls.md PIT-005）
#   [1]  security-guard       → backend-security-guard
#   [2]  repository-hygiene   → backend (Repository hygiene step)
#   [3]  compileall           → backend (Compile Python step)
#   [4]  pre-commit           → backend (Pre-commit step)
#   [5]  ruff-changed         → backend (Lint ruff changed files)
#   [6]  ruff-full            → backend-ruff-full / backend (core + apiSystem)
#   [7]  mypy-changed         → backend (Type check mypy changed files)
#   [8]  mypy-curated+full    → backend (Type check mypy curated gate + full-scan ratchet)
#   [9]  structure-tests      → backend (Tests structure, real run)
#   [10] mypy-strict          → backend-mypy-strict
#   [11] mypy-extra           → backend-mypy (extra gate)
#   [12] unit-tests           → backend (Tests unit)
#   [13] smoke-check          → backend (Smoke check minimal)
#   [14] pip-audit            → backend (Dependency audit)
#   [15] bandit               → backend (Static security scan)
#   [16] unit-coverage        → backend-unit-coverage (≥85%)
#   [17] integration-smoke    → backend-integration-smoke
#   [18] property-smoke       → backend-property-smoke
#   [19] apps-coverage        → backend-coverage (≥75%)
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
AUTO_SCOPE=false

for arg in "$@"; do
  case "$arg" in
    --full)    MODE="full" ;;
    --quick)   MODE="quick" ;;
    --backend) RUN_FRONTEND=false ;;
    --frontend) RUN_BACKEND=false ;;
    --auto) AUTO_SCOPE=true ;;
    -h|--help)
      echo "用法: $0 [--quick|--full|--backend|--frontend]"
      echo ""
      echo "  --quick      快速检查（默认，不需要数据库）"
      echo "  --full       完整检查（需要 PostgreSQL）"
      echo "  --backend    仅后端检查"
      echo "  --frontend   仅前端检查"
      echo "  --auto       按改动范围自动裁剪后端/前端（pre-push 使用）"
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

# ── 按改动范围自动裁剪后端/前端（--auto，pre-push 使用）────────
apply_auto_scope() {
  [ "$AUTO_SCOPE" = true ] || return 0
  [ -n "$BASE_MERGE" ] || return 0
  local changed has_backend="" has_frontend=""
  changed=$(git -C "$ROOT_DIR" diff --name-only "$BASE_MERGE" HEAD 2>/dev/null || true)
  if echo "$changed" | grep -q '^backend/'; then has_backend=1; fi
  if echo "$changed" | grep -q '^frontend/'; then has_frontend=1; fi
  if [ -n "$has_backend" ] && [ -z "$has_frontend" ]; then
    RUN_FRONTEND=false
    echo -e "${YELLOW}  [auto] 仅后端改动，跳过前端检查${NC}"
  elif [ -z "$has_backend" ] && [ -n "$has_frontend" ]; then
    RUN_BACKEND=false
    echo -e "${YELLOW}  [auto] 仅前端改动，跳过后端检查${NC}"
  elif [ -z "$has_backend" ] && [ -z "$has_frontend" ]; then
    RUN_BACKEND=false
    RUN_FRONTEND=false
    echo -e "${YELLOW}  [auto] 未检出 backend/ 或 frontend/ 改动，跳过全部检查${NC}"
  fi
}
apply_auto_scope

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
#  [0] 护栏通电自检（跨前后端，最先跑，快失败）
# ============================================================
# 防止「写了检查脚本但从不挂进必经链」——没人执行的护栏等于没有护栏，
# 而且还多一份维护税。见 docs/harness/pitfalls.md PIT-001 / PIT-005。
# 纯 Node、无依赖、秒级返回，所以放在所有检查之前当冒烟闸门。
if [ "$RUN_BACKEND" = true ] || [ "$RUN_FRONTEND" = true ]; then
  echo -e "\n${CYAN}╔══════════════════════════════════════════════╗${NC}"
  echo -e "${CYAN}║          护栏通电自检                        ║${NC}"
  echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
  header "0" "护栏通电 (guardrails wired)"
  if command -v node > /dev/null 2>&1 \
    && node "$ROOT_DIR/scripts/check-guardrails-wired.mjs" > /dev/null 2>&1; then
    pass "guardrails-wired"
  elif ! command -v node > /dev/null 2>&1; then
    skip "guardrails-wired（未安装 node）"
  else
    # 失败时重跑一次把明细打到屏幕，避免只看到一行 ✗ 无从下手
    node "$ROOT_DIR/scripts/check-guardrails-wired.mjs" || true
    fail "guardrails-wired"
  fi
fi

# ============================================================
#  [0b] 审批分级跨语言一致性（approval parity）
# ============================================================
# 为什么必跑：approval-gate.ts 的分级规则是服务端 risk.py 的镜像，而它此前
# **从未被真正执行过**（旧检查只是用正则从源码里抠数组比文本）。这条用 Node 的
# 类型剥离直接跑 approval-rules.ts，拿与 Python 测试同一份向量逐条对账，
# 秒级返回且不需要数据库。脚本在 scripts/check-approval-parity.mjs。
if [ "$RUN_BACKEND" = true ]; then
  header "0b" "审批分级跨语言 (approval parity)"
  if ! command -v node > /dev/null 2>&1; then
    skip "approval-parity（未安装 node）"
  elif node "$ROOT_DIR/scripts/check-approval-parity.mjs" 2>&1; then
    pass "approval-parity"
  else
    fail "approval-parity"
  fi
fi

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

  banned=$(git -C "$ROOT_DIR" -c core.quotePath=false ls-files | grep -E '(^|/)(\.DS_Store|__pycache__/|[^/]+\.pyc)$' || true)
  if [ -n "$banned" ]; then
    echo -e "  ${RED}发现禁止追踪的文件:${NC}"; echo "$banned" | sed 's/^/    /'
    _hygiene_ok=false
  fi

  env_tracked=$(git -C "$ROOT_DIR" -c core.quotePath=false ls-files | grep -E '(^|/)\.env(\.[^/]+)?$' | grep -v -E '(^|/)\.env\.example$' || true)
  if [ -n "$env_tracked" ]; then
    echo -e "  ${RED}发现已追踪的 .env 文件:${NC}"; echo "$env_tracked" | sed 's/^/    /'
    _hygiene_ok=false
  fi

  media_tracked=$(git -C "$ROOT_DIR" -c core.quotePath=false ls-files backend/media backend/apiSystem/media 2>/dev/null | grep -v '\.gitkeep$' || true)
  if [ -n "$media_tracked" ]; then
    echo -e "  ${RED}发现已追踪的 media 文件:${NC}"; echo "$media_tracked" | sed 's/^/    /'
    _hygiene_ok=false
  fi

  venv_tracked=$(git -C "$ROOT_DIR" -c core.quotePath=false ls-files | grep -E '^(backend/)?(\.venv|venv(311|312)?)/' || true)
  if [ -n "$venv_tracked" ]; then
    echo -e "  ${RED}发现已追踪的虚拟环境文件:${NC}"; echo "$venv_tracked" | sed 's/^/    /'
    _hygiene_ok=false
  fi

  forbidden_binary=$(git -C "$ROOT_DIR" -c core.quotePath=false ls-files | grep -Ei '^(backend/(apps|apiSystem|scripts)/|scripts/).*\.(onnx|mp4|zip)$' || true)
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

  # [3b] 迁移漂移检查（模型改了却没生成迁移）
  #
  # 为什么单独一道：`agent_kind` 那次真实事故——代码里加了字段、迁移文件也生成了，
  # 但**开发库没跑 migrate**，于是线上表现是「创建会话失败，请稍后重试」，
  # 而日志里才看得到 `column agent_agentsession.agent_kind does not exist`。
  # 前后端 CI 全绿、所有单测全绿（测试库会自己建表），只有真人一点就炸。
  #
  # 两道，缺一不可（都是真实事故的产物）：
  #
  #   3b  「模型改了但没生成迁移文件」→ `makemigrations --check`
  #   3c  「迁移文件在但目标库没应用」→ `migrate --check`
  #
  # 后者是 2026-11-18/19 **连续两次**的真实事故：0016（agent_kind）与 0017
  # （message.agent_kind）都生成了迁移，但开发库没跑 migrate，于是线上表现是
  # 「创建会话失败」与「双答无回答」，日志里才看得到 `column ... does not exist`。
  # 而测试库自己建表 → 单测全绿、CI 全绿，只有真人一点就炸。
  #
  # 3c 需要连库，所以只在库可达时跑（本地开发机 / --full）；CI 里没有持久库，
  # 那侧靠 `make migrate` 的部署纪律兜。
  header "3a" "openapi 产物与代码一致"
  # 产物 backend/openapi.json 是前端 TS 类型的唯一输入，不在必经链上会静默腐烂
  # （实测落后 12 条路径 / 21 个 schema）。CI 侧只在 pull_request 跑（见
  # backend-ci.yml 的 openapi-freshness），本地这侧随时可跑。
  if bash scripts/check-openapi-fresh.sh --json >/dev/null 2>&1; then
    pass "openapi-fresh"
  else
    fail "openapi-fresh（产物落后代码，跑 make openapi-refresh 后重试）"
  fi

  header "3b" "迁移漂移检查 (makemigrations --check)"
  if DB_NAME="${DB_NAME:-test_fachuan_dev}" $BACKEND_PYTHON apiSystem/manage.py makemigrations --check --dry-run 2>&1 | grep -q "No changes detected"; then
    pass "migrations-generated"
  else
    fail "migrations-generated（模型改了但没生成迁移，跑 makemigrations 后重试）"
  fi

  header "3c" "迁移已应用检查 (migrate --check)"
  # 两个坑都要在这一段里避开：
  #   1. 脚本是 `set -euo pipefail`，而 `migrate --check` 在「有未应用迁移」时
  #      **故意**返回非零 —— 不兜住它，整个 ci-local 会在这一步静默中断
  #      （表现为 3c 之后的检查全不跑，比报错更难发现）
  #   2. `grep -q` 在无匹配时返回 1，配合 pipefail 同样会中断
  # 所以：先把输出与返回码捞干净，再纯字符串判断。
  #
  # 用**开发库**（FACHUAN_LOCAL_DB_NAME，缺省 fachuan_dev）而不是 ci-local 顶部
  # export 的 TEST_DB_NAME：后者是 --full 专用的临时库，平时根本没迁移过，
  # 对它做「已应用检查」只会产生噪音。这一道要防的是**开发者自己那个库**漂了。
  _migrate_check_db="${FACHUAN_LOCAL_DB_NAME:-fachuan_dev}"
  _migrate_rc=0
  _migrate_out=$(DB_NAME="$_migrate_check_db" $BACKEND_PYTHON apiSystem/manage.py migrate --check 2>&1) || _migrate_rc=$?
  if [ "$_migrate_rc" -eq 0 ]; then
    pass "migrations-applied"
  else
    case "$_migrate_out" in
      *"could not connect"*|*"Connection refused"*|*"connection refused"*|*"does not exist"*"database"*|*OperationalError*)
        # 库不可达不算错（CI / 无 PG 的机器）：如实跳过，不要假装通过
        skip "migrations-applied（数据库不可连）"
        ;;
      *)
        printf '%s\n' "$_migrate_out" | sed -n '/^\[20/!p' | tail -5
        fail "migrations-applied（目标库有未应用的迁移，跑 manage.py migrate 后重试）"
        ;;
    esac
  fi

  # [4] Pre-commit（对齐 backend job 的 Pre-commit step）
  header "4/22" "Pre-commit hooks (changed files)"
  if [ ! -f "$ROOT_DIR/.pre-commit-config.yaml" ]; then
    skip "pre-commit（无 .pre-commit-config.yaml）"
  elif [ -n "$BASE_MERGE" ]; then
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

  # [8] Mypy curated gate + apps 全量门（对齐 backend job 的 curated gate + full-scan ratchet step）
  # 2026-10-03：apps 全量错误清零后追加全量硬门禁（本地实测 0 错 / 2312 文件 / ~48s）。
  # curated 保留作快速反馈（含 apps 外的 apiSystem/apiSystem/api.py）。
  header "8/22" "Mypy 检查 (curated gate + apps 全量)"
  MYPY_CURATED=(
    apps/core/services/wiring.py
    apps/core/protocols/common/__init__.py
    apps/core/dto/auth.py
    apps/core/infrastructure/throttling.py
    apps/core/exceptions/handlers.py
    apiSystem/apiSystem/api.py
  )
  if PYTHONPATH=apiSystem:. $BACKEND_PYTHON -m mypy --config-file=mypy.ini --follow-imports=silent "${MYPY_CURATED[@]}" 2>&1 \
    && PYTHONPATH=apiSystem:. $BACKEND_PYTHON -m mypy --config-file=mypy.ini apps 2>&1; then
    pass "mypy-curated+full"
  else
    fail "mypy-curated+full"
  fi

  # [9] Structure tests（对齐 backend job 的 Tests structure, real run step）
  # 2026-10-03：从 --full collect-only 升级为默认真跑（实测 ~18s，无需数据库），
  # 让 test_quality_ratchet / four_layer_architecture 等防回潮棘轮在本地
  # make ci 即生效，而不只依赖远端 CI。
  header "9/22" "结构测试 (structure, real run)"
  if $BACKEND_PYTEST -c pytest.ini --no-cov -q tests/ci/structure/ 2>&1; then
    pass "structure-tests"
  else
    fail "structure-tests"
  fi

  if [ "$MODE" = "full" ]; then
    # [10] Mypy strict gate（对齐 backend-mypy-strict job）
    header "10/22" "Mypy 检查 (strict gate)"
    MYPY_STRICT=(
      "${MYPY_CURATED[@]}"
      apps/organization/services/access/organization_access_policy.py
    )
    if PYTHONPATH=apiSystem:. $BACKEND_PYTHON -m mypy --config-file=mypy.ini --follow-imports=silent "${MYPY_STRICT[@]}" 2>&1; then
      pass "mypy-strict"
    else
      fail "mypy-strict"
    fi

    # [11] Mypy extra gate（对齐 backend-myp job）
    header "11/22" "Mypy 检查 (extra gate)"
    MYPY_EXTRA=(
      apps/core/security/auth.py
      apps/core/infrastructure/throttling.py
      apps/core/infrastructure/cache.py
      apps/core/middleware/request_id.py
      apps/core/middleware/security.py
      apps/organization/services/auth/auth_service.py
    )
    if PYTHONPATH=apiSystem:. $BACKEND_PYTHON -m mypy --config-file=mypy.ini --follow-imports=silent "${MYPY_EXTRA[@]}" 2>&1; then
      pass "mypy-extra"
    else
      fail "mypy-extra"
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
    skip "unit-tests（需要 --full）"
    skip "smoke-check（需要 --full）"
    skip "mypy-strict（需要 --full）"
    skip "mypy-extra（需要 --full）"
  fi

  # [14] pip-audit（对齐 backend job 的 Dependency audit step）
  # 豁免清单单一来源：backend/devtools/pip-audit-ignores.txt（与 backend-ci.yml 同源）。
  # 此处不再硬编码副本——历史上两份清单各自维护，devtools 新增豁免后脚本副本必然落后，
  # 导致本地 push 被已豁免的 advisory 拦下（v27.8.5 的 Pillow 批次即踩到此坑）。
  # 末尾 LOCAL_ONLY_AUDIT_IGNORES 是本地 TRAE 污染 python 底盘的构建工具漏洞，
  # CI 干净环境扫不到，故只在本脚本追加、不进 devtools 清单。
  header "14/22" "依赖安全审计 (pip-audit)"
  LOCAL_ONLY_AUDIT_IGNORES="PYSEC-2026-3721 PYSEC-2026-3447"
  # 仅当本次有依赖文件变更时才扫描，避免每次 push 白跑网络请求；网络抖动自动重试一次
  _pip_audit_invoke() {
    local ignore_file="$ROOT_DIR/backend/devtools/pip-audit-ignores.txt"
    local ignore_args=""
    if [ -f "$ignore_file" ]; then
      # 与 backend-ci.yml 完全一致的解析方式：跳过注释/空行，取第 1 列
      ignore_args="$(grep -Ev '^[[:space:]]*(#|$)' "$ignore_file" \
        | awk -F' *[|] *' '{printf "--ignore-vuln %s ", $1}')"
    else
      echo "  ⚠ 未找到 ${ignore_file}，仅使用本地专属豁免"
    fi
    local local_args=""
    local vuln_id
    for vuln_id in $LOCAL_ONLY_AUDIT_IGNORES; do
      local_args="$local_args--ignore-vuln $vuln_id "
    done
    # shellcheck disable=SC2086
    $BACKEND_PYTHON -m pip_audit $ignore_args $local_args 2>&1
  }
  DEP_CHANGED=false
  if [ -n "$BASE_MERGE" ]; then
    if git -C "$ROOT_DIR" diff --name-only "$BASE_MERGE" HEAD 2>/dev/null \
      | grep -qE '(^|/)(pyproject\.toml|uv\.lock|requirements[^/]*\.(txt|pip)|Pipfile(\..*)?)$'; then
      DEP_CHANGED=true
    fi
  else
    DEP_CHANGED=true
  fi
  if [ "$DEP_CHANGED" = false ]; then
    skip "pip-audit（无依赖文件变更）"
  elif _pip_audit_invoke; then
    pass "pip-audit"
  else
    echo "  pip-audit 失败（疑似网络抖动），重试一次..."
    if _pip_audit_invoke; then pass "pip-audit"; else fail "pip-audit"; fi
  fi

  # [15] Bandit（对齐 backend job 的 Static security scan step）
  # 2026-10-03：-lll 存量清零后升级为 -ll（MEDIUM 以上全拦）
  header "15/22" "静态安全扫描 (bandit)"
  if $BACKEND_PYTHON -m bandit -r apps -q -ll -x "*/migrations/*,*/static/*,*/staticfiles/*,*/media/*,*/venv*/*,*/htmlcov/*" 2>&1; then
    pass "bandit"
  else
    fail "bandit"
  fi

  if [ "$MODE" = "full" ]; then
    # [16] Unit coverage（对齐 backend-unit-coverage job）
    header "16/22" "单元测试覆盖率 (≥85%)"
    if $BACKEND_PYTEST -c pytest.ini \
      -o addopts="--import-mode=importlib -q --tb=short --strict-markers --timeout=60" \
      --reuse-db \
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
    #
    # 参数必须与 workflow 一致：CI 用
    #   pytest -c pytest.ini -o "addopts=--reuse-db ... --timeout=60"
    # 早期这里只传 --no-cov，于是本地每次重建全库、且沿用 30s 默认超时，
    # 建表阶段就 Timeout 报错——看起来像测试挂了，实际是脚本与 CI 不同步。
    header "17/22" "集成测试 (integration smoke)"
    if $BACKEND_PYTEST -c pytest.ini \
        -o "addopts=--reuse-db --import-mode=importlib -q --tb=short --strict-markers --timeout=60" \
        --no-cov -q tests/ci/integration/ 2>&1; then
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
    # 2026-10-03：覆盖率棘轮 75 → 78（当前实测 83.41，余量充足）
    header "19/22" "全局覆盖率基线 (≥78%)"
    if $BACKEND_PYTEST -c pytest.ini \
      -o addopts="--import-mode=importlib -q --tb=short --strict-markers --timeout=60" \
      --reuse-db \
      --cov=apps \
      --cov-report=term-missing --cov-fail-under=78 \
      tests/ci/unit/ 2>&1; then
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
