#!/usr/bin/env bash
#
# backend/.env 自动备份
#
# 起因（2026-10-27）：`backend/` 被误清空，`.env` 因被 .gitignore 忽略而无法从
# git 恢复——里面既有数据库口令，也有 **CREDENTIAL_ENCRYPTION_KEY**（Fernet 主密钥）。
# 主密钥丢失意味着数据库里所有 `enc:v1:` 密文永久解不开：OnlyOffice JWT、邮箱
# 密码、飞书/企业微信 secret、PaddleOCR/企查查/天眼查 token 全部作废。
# 最终是靠 ~/.fachuan-backups/ 里一个多月前的旧备份才救回来，纯属侥幸。
#
# 用法：
#   scripts/backup-env.sh            # 备份（内容未变则跳过，不堆垃圾）
#   scripts/backup-env.sh --force    # 强制备份
#   scripts/backup-env.sh --list     # 列出已有备份
#   scripts/backup-env.sh --restore  # 从最近一份还原（原文件先另存 .env.before-restore）
#
# 建议挂到 crontab（每天 9:30）：
#   30 9 * * * cd /path/to/repo && scripts/backup-env.sh >/dev/null 2>&1

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO_ROOT/backend/.env"
BACKUP_DIR="${FACHUAN_ENV_BACKUP_DIR:-$HOME/.fachuan-backups}"
KEEP=20

die() { echo "✗ $*" >&2; exit 1; }
info() { echo "$*"; }

ensure_dir() {
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
}

list_backups() {
  ensure_dir
  if ! compgen -G "$BACKUP_DIR/.env.bak-*" >/dev/null; then
    info "（暂无备份）"
    return 0
  fi
  ls -1t "$BACKUP_DIR"/.env.bak-* | while read -r f; do
    printf "%s  %6s bytes\n" "$(basename "$f")" "$(wc -c <"$f" | tr -d ' ')"
  done
}

latest_backup() {
  ls -1t "$BACKUP_DIR"/.env.bak-* 2>/dev/null | head -1
}

do_backup() {
  [ -f "$SRC" ] || die "源文件不存在：$SRC"
  ensure_dir

  # 内容未变就跳过：备份的价值在「有变化的历史」，不是每天一份全同副本。
  local last
  last="$(latest_backup || true)"
  if [ -n "$last" ] && cmp -s "$SRC" "$last"; then
    info "✓ 内容与最近备份一致，跳过（$(basename "$last")）"
    return 0
  fi

  local dest="$BACKUP_DIR/.env.bak-$(date +%Y%m%d-%H%M%S)"
  cp "$SRC" "$dest"
  chmod 600 "$dest"
  info "✓ 已备份 → $dest"

  # 只保留最近 KEEP 份
  local n=0
  ls -1t "$BACKUP_DIR"/.env.bak-* 2>/dev/null | while read -r f; do
    n=$((n + 1))
    if [ "$n" -gt "$KEEP" ]; then rm -f "$f" && info "  清理旧备份 $(basename "$f")"; fi
  done

  # 软校验：加密主密钥是否还在（丢了它 = 数据库密文全废）
  if grep -q '^CREDENTIAL_ENCRYPTION_KEY=.\+' "$SRC"; then
    info "  ✓ 含 CREDENTIAL_ENCRYPTION_KEY"
  else
    echo "  ⚠ 警告：CREDENTIAL_ENCRYPTION_KEY 为空——数据库内 enc:v1: 密文将无法解密" >&2
  fi
}

do_restore() {
  ensure_dir
  local last
  last="$(latest_backup || true)"
  [ -n "$last" ] || die "没有可还原的备份"

  if [ -f "$SRC" ]; then
    local keep="$SRC.before-restore-$(date +%Y%m%d-%H%M%S)"
    cp "$SRC" "$keep"
    chmod 600 "$keep"
    info "当前 .env 已另存 → $keep"
  fi

  cp "$last" "$SRC"
  chmod 600 "$SRC"
  info "✓ 已从 $(basename "$last") 还原到 $SRC"
}

case "${1:-}" in
  --list) list_backups ;;
  --restore) do_restore ;;
  --force) do_backup ;;
  "") do_backup ;;
  *) die "未知参数：$1（可用：--list / --restore / --force）" ;;
esac
