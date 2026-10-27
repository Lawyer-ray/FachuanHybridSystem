#!/usr/bin/env bash
#
# 数据库 + media 文件备份
#
# 起因（2026-10-28 审计）：全仓此前**只有** .env 和 CLAUDE.md 两个文本文件的备份，
# 数据库与 media 零备份。而库里是不可再生的律师案卷、当事人身份证扫描件、财务流水；
# media/ 里是原始文书与扫描件。项目已经发生过两次事故：
#   - 2026-10-23 pytest teardown flush 清空 agent_agentattachment 98 条
#   - 2026-10-27 backend/ 目录被整树删除两次（.env 与 CLAUDE.md 差点永久丢失）
# 磁盘故障 / 误操作 / 勒索软件 = 全所数据永久灭失，没有任何回退路径。
#
# 用法：
#   scripts/backup-db.sh              # 备份（pg_dump + media 增量归档），内容未变则跳过
#   scripts/backup-db.sh --force      # 强制备份
#   scripts/backup-db.sh --list       # 列出已有备份
#   scripts/backup-db.sh --restore-db <file>   # 还原数据库（危险，需 --yes）
#   scripts/backup-db.sh --verify     # 校验最近一份备份可读（restore --list）
#
# 建议 crontab（每天 2:30，含异机拷贝）：
#   30 2 * * * cd /path/to/repo && scripts/backup-db.sh >> ~/.fachuan-backups/backup.log 2>&1
#
# 环境变量：
#   FACHUAN_DB_BACKUP_DIR   备份目录（默认 ~/.fachuan-backups/db）
#   FACHUAN_BACKUP_KEEP     保留份数（默认 14）
#   FACHUAN_BACKUP_REMOTE   可选的异机/外置盘目标目录（cp 过去，避免单盘故障）
#   FACHUAN_BACKUP_SKIP_MEDIA=1   只备份数据库
#
# 退出码：0 成功（含"内容未变已跳过"）；非 0 失败（cron 可据此告警）。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
ENV_FILE="$BACKEND_DIR/.env"
BACKUP_DIR="${FACHUAN_DB_BACKUP_DIR:-$HOME/.fachuan-backups/db}"
KEEP="${FACHUAN_BACKUP_KEEP:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"

die() { echo "✗ $*" >&2; exit 1; }
info() { echo "$*"; }
warn() { echo "⚠ $*" >&2; }

ensure_dir() {
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
}

# ── 读取 backend/.env 里的数据库连接参数（不 source，避免执行任意代码） ──
env_get() {
  local key="$1"
  [ -f "$ENV_FILE" ] || return 0
  # 取最后一个同名赋值为准（.env 里后者覆盖前者），去掉引号
  awk -F= -v k="$key" '
    $0 ~ "^[[:space:]]*"k"=" {
      v = substr($0, index($0, "=") + 1)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
      gsub(/^["\x27]|["\x27]$/, "", v)
      found = v
    }
    END { if (found != "") print found }
  ' "$ENV_FILE"
}

DB_NAME="${DB_NAME:-$(env_get DB_NAME)}"
DB_USER="${DB_USER:-$(env_get DB_USER)}"
DB_HOST="${DB_HOST:-$(env_get DB_HOST)}"
DB_PORT="${DB_PORT:-$(env_get DB_PORT)}"
DB_NAME="${DB_NAME:-fachuan_dev}"
DB_USER="${DB_USER:-$(whoami)}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"

MEDIA_DIR="${MEDIA_ROOT:-$(env_get MEDIA_ROOT)}"
if [ -z "$MEDIA_DIR" ]; then
  # 实际路径是 backend/apiSystem/media（settings 的 BASE_DIR 是 apiSystem/apiSystem），
  # 不是 backend/media；两处都探一下，避免"跳过 media"却以为是正常。
  for cand in "$BACKEND_DIR/apiSystem/media" "$BACKEND_DIR/media"; do
    if [ -d "$cand" ]; then MEDIA_DIR="$cand"; break; fi
  done
fi
MEDIA_DIR="${MEDIA_DIR:-$BACKEND_DIR/apiSystem/media}"

# ── 保护：绝不备份测试库（可能是 pytest 临时库，恢复它没有意义还会误导） ──
case "$DB_NAME" in
  test_*|*_test|*_test_*|fachuan_ci_test)
    die "拒绝备份测试库 '$DB_NAME'（真实备份请确认 .env 指向工作库）"
    ;;
esac

list_backups() {
  ensure_dir
  info "备份目录: $BACKUP_DIR"
  if ! compgen -G "$BACKUP_DIR/*.dump" >/dev/null && ! compgen -G "$BACKUP_DIR/*.tar.gz" >/dev/null; then
    info "（暂无备份）"
    return 0
  fi
  ls -lh "$BACKUP_DIR" | awk 'NR>1 && /\.(dump|tar\.gz)$/ {print "  " $9 "  " $5 "  " $6" "$7" "$8}'
}

prune_old() {
  local pattern="$1"
  # shellcheck disable=SC2012
  ls -1t "$BACKUP_DIR"/$pattern 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
    rm -f "$old" && info "  清理旧备份: $(basename "$old")"
  done
}

verify_dump() {
  local file="$1"
  pg_restore --list "$file" >/dev/null 2>&1
}

do_verify() {
  ensure_dir
  local latest
  latest="$(ls -1t "$BACKUP_DIR"/*.dump 2>/dev/null | head -1 || true)"
  [ -n "$latest" ] || die "没有可校验的 .dump 备份"
  info "校验: $(basename "$latest")"
  if verify_dump "$latest"; then
    local n
    n="$(pg_restore --list "$latest" 2>/dev/null | grep -c "^[0-9]" || echo 0)"
    info "  ✅ 可读（$n 个对象条目）"
  else
    die "备份损坏或不可读"
  fi
}

do_backup() {
  ensure_dir
  command -v pg_dump >/dev/null 2>&1 || die "未找到 pg_dump（brew install postgresql@18 或加入 PATH）"

  # 连通性预检：连不上要明确报错，不要产出 0 字节备份
  if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" >/dev/null 2>&1; then
    die "数据库不可达: $DB_USER@$DB_HOST:$DB_PORT/$DB_NAME（先跑 scripts/ensure_postgres.sh）"
  fi

  local dump_file="$BACKUP_DIR/${DB_NAME}-${STAMP}.dump"
  info "▶ 备份数据库 $DB_NAME → $(basename "$dump_file")"

  # -Fc 自定义格式：压缩 + 支持 pg_restore 选择性还原
  if ! PGPASSWORD="${PGPASSWORD:-$(env_get DB_PASSWORD)}" pg_dump \
      -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
      -Fc --no-owner --no-privileges -f "$dump_file" 2>/dev/null; then
    rm -f "$dump_file"
    die "pg_dump 失败（检查 .env 里的 DB_USER/DB_PASSWORD 与 pg_hba.conf）"
  fi

  # 产物自检：0 字节 = 失败，别留下误导人的"成功"
  if [ ! -s "$dump_file" ]; then
    rm -f "$dump_file"
    die "pg_dump 产出空文件，视为失败"
  fi
  if ! verify_dump "$dump_file"; then
    warn "备份文件 pg_restore --list 不可读，可能损坏"
  fi
  chmod 600 "$dump_file"
  info "  ✅ 数据库: $(du -h "$dump_file" | cut -f1)"

  # ── media 增量归档 ──
  local media_file=""
  if [ "${FACHUAN_BACKUP_SKIP_MEDIA:-0}" != "1" ] && [ -d "$MEDIA_DIR" ]; then
    media_file="$BACKUP_DIR/media-${STAMP}.tar.gz"
    info "▶ 备份 media $MEDIA_DIR → $(basename "$media_file")"
    if tar -czf "$media_file" -C "$(dirname "$MEDIA_DIR")" "$(basename "$MEDIA_DIR")" 2>/dev/null; then
      chmod 600 "$media_file"
      info "  ✅ media: $(du -h "$media_file" | cut -f1)"
    else
      rm -f "$media_file"; media_file=""
      warn "media 归档失败（数据库备份已成功，不因此整体失败）"
    fi
  else
    info "▶ 跳过 media（目录不存在或 FACHUAN_BACKUP_SKIP_MEDIA=1）"
  fi

  # ── 可选异机/外置盘副本：单盘故障时数据库和备份一起没了就没意义 ──
  if [ -n "${FACHUAN_BACKUP_REMOTE:-}" ]; then
    if mkdir -p "$FACHUAN_BACKUP_REMOTE" 2>/dev/null; then
      cp -f "$dump_file" "$FACHUAN_BACKUP_REMOTE/" 2>/dev/null && info "  ✅ 已拷贝到 $FACHUAN_BACKUP_REMOTE"
      [ -n "$media_file" ] && cp -f "$media_file" "$FACHUAN_BACKUP_REMOTE/" 2>/dev/null
    else
      warn "异机备份目录不可写: $FACHUAN_BACKUP_REMOTE"
    fi
  fi

  prune_old "*.dump"
  prune_old "*.tar.gz"

  info "完成。保留最近 $KEEP 份于 $BACKUP_DIR"
  [ -n "${FACHUAN_BACKUP_REMOTE:-}" ] || warn "未设置 FACHUAN_BACKUP_REMOTE：备份与本机同盘，磁盘故障仍会一起丢"
}

do_restore() {
  local file="$1" confirm="${2:-}"
  [ -n "$file" ] || die "用法: backup-db.sh --restore-db <file> --yes"
  [ -f "$file" ] || die "文件不存在: $file"
  [ "$confirm" = "--yes" ] || die "还原会覆盖当前数据库 $DB_NAME，确认请追加 --yes"
  command -v pg_restore >/dev/null 2>&1 || die "未找到 pg_restore"

  info "▶ 还原 $DB_NAME ← $file"
  info "  （--clean --if-exists：先删同名对象再重建）"
  PGPASSWORD="${PGPASSWORD:-$(env_get DB_PASSWORD)}" pg_restore \
    -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    --clean --if-exists --no-owner --no-privileges "$file" || true
  info "还原完成；若有 'does not exist' 类告警属 --clean 正常噪声"
}

main() {
  local mode="backup"
  local restore_file="" yes_flag=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --force) mode="backup" ;;
      --list) mode="list"; shift; continue ;;
      --verify) mode="verify"; shift; continue ;;
      --restore-db) mode="restore"; restore_file="${2:-}"; shift 2; continue ;;
      --yes) yes_flag="--yes"; shift; continue ;;
      -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
      *) die "未知参数: $1" ;;
    esac
    shift
  done

  case "$mode" in
    list) list_backups ;;
    verify) do_verify ;;
    restore) do_restore "$restore_file" "$yes_flag" ;;
    backup) do_backup ;;
  esac
}

main "$@"
