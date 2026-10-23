#!/usr/bin/env bash
# 共享 MCP 运维命令（make mcp / mcp-status / mcp-logs / mcp-verify 的实现）。
#
# 为什么需要它：mcp_server 的工具注册表是**进程启动时快照**——改了代码
# （新增/删除工具）不重启共享 MCP，pi 拿到的还是旧工具面，且**没有任何
# 报错**，只表现为模型说「没有这个工具」（apps/agent/README §10 实测教训）。
# 本脚本把「杀旧 → 拉新 → 工具面核对」固化成一条命令，核对不过就非零退出。
#
# 用法（也可直接 bash scripts/shared_mcp.sh <子命令>，须在 backend/ 下）：
#   restart  杀旧拉新 + 自动 verify（默认）
#   status   进程/端口/运行时长/日志路径
#   logs     跟随日志（tail -f）
#   verify   只核对：运行中的工具面 vs 代码注册表（MCP 真握手，非端口探测）
#   stop     只停不启
#
# 兼容 macOS bash 3.2：不用关联数组；变量引用一律 ${VAR}（避免后跟全角字符）。

set -u

# ── 基础路径（脚本在根 scripts/，后端在 ../backend）──────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(dirname "${SCRIPT_DIR}")/backend"
PYTHON_BIN="${BACKEND_DIR}/.venv/bin/python"
[ -x "${PYTHON_BIN}" ] || PYTHON_BIN="$(command -v python3 || echo python3)"

# ── 端口/主机解析：环境变量 > backend/.env > 默认（与 shared_mcp.py 同名同序）──
MCP_PORT="${FACHUAN_MCP_HTTP_PORT:-}"
MCP_HOST="${FACHUAN_MCP_HTTP_HOST:-}"
if [ -z "${MCP_PORT}" ] || [ -z "${MCP_HOST}" ]; then
  ENV_FILE="${BACKEND_DIR}/.env"
  if [ -f "${ENV_FILE}" ]; then
    [ -z "${MCP_PORT}" ] && MCP_PORT="$(grep -E '^FACHUAN_MCP_HTTP_PORT=' "${ENV_FILE}" | tail -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
    [ -z "${MCP_HOST}" ] && MCP_HOST="$(grep -E '^FACHUAN_MCP_HTTP_HOST=' "${ENV_FILE}" | tail -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
  fi
fi
MCP_PORT="${MCP_PORT:-8011}"
MCP_HOST="${MCP_HOST:-127.0.0.1}"
LOG_DIR="${TMPDIR:-/tmp}"
LOG_FILE="${LOG_DIR%/}/fachuan-shared-mcp-${MCP_PORT}.log"

# ── 小工具 ─────────────────────────────────────────────────────────────────
pids_on_port() {
  lsof -nP -ti tcp:"${MCP_PORT}" -sTCP:LISTEN 2>/dev/null || true
}

port_open() {
  lsof -nP -i tcp:"${MCP_PORT}" -sTCP:LISTEN >/dev/null 2>&1
}

say() { printf '[mcp] %s\n' "$*"; }
die() { printf '[mcp] 错误: %s\n' "$*" >&2; exit 1; }

# ── 子命令 ─────────────────────────────────────────────────────────────────
cmd_status() {
  local pids
  pids="$(pids_on_port)"
  say "endpoint  : http://${MCP_HOST}:${MCP_PORT}/mcp"
  say "日志      : ${LOG_FILE}"
  if [ -z "${pids}" ]; then
    say "进程      : 未运行（Django 下次用到 agent 时会自动拉起，或跑 make mcp）"
    return 0
  fi
  for pid in ${pids}; do
    local elapsed cmd
    elapsed="$(ps -o etime= -p "${pid}" 2>/dev/null | tr -d ' ' || echo '?')"
    cmd="$(ps -o command= -p "${pid}" 2>/dev/null || echo '?')"
    say "进程      : PID ${pid} · 已运行 ${elapsed}"
    say "  ↳ ${cmd}"
  done
  say "核对工具面: make mcp-verify"
}

cmd_stop() {
  local pids
  pids="$(pids_on_port)"
  if [ -z "${pids}" ]; then
    say "没有运行中的共享 MCP（端口 ${MCP_PORT}），无需停止"
    return 0
  fi
  say "停止 ${pids}（先 TERM，5 秒后仍存活则 KILL）"
  kill ${pids} 2>/dev/null || true
  local i
  for i in 1 2 3 4 5; do
    port_open || { say "已停止"; return 0; }
    sleep 1
  done
  pids="$(pids_on_port)"
  [ -n "${pids}" ] && kill -9 ${pids} 2>/dev/null || true
  sleep 0.5
  port_open && die "强杀后端口仍被占用，请人工检查: lsof -nP -i tcp:${MCP_PORT}" || { say "已停止（强杀）"; return 0; }
}

cmd_start() {
  port_open && { say "端口 ${MCP_PORT} 已有进程在监听，跳过启动（如需换新代码请先 stop/restart）"; return 0; }
  say "拉起共享 MCP（日志: ${LOG_FILE}）"
  (
    cd "${BACKEND_DIR}" || exit 1
    nohup env FACHUAN_MCP_TRANSPORT=streamable-http \
      FACHUAN_MCP_HTTP_HOST="${MCP_HOST}" \
      FACHUAN_MCP_HTTP_PORT="${MCP_PORT}" \
      "${PYTHON_BIN}" -m mcp_server >>"${LOG_FILE}" 2>&1 &
  )
  local i
  for i in $(seq 1 30); do
    port_open && { say "端口就绪（等待 ${i}s 内）"; return 0; }
    sleep 1
  done
  die "30 秒内端口未就绪，看日志排障: tail -50 ${LOG_FILE}"
}

# verify：MCP 真握手取线上工具面，与代码注册表逐名对比。
# registry 侧复刻 mcp_server/__main__ 的引导（sys.path/settings/stdout 改道）。
# bootstrap 的 Django INFO 日志走 stderr，被暂存到临时文件——只在失败（rc=2，
# 握手/注册表异常）时附带输出帮助排障；成功与漂移（rc=1）路径保持干净。
cmd_verify() {
  local err_tmp rc
  err_tmp="$(mktemp)"
  (
    cd "${BACKEND_DIR}" || exit 2
    "${PYTHON_BIN}" - "${MCP_HOST}" "${MCP_PORT}" <<'PYEOF' 2>"${err_tmp}"
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent if "__file__" in dir() else Path.cwd()
# heredoc 里 __file__ 未定义，用 cwd（脚本约定在 backend/ 下运行）
BACKEND = Path.cwd()
for p in (str(BACKEND / "apiSystem"), str(BACKEND)):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

import django

_real_stdout = sys.stdout
sys.stdout = sys.stderr  # bootstrap 日志改道（与 __main__ 同法）
try:
    django.setup()
finally:
    sys.stdout = _real_stdout

HOST, PORT = sys.argv[1], sys.argv[2]
URL = f"http://{HOST}:{PORT}/mcp"


def registry_tools() -> list[str]:
    from mcp_server.server import mcp

    return sorted(t.name for t in asyncio.run(mcp.list_tools()))


async def live_tools() -> list[str]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(URL) as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            return sorted(t.name for t in (await session.list_tools()).tools)


def main() -> int:
    try:
        reg = registry_tools()
    except Exception as exc:  # noqa: BLE001
        print(f"[verify] 注册表枚举失败: {exc}", file=sys.stderr)
        return 2
    try:
        live = asyncio.run(live_tools())
    except Exception as exc:  # noqa: BLE001
        print(f"[verify] 线上握手失败: {exc}")
        print(f"[verify] 端口 {PORT} 可能未就绪，或被非 MCP 进程占用（lsof -nP -i tcp:{PORT}）")
        return 2

    reg_set, live_set = set(reg), set(live)
    missing = sorted(reg_set - live_set)
    extra = sorted(live_set - reg_set)
    print(f"[verify] 代码注册表: {len(reg)} 个工具 · 线上: {len(live)} 个工具")
    if missing:
        print(f"[verify] 线上缺失 {len(missing)} 个（代码有、线上无 → 旧进程，跑 make mcp 重启）:")
        for name in missing:
            print(f"    - {name}")
    if extra:
        print(f"[verify] 线上多出 {len(extra)} 个（线上有、代码无 → 代码回退后未重启）:")
        for name in extra:
            print(f"    - {name}")
    if not missing and not extra:
        print("[verify] 工具面一致 ✅")
        return 0
    return 1


sys.exit(main())
PYEOF
  )
  rc=$?
  if [ "${rc}" -eq 2 ]; then
    local detail
    detail="$(grep -v ' INFO - ' "${err_tmp}" | tail -15)"
    if [ -n "${detail}" ]; then
      echo "[verify] --- stderr 异常栈尾部（bootstrap INFO 已省略）---" >&2
      echo "${detail}" >&2
    fi
  fi
  rm -f "${err_tmp}"
  return "${rc}"
}

cmd_restart() {
  cmd_stop
  cmd_start
  say "核对工具面…"
  if cmd_verify; then
    say "重启完成，工具面与代码一致"
  else
    die "工具面核对未通过（见上方输出）——新进程可能没起来或注册表异常，排障: tail -50 ${LOG_FILE}"
  fi
}

case "${1:-restart}" in
  restart) cmd_restart ;;
  status) cmd_status ;;
  logs)
    [ -f "${LOG_FILE}" ] || die "日志不存在: ${LOG_FILE}（还没启动过？）"
    say "跟随 ${LOG_FILE}（Ctrl+C 退出）"
    tail -n 200 -f "${LOG_FILE}"
    ;;
  verify) cmd_verify || die "工具面核对未通过" ;;
  stop) cmd_stop ;;
  *) die "未知子命令: $1（可用: restart/status/logs/verify/stop）" ;;
esac
