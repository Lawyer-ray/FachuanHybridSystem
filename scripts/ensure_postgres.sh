#!/usr/bin/env bash
# ============================================================
# ensure_postgres.sh — 确保 PostgreSQL 可连接，必要时自动诊断并自愈
#
# 背景（2026-10-11 事故）：Mac 关机流程被打断时，PostgreSQL 的优雅关闭
# 未完成即断电，残留 postmaster.pid 锁文件。重启后该 PID 可能被系统
# 复用给无关进程，PostgreSQL 自带的死锁文件检测（kill(pid,0) 探活）
# 无法识别 PID 已易主，导致 launchd 每 10 秒重试全部撞死在
# "lock file postmaster.pid already exists"，后端 migrate 连接被拒。
#
# 自愈动作（仅对「本机 + brew 安装」的 PostgreSQL 生效）：
#   1. postmaster.pid 记录的 PID 已死，或属于非 postgres 进程（PID 复用）
#      → 删除过期锁文件
#   2. brew 服务处于 error / stopped → restart
#
# 接入点：backend/Makefile 的 migrate 目标（覆盖 run-dev / qcluster 等）、
#         根 Makefile 的 start / prod-restart（公网栈）。
#
# 用法: bash scripts/ensure_postgres.sh
# 环境变量覆盖（测试 / 特殊部署用）:
#   PG_HOST / PG_PORT      连接目标（默认读 backend/.env，兜底 127.0.0.1:5432）
#   PG_DATA_DIR            postmaster.pid 所在数据目录（默认按 brew 服务自动发现）
#   PG_SERVICE             brew 服务名（默认自动发现 postgresql@*）
#   ENSURE_PG_TIMEOUT      自愈后等待就绪的秒数（默认 30）
#   ENSURE_PG_DRY_RUN=1    只诊断，不执行删除 / 重启
#
# 注意：本脚本需兼容 macOS 自带 bash 3.2 —— 变量一律用 ${VAR} 花括号，
#       避免 $VAR 紧跟全角字符时多字节尾部被误并入变量名（unbound variable）。
# ============================================================
set -uo pipefail

GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'; RED=$'\033[0;31m'; NC=$'\033[0m'
log()  { echo "[ensure_postgres] $*"; }
ok()   { log "${GREEN}✓${NC} $*"; }
warn() { log "${YELLOW}⚠${NC} $*"; }
fail() { log "${RED}✗${NC} $*"; }

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TIMEOUT="${ENSURE_PG_TIMEOUT:-30}"

# ---------- 连接目标解析：环境变量 > backend/.env > 默认值 ----------
PG_HOST="${PG_HOST:-}"
PG_PORT="${PG_PORT:-}"
if [[ -z "${PG_HOST}" || -z "${PG_PORT}" ]]; then
  ENV_FILE="${REPO_ROOT}/backend/.env"
  if [[ -f "${ENV_FILE}" ]]; then
    [[ -z "${PG_HOST}" ]] && PG_HOST=$(grep -E '^DB_HOST=' "${ENV_FILE}" | tail -1 | cut -d= -f2 | tr -d '[:space:]')
    [[ -z "${PG_PORT}" ]] && PG_PORT=$(grep -E '^DB_PORT=' "${ENV_FILE}" | tail -1 | cut -d= -f2 | tr -d '[:space:]')
  fi
fi
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-5432}"

# ---------- 探活：优先 pg_isready（能识别 rejecting），兜底 bash /dev/tcp ----------
is_ready() {
  if command -v pg_isready >/dev/null 2>&1; then
    pg_isready -h "${PG_HOST}" -p "${PG_PORT}" -t 2 >/dev/null 2>&1
  else
    (exec 3<>"/dev/tcp/${PG_HOST}/${PG_PORT}") >/dev/null 2>&1 && exec 3>&- 3<&-
  fi
}

if is_ready; then
  exit 0  # 正常启动的快速路径：静默通过，零噪音
fi

log "PostgreSQL 未就绪（${PG_HOST}:${PG_PORT}），开始诊断…"

# ---------- 远程数据库只等待、不自愈（无法安全操作远端机器） ----------
if [[ "${PG_HOST}" != "127.0.0.1" && "${PG_HOST}" != "localhost" && "${PG_HOST}" != "::1" ]]; then
  warn "目标 ${PG_HOST} 非本机，跳过自愈，仅等待 ${TIMEOUT}s…"
  for _ in $(seq 1 "${TIMEOUT}"); do is_ready && { ok "已就绪"; exit 0; }; sleep 1; done
  fail "远程 PostgreSQL ${PG_HOST}:${PG_PORT} 一直未就绪，请检查远端服务"
  exit 1
fi

# ---------- 发现 brew 服务与数据目录 ----------
if ! command -v brew >/dev/null 2>&1; then
  fail "未安装 Homebrew，无法自动诊断，请手动检查 PostgreSQL 状态"
  exit 1
fi

BREW_PREFIX="$(brew --prefix)"
# brew services list 的列是空格对齐（非制表符），必须用 awk 按字段解析
if [[ -z "${PG_SERVICE:-}" ]]; then
  PG_SERVICE=$(brew services list 2>/dev/null | tail -n +2 | awk '$1 ~ /^postgres/ {print $1; exit}')
fi
if [[ -z "${PG_SERVICE:-}" ]]; then
  fail "未发现 brew 管理的 PostgreSQL 服务（brew services list），请手动启动数据库"
  exit 1
fi
PG_STATUS=$(brew services list 2>/dev/null | awk -v s="${PG_SERVICE}" '$1==s {print $2; exit}')
log "brew 服务: ${PG_SERVICE}（状态: ${PG_STATUS:-未知}）"

PG_DATA_DIR="${PG_DATA_DIR:-}"
if [[ -z "${PG_DATA_DIR}" ]]; then
  for candidate in "${BREW_PREFIX}/var/${PG_SERVICE}" "${BREW_PREFIX}/var/postgres" "${BREW_PREFIX}/var/postgresql"; do
    if [[ -f "${candidate}/PG_VERSION" ]]; then PG_DATA_DIR="${candidate}"; break; fi
  done
fi
if [[ -z "${PG_DATA_DIR}" || ! -d "${PG_DATA_DIR}" ]]; then
  warn "未定位数据目录（尝试 ${BREW_PREFIX}/var/${PG_SERVICE} 等），跳过锁文件检查，仅重启服务"
else
  log "数据目录: ${PG_DATA_DIR}"
fi

# ---------- 诊断 postmaster.pid：PID 已死 / 被无关进程复用 = 过期锁文件 ----------
STALE_REASON=""
check_stale_pid() {
  local pid_file="$1" pid comm
  [[ -f "${pid_file}" ]] || return 1
  pid=$(head -n 1 "${pid_file}" 2>/dev/null | tr -d '[:space:]')
  [[ "${pid}" =~ ^[0-9]+$ ]] || { STALE_REASON="锁文件内容异常（首行非 PID: '${pid}'）"; return 0; }
  comm=$(ps -p "${pid}" -o comm= 2>/dev/null | xargs || true)
  if [[ -z "${comm}" ]]; then
    STALE_REASON="记录的 PID ${pid} 已不存在"
  elif [[ "${comm}" != *postgres* ]]; then
    # 正是 2026-10-11 事故形态：重启后 PID 被复用（当时是 HomeWidget），
    # PostgreSQL 自身 kill(pid,0) 探活被骗过，必须按进程名复核
    STALE_REASON="记录的 PID ${pid} 已被无关进程复用（${comm}）"
  else
    return 1  # 确有 postmaster 存活，锁文件有效，不许删
  fi
  return 0
}

DRY_RUN="${ENSURE_PG_DRY_RUN:-0}"
NEED_RESTART=0

if [[ -n "${PG_DATA_DIR:-}" ]] && check_stale_pid "${PG_DATA_DIR}/postmaster.pid"; then
  warn "发现过期 postmaster.pid：${STALE_REASON}"
  if [[ "${DRY_RUN}" == "1" ]]; then
    log "[dry-run] 将删除 ${PG_DATA_DIR}/postmaster.pid 并重启 ${PG_SERVICE}"
  else
    rm -f "${PG_DATA_DIR}/postmaster.pid" && ok "已删除过期锁文件 postmaster.pid"
    NEED_RESTART=1
  fi
elif [[ -n "${PG_DATA_DIR:-}" && -f "${PG_DATA_DIR}/postmaster.pid" ]]; then
  log "postmaster.pid 有效（postmaster 仍在运行），不动锁文件"
fi

# ---------- 执行自愈 ----------
if [[ "${DRY_RUN}" != "1" ]]; then
  if [[ "${NEED_RESTART}" == "1" || "${PG_STATUS:-}" != "started" ]]; then
    action="restart"; [[ "${PG_STATUS:-}" == "stopped" ]] && action="start"
    if brew services "${action}" "${PG_SERVICE}" >/dev/null 2>&1; then
      ok "已 brew services ${action} ${PG_SERVICE}"
    else
      fail "brew services ${action} ${PG_SERVICE} 失败"
      exit 1
    fi
  else
    # 服务名义上 started 但未就绪：先容忍慢启动，不行再强制重启一次
    log "服务状态 started 但未就绪，先等待慢启动…"
    for _ in $(seq 1 8); do is_ready && { ok "已就绪（慢启动）"; exit 0; }; sleep 1; done
    warn "等待 8s 仍未就绪，强制重启一次"
    brew services restart "${PG_SERVICE}" >/dev/null 2>&1 && ok "已强制重启 ${PG_SERVICE}"
  fi

  log "等待就绪（最长 ${TIMEOUT}s）…"
  for _ in $(seq 1 "${TIMEOUT}"); do is_ready && { ok "PostgreSQL 已恢复: ${PG_HOST}:${PG_PORT}"; exit 0; }; sleep 1; done

  fail "自愈后仍无法连接 ${PG_HOST}:${PG_PORT}，请查看日志定位："
  log_file="${BREW_PREFIX}/var/log/${PG_SERVICE}.log"
  [[ -f "${log_file}" ]] && tail -n 5 "${log_file}" | sed 's/^/    /'
  exit 1
fi
log "[dry-run] 诊断结束，未做任何变更（服务状态: ${PG_STATUS:-未知}）"
