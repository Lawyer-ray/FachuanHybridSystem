#!/usr/bin/env bash
#
# OpenAPI 产物与代码一致性检查（护栏）
#
# ## 为什么需要它（PIT：没人执行的护栏等于没有护栏）
#
# `backend/openapi.json` 是前端类型 `frontend/src/types/api-schema.d.ts` 的**唯一输入**。
# 它不在任何必经链上，于是长期静默腐烂：2026-11-21 实测一次导出发现它落后
# **12 条路径 + 21 个 schema**（其中 3 个 schema 是改名，前端类型里仍是旧名）。
#
# 腐烂的后果不是构建变红，而是「类型看起来对、运行时字段不存在」——TS 只会相信
# 生成物，不会替你验证后端。这条护栏就是让漂移在 PR 阶段暴露。
#
# ## 用法
#
#   bash scripts/check-openapi-fresh.sh            # 检查（有漂移 → 退出码 1）
#   bash scripts/check-openapi-fresh.sh --write    # 刷新两个产物（openapi.json + TS 类型）
#   bash scripts/check-openapi-fresh.sh --json     # 机器可读摘要
#
# ## 为什么只查 pull_request，不在 push 到 main 时查
#
# 现存漂移是历史欠账。如果这个检查也跑在 push 到 main 上，main 会立刻变红，而修它
# 需要一次「纯产物刷新」提交。所以 CI 侧限定 `if: github.event_name == 'pull_request'`：
# main 保持绿，下一份 PR 起就必须自证产物是新的（见 backend-ci.yml 的 openapi-freshness）。
#
# ## 不做的事
#
# 不启动服务、不连库、不跑迁移：`export_openapi_schema` 只导入路由并 dump schema。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$REPO_ROOT/backend"
ARTIFACT="$BACKEND/openapi.json"
TS_TYPES="$REPO_ROOT/frontend/src/types/api-schema.d.ts"
PY="$BACKEND/.venv/bin/python"

MODE="check"
case "${1:-}" in
  --write) MODE="write" ;;
  --json) MODE="json" ;;
  --help | -h)
    sed -n '1,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  "") ;;
  *)
    echo "未知参数：$1（可用：--write / --json / --help）" >&2
    exit 2
    ;;
esac

if [ ! -x "$PY" ]; then
  echo "找不到后端虚拟环境 $PY —— 先 cd backend && uv sync" >&2
  exit 2
fi

TMP_JSON="$(mktemp -t openapi-fresh-XXXXXX.json)"
trap 'rm -f "$TMP_JSON"' EXIT

# 导出当前代码树的 schema。不连库：路由注册是纯导入行为。
( cd "$BACKEND" && env DJANGO_SETTINGS_MODULE=apiSystem.settings PYTHONPATH=apiSystem:. \
    "$PY" apiSystem/manage.py export_openapi_schema --out "$TMP_JSON" >/dev/null )

# 用 python 比对并输出人话摘要（比 jq 少一个依赖，且能列出具体路径）。
SUMMARY="$("$PY" - "$TMP_JSON" "$ARTIFACT" <<'PY'
import json
import sys

fresh_path, committed_path = sys.argv[1], sys.argv[2]
with open(fresh_path, encoding="utf-8") as handle:
    fresh = json.load(handle)
try:
    with open(committed_path, encoding="utf-8") as handle:
        committed = json.load(handle)
except FileNotFoundError:
    print('MISSING\t-\t-\t-\t-\t-')
    raise SystemExit(0)

fp, cp = set(fresh.get("paths", {})), set(committed.get("paths", {}))
fs = set(fresh.get("components", {}).get("schemas", {}))
cs = set(committed.get("components", {}).get("schemas", {}))
added_paths, removed_paths = sorted(fp - cp), sorted(cp - fp)
added_schemas, removed_schemas = sorted(fs - cs), sorted(cs - fs)
drift = bool(added_paths or removed_paths or added_schemas or removed_schemas)

print(f"{'DRIFT' if drift else 'OK'}\t{len(added_paths)}\t{len(removed_paths)}\t{len(added_schemas)}\t{len(removed_schemas)}\t{len(fp)}")
for path in added_paths[:20]:
    print(f"ADD_PATH\t{path}")
for path in removed_paths[:20]:
    print(f"DEL_PATH\t{path}")
for name in added_schemas[:20]:
    print(f"ADD_SCHEMA\t{name}")
for name in removed_schemas[:20]:
    print(f"DEL_SCHEMA\t{name}")
PY
)"

STATUS="$(printf '%s' "$SUMMARY" | head -1 | cut -f1)"
ADD_PATHS="$(printf '%s' "$SUMMARY" | head -1 | cut -f2)"
DEL_PATHS="$(printf '%s' "$SUMMARY" | head -1 | cut -f3)"
ADD_SCHEMAS="$(printf '%s' "$SUMMARY" | head -1 | cut -f4)"
DEL_SCHEMAS="$(printf '%s' "$SUMMARY" | head -1 | cut -f5)"
TOTAL_PATHS="$(printf '%s' "$SUMMARY" | head -1 | cut -f6)"

if [ "$MODE" = "json" ]; then
  printf '{"status":"%s","added_paths":%s,"removed_paths":%s,"added_schemas":%s,"removed_schemas":%s,"total_paths":%s}\n' \
    "$STATUS" "$ADD_PATHS" "$DEL_PATHS" "$ADD_SCHEMAS" "$DEL_SCHEMAS" "$TOTAL_PATHS"
  [ "$STATUS" = "OK" ] && exit 0 || exit 1
fi

if [ "$STATUS" = "OK" ]; then
  echo "✅ openapi 产物与代码一致（$TOTAL_PATHS 条路径）"
  exit 0
fi

if [ "$STATUS" = "MISSING" ]; then
  echo "❌ 缺少 backend/openapi.json。生成方式：bash scripts/check-openapi-fresh.sh --write" >&2
  exit 1
fi

echo "❌ openapi 产物与代码不一致（代码有、产物没有 / 或反过来的）"
echo "   新增路径 $ADD_PATHS 条 / 删除路径 $DEL_PATHS 条 / 新增 schema $ADD_SCHEMAS 个 / 删除 schema $DEL_SCHEMAS 个"
printf '%s' "$SUMMARY" | tail -n +2 | sed 's/^ADD_PATH/   + 路径/; s/^DEL_PATH/   - 路径/; s/^ADD_SCHEMA/   + 类型/; s/^DEL_SCHEMA/   - 类型/'

if [ "$MODE" = "write" ]; then
  echo
  echo "→ 刷新产物…"
  cp "$TMP_JSON" "$ARTIFACT" 2>/dev/null || cp "$TMP_JSON" "$ARTIFACT"
  echo "   backend/openapi.json 已更新"
  if [ -d "$REPO_ROOT/frontend/node_modules" ]; then
    ( cd "$REPO_ROOT/frontend" && npx --no-install openapi-typescript ../backend/openapi.json -o src/types/api-schema.d.ts >/dev/null )
    echo "   frontend/src/types/api-schema.d.ts 已更新"
  else
    echo "   ⚠️ frontend/node_modules 不存在，跳过 TS 类型生成；请先在 frontend 下 pnpm install 后执行："
    echo "      cd frontend && npx openapi-typescript ../backend/openapi.json -o src/types/api-schema.d.ts"
  fi
  echo
  echo "✅ 已刷新。请把两个产物文件与本次代码改动放在同一个提交里。"
  exit 0
fi

cat >&2 <<'EOF'

修复方式（一条命令刷新两个产物）：
    bash scripts/check-openapi-fresh.sh --write

只刷新后端快照：
    cd backend && .venv/bin/python apiSystem/manage.py export_openapi_schema

注意：产物是「代码 → 快照」的单向生成物，**不要手改**；刷新提交里不要混入无关代码改动。
EOF
exit 1
