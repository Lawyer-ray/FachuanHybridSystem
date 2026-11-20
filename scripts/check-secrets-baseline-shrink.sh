#!/usr/bin/env bash
# 兜底护栏：backend/.secrets.baseline 被整份删除 >100 行 或 results 被清空 → 立刻失败。
#
# 背景（详见 docs/harness/backend/infra.md「detect-secrets 把基线整份清空」一节）：
#   detect-secrets v1.5.0 的 `detect-secrets-hook --baseline FILE` 会**原地写回**基线，
#   用「本次扫描的 filelist」去 trim 基线，扫不到的条目整条删掉。一次普通提交就能把
#   2896 行削到 146 行（`"results": {}`），而 `results: {}` 会让历史豁免全部失效，
#   之后每一次提交都被“Potential secrets about to be committed”挡住。
#
# 这条护栏是**第二道防线**：主修法是 scripts/detect_secrets_readonly.py（把基线变成
# 钩子的只读输入）。若将来有人把钩子改回 `--baseline` 直连、或有人手工 `detect-secrets scan`
# 把基线重刷坏了，这里会立刻拦下并给出还原命令。
#
# 用法：
#   bash scripts/check-secrets-baseline-shrink.sh          # 退出码 0/1
#   ALLOW_SECRETS_BASELINE_SHRINK=1 bash ...               # 有意重刷基线时放行
#   SECRETS_BASELINE_MAX_SHRINK=0 bash ...                 # 任何净删除都算（更严）
#
# 判据（任一成立即失败）：
#   1. `git diff HEAD --numstat -- backend/.secrets.baseline` 的删除行数 > 阈值（默认 100）
#   2. 工作区基线 `"results": {}`（零条目）而 HEAD 版本有条目
set -uo pipefail

BASELINE="backend/.secrets.baseline"
MAX_SHRINK="${SECRETS_BASELINE_MAX_SHRINK:-100}"

cd "$(dirname "$0")/.." || exit 0

if [ "${ALLOW_SECRETS_BASELINE_SHRINK:-0}" = "1" ]; then
    echo "check-secrets-baseline-shrink: ALLOW_SECRETS_BASELINE_SHRINK=1，跳过（有意重刷基线）"
    exit 0
fi

if ! git rev-parse --git-dir >/dev/null 2>&1; then
    exit 0
fi

if [ ! -f "$BASELINE" ]; then
    echo "check-secrets-baseline-shrink: $BASELINE 不存在，跳过"
    exit 0
fi

fail() {
    echo ""
    echo "=============================================================="
    echo " check-secrets-baseline-shrink: 基线被批量删除，已阻止"
    echo "=============================================================="
    echo " $1"
    echo ""
    echo " 还原：git checkout -- $BASELINE"
    echo " 确认：wc -l $BASELINE   # 应为 ~2879 行，且 \"results\" 非空"
    echo ""
    echo " 如果这是有意重刷基线（例如新增审计过的误报条目），用："
    echo "   ALLOW_SECRETS_BASELINE_SHRINK=1 git commit ..."
    echo "=============================================================="
    exit 1
}

# ---- 判据 1：净删除行数 ----
numstat=$(git diff HEAD --numstat -- "$BASELINE" 2>/dev/null || true)
deleted=$(printf '%s\n' "$numstat" | awk -v f="$BASELINE" '$3 == f {print $2; exit}')
case "${deleted:-}" in
    '' | '-' | *[!0-9]*) deleted=0 ;;
esac

if [ "$deleted" -gt "$MAX_SHRINK" ]; then
    fail "本次改动删除了 ${deleted} 行（阈值 ${MAX_SHRINK}）。"
fi

# ---- 判据 2：results 被清空（哪怕行数没超阈，也是致命的）----
now_entries=$(grep -c '"hashed_secret"' "$BASELINE" 2>/dev/null || true)
case "${now_entries:-}" in
    '' | *[!0-9]*) now_entries=0 ;;
esac

if [ "$now_entries" -eq 0 ]; then
    head_entries=$(git show "HEAD:$BASELINE" 2>/dev/null | grep -c '"hashed_secret"' || true)
    case "${head_entries:-}" in
        '' | *[!0-9]*) head_entries=0 ;;
    esac
    if [ "$head_entries" -gt 0 ]; then
        fail "工作区基线的 \"results\" 已空（0 条），HEAD 里有 $head_entries 条 —— 历史豁免会全部失效。"
    fi
fi

exit 0
