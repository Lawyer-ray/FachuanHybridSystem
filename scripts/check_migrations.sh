#!/usr/bin/env bash
# 迁移三道闸门 —— 开 PR 前必须全绿（`make pr-ready` 会调它）。
#
# 为什么需要三道（都是真实事故的产物）：
#   ① 模型改了但没生成迁移文件      → 在开发机上是「字段不存在」的 500
#   ② 迁移文件在但目标库没应用      → 同样的 500，而且**单测/CI 全绿**
#      （测试库自己建表），只有真人一点就炸：2026-11-18/19 连撞两次
#      （0016 agent_kind、0017 message.agent_kind），2026-11-21 第三次
#      （0023 decision_reason）。
#   ③ 多个会话在同一分支各加一个迁移 → 出现多个 leaf（分支冲突），
#      `migrate` 直接 CommandError。本项目**允许多个 AI 并行改同一分支**，
#      所以这道不能省；它纯读迁移图，不需要数据库。
#
# 用法：
#   ./scripts/check_migrations.sh              # 用 DB_NAME（缺省 fachuan_dev）
#   DB_NAME=test_fachuan_dev ./scripts/check_migrations.sh
#   SKIP_APPLIED=1 ./scripts/check_migrations.sh   # 只跑 ①③（库不可达时）
#   ONLY=graph ./scripts/check_migrations.sh       # 只跑 ③（ci-local 的 3d 用）
#
# 退出码：0 = 全绿；1 = 有红项（逐条打印怎么修）。
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
PY="$BACKEND_DIR/.venv/bin/python"
MANAGE="$BACKEND_DIR/apiSystem/manage.py"
DB_NAME="${DB_NAME:-${FACHUAN_LOCAL_DB_NAME:-fachuan_dev}}"
ONLY="${ONLY:-all}"

if [ ! -x "$PY" ]; then
  echo "❌ 找不到 $PY（先在 backend 里跑 uv sync）" >&2
  exit 1
fi

cd "$BACKEND_DIR" || exit 1
failed=0

step() { printf '\n\033[36m▶ %s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓ %s\033[0m\n' "$1"; }
bad()  { printf '  \033[31m✗ %s\033[0m\n' "$1"; failed=$((failed + 1)); }
skip() { printf '  \033[33m– %s\033[0m\n' "$1"; }

# ── ① 模型改了但没生成迁移文件 ────────────────────────────────────────────
if [ "$ONLY" != "graph" ]; then
step "① 迁移文件是否齐全（makemigrations --check）"
out=$(DB_NAME="${DB_NAME}" "$PY" "$MANAGE" makemigrations --check --dry-run 2>&1)
if printf '%s' "$out" | grep -q "No changes detected"; then
  ok "模型与迁移文件一致"
else
  printf '%s\n' "$out" | sed -n '/^\[20/!p' | tail -8
  bad '模型改了但没生成迁移 —— 在 backend 里跑 manage.py makemigrations 并提交'
fi
fi

# ── ② 迁移文件在但目标库没应用 ────────────────────────────────────────────
if [ "$ONLY" != "graph" ]; then
step "② 迁移是否已应用到目标库（migrate --check，库=${DB_NAME}）"
if [ "${SKIP_APPLIED:-0}" = "1" ]; then
  skip "SKIP_APPLIED=1，跳过"
else
  rc=0
  out=$(DB_NAME="${DB_NAME}" "$PY" "$MANAGE" migrate --check 2>&1) || rc=$?
  if [ "$rc" -eq 0 ]; then
    ok "目标库没有未应用的迁移"
  else
    case "$out" in
      *"could not connect"*|*"Connection refused"*|*"connection refused"*|*OperationalError*|*"does not exist"*)
        skip '数据库不可连（CI 容器正常）—— 部署侧必须跑 manage.py migrate'
        ;;
      *)
        printf '%s\n' "$out" | sed -n '/^\[20/!p' | tail -8
        bad "目标库有未应用的迁移 —— 跑 cd backend/apiSystem && DB_NAME=${DB_NAME} ../.venv/bin/python manage.py migrate"
        ;;
    esac
  fi
fi
fi

# ── ③ 同一 app 多个 leaf（并行会话各加一个迁移的典型冲突）────────────────
step "③ 迁移图是否有分支冲突（每个 app 只能有一个 leaf）"
graph_out=$("$PY" - <<'PY' 2>&1
import os
import sys

sys.path.insert(0, "apiSystem")
sys.path.insert(0, ".")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
import django

django.setup()
from django.db.migrations.loader import MigrationLoader

# connection=None：只读磁盘上的迁移文件，不连数据库（CI quick 也能跑）
loader = MigrationLoader(None, ignore_no_migrations=True)
leaves = sorted(loader.graph.leaf_nodes())
by_app: dict[str, list[str]] = {}
for app, name in leaves:
    by_app.setdefault(app, []).append(name)
conflicts = {app: names for app, names in by_app.items() if len(names) > 1}
if conflicts:
    for app, names in conflicts.items():
        print(f"{app}: {', '.join(names)}")
    sys.exit(1)
print(f"{len(leaves)} leaves / {len(by_app)} apps · 无分支冲突")
PY
)
rc=$?
# Django 启动日志也走 stdout：只取我们自己那行摘要/冲突行，别把 INFO 当结论
summary=$(printf '%s\n' "$graph_out" | grep -E '^[0-9]+ leaves' | tail -1)
if [ "$rc" -eq 0 ]; then
  ok "${summary:-迁移图无分支冲突}"
else
  printf '%s\n' "$graph_out" | grep -E '^[a-z_]+: ' | tail -8
  bad '迁移图有多个 leaf（并行会话各建了一个迁移）—— 跑 manage.py makemigrations --merge 合并后提交'
fi

printf '\n'
total=3
[ "$ONLY" = "graph" ] && total=1
if [ "$failed" -eq 0 ]; then
  printf '\033[32m全部通过（%d/%d）\033[0m\n' "$total" "$total"
  exit 0
fi
printf '\033[31m%d 项红 —— 修完再开 PR（见上）\033[0m\n' "$failed"
exit 1
