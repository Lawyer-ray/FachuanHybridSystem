#!/usr/bin/env bash
#
# 仓库内全部 CLAUDE.md 自动备份
#
# 起因（2026-10-27）：`backend/CLAUDE.md` 随 backend/ 误清空丢失。CLAUDE.md 全族被
# .gitignore 忽略、git 里没有——它是各 AI 会话的规范权威（四层架构、迁移纪律、
# 子模块 PR 流程……），丢失只能靠翻历史会话转录碰运气找回。本次是从 10-25 的
# Claude 转录里挖回来的，不能再赌第二次。
#
# 与 backup-env.sh 的差异：备份对象是**一组**文件（自动发现仓库内所有 CLAUDE.md，
# 新增子目录规范文件自动纳入），且**源文件丢失也能恢复**——restore 按「备份里存在
# 的文件」逐一还原，不依赖源文件还在。
#
# 用法：
#   scripts/backup-claude-md.sh            # 备份（内容未变的文件跳过）
#   scripts/backup-claude-md.sh --force    # 强制备份
#   scripts/backup-claude-md.sh --list     # 列出各文件的备份份数与最近时间
#   scripts/backup-claude-md.sh --restore  # 每个文件从各自最近一份还原（先另存 .before-restore）
#
# 已挂 crontab（每天 9:35，紧随 backup-env.sh 之后）。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${FACHUAN_CLAUDE_MD_BACKUP_DIR:-$HOME/.fachuan-backups/claude-md}"
KEEP=20
# 备份名里目录分隔符的转义（backend/CLAUDE.md → backend__CLAUDE.md）
SEP_REPL="__"

die() { echo "✗ $*" >&2; exit 1; }
info() { echo "$*"; }

# 相对路径（repo 内）⇄ 备份文件名前缀
prefix_of() { printf '%s' "${1#/}" | sed "s|/|$SEP_REPL|g"; }
path_of() { printf '%s' "$1" | sed "s|$SEP_REPL|/|g"; }

discover_sources() {
  { find "$REPO_ROOT" -name 'CLAUDE.md' -type f \
      -not -path '*/node_modules/*' \
      -not -path '*/.venv/*' \
      -not -path '*/.git/*' \
      -not -path '*/dist/*' \
      -not -path '*/.claude/*' \
      2>/dev/null
    # harness 叶子（2026-10-30 索引改造）：CLAUDE.md 的细则已拆到 docs/harness/，
    # 同样不入 git（docs/ 被忽略），必须一并备份，否则丢失后无从恢复。
    if [ -d "$REPO_ROOT/docs/harness" ]; then
      find "$REPO_ROOT/docs/harness" -name '*.md' -type f 2>/dev/null
    fi
  } | sort
}

ensure_dir() {
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
}

latest_backup_of() { # $1 = 备份前缀
  ls -1t "$BACKUP_DIR/$1".bak-* 2>/dev/null | head -1 || true
}

list_backups() {
  ensure_dir
  if ! compgen -G "$BACKUP_DIR"/*.bak-* >/dev/null; then
    info "（暂无备份）"
    return 0
  fi
  # 按前缀归组：prefix.bak-<ts>。不用管道喂 while——子 shell 里 found 传不出来
  local pfx name cnt last
  while read -r pfx; do
    name="$(basename "$pfx")"
    cnt="$(ls -1 "$BACKUP_DIR/$name".bak-* 2>/dev/null | wc -l | tr -d ' ')"
    last="$(latest_backup_of "$name")"
    printf "%-40s %2s 份  最近 %s\n" "$(path_of "$name")" "$cnt" "$(basename "${last:-无}")"
  done < <(ls -1 "$BACKUP_DIR"/*.bak-* 2>/dev/null | sed 's|\.bak-[^-]*-[^-]*$||' | sort -u)
}

do_backup() {
  ensure_dir
  local srcs
  srcs="$(discover_sources)"
  [ -n "$srcs" ] || die "仓库内没有发现任何 CLAUDE.md（REPO_ROOT=$REPO_ROOT 是否正确？）"

  local n=0 skipped=0
  while read -r src; do
    local rel pfx last dest
    rel="${src#"$REPO_ROOT"/}"
    pfx="$(prefix_of "$rel")"
    n=$((n + 1))

    last="$(latest_backup_of "$pfx")"
    if [ "${1:-}" != "--force" ] && [ -n "$last" ] && cmp -s "$src" "$last"; then
      skipped=$((skipped + 1))
      continue
    fi

    dest="$BACKUP_DIR/$pfx.bak-$(date +%Y%m%d-%H%M%S)"
    cp "$src" "$dest"
    chmod 600 "$dest"
    info "✓ $rel → $(basename "$dest")"

    # 每个文件各自只保留最近 KEEP 份
    # 注意用完整 if：裸 `[ ] && ...` 求值为假会让循环以非零退出，set -e 直接杀脚本
    local i=0
    ls -1t "$BACKUP_DIR/$pfx".bak-* 2>/dev/null | while read -r f; do
      i=$((i + 1))
      if [ "$i" -gt "$KEEP" ]; then
        rm -f "$f"
        info "  清理旧备份 $(basename "$f")"
      fi
    done
  done <<<"$srcs"

  info "完成：$n 个文件，$skipped 个内容未变跳过，$((n - skipped)) 个新备份"
}

do_restore() {
  ensure_dir
  if ! compgen -G "$BACKUP_DIR"/*.bak-* >/dev/null; then
    die "没有可还原的备份"
  fi
  # 同上：process substitution 避免子 shell，any 才能传出循环
  local any=0 pfx
  while read -r pfx; do
    local rel src last
    rel="$(path_of "$(basename "$pfx")")"
    src="$REPO_ROOT/$rel"
    last="$(latest_backup_of "$(basename "$pfx")")"
    [ -n "$last" ] || continue
    any=1

    # 现存文件先另存，绝不静默覆盖（可能与备份内容已不同——比如刚做过手工修补）
    if [ -f "$src" ]; then
      local keep="$src.before-restore-$(date +%Y%m%d-%H%M%S)"
      cp "$src" "$keep"
      info "当前 $rel 已另存 → $(basename "$keep")"
    fi

    mkdir -p "$(dirname "$src")"
    cp "$last" "$src"
    info "✓ 已从 $(basename "$last") 还原 → $rel"
  done < <(ls -1 "$BACKUP_DIR"/*.bak-* 2>/dev/null | sed 's|\.bak-[^-]*-[^-]*$||' | sort -u)
  [ "$any" -eq 1 ] || die "备份目录里没有可还原的文件"
}

case "${1:-}" in
  --list) list_backups ;;
  --restore) do_restore ;;
  --force) do_backup --force ;;
  "") do_backup ;;
  *) die "未知参数：$1（可用：--list / --restore / --force）" ;;
esac
