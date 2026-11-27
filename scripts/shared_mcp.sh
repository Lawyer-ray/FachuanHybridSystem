#!/usr/bin/env bash
# 共享 MCP 运维命令（make mcp / mcp-status / mcp-logs / mcp-verify / mcp-fingerprint /
# mcp-bluegreen 的实现）。
#
# 为什么需要它：mcp_server 的工具注册表是**进程启动时快照**——改了代码
# （新增/删除工具、改描述、改参数 schema）不重启共享 MCP，pi 拿到的还是旧工具面，
# 且**没有任何报错**，只表现为模型说「没有这个工具」（apps/agent/README §10 实测教训）。
# 本脚本把「杀旧 → 拉新 → 工具面核对」固化成一条命令，核对不过就非零退出。
#
# 用法（也可直接 bash scripts/shared_mcp.sh <子命令>，任意目录可运行——脚本
# 按自身路径自解析仓库位置）：
#   restart [--if-stale]   杀旧拉新 + 自动 verify（默认）；--if-stale 时工具面没变就跳过
#   bluegreen [--if-stale] [--drain N]
#                          零停机切换：候选与旧实例并存 → side 端口真握手 →
#                          旧实例 SIGTERM 退休。**默认强制切**：指纹只覆盖注册元数据
#                          （名字/描述/schema/注解），**看不见「只改实现」**，而只改实现
#                          恰恰是最常见的一类变更 —— 所以默认不按指纹跳过，--if-stale 才跳过
#   status                 进程/端口/运行时长/日志路径
#   logs                   跟随日志（tail -f）
#   verify [--port N]      只核对：运行中的工具面 vs 代码注册表（MCP 真握手，非端口探测）；
#                          线上与代码的**指纹**不同也非零退出（工具名全对但描述/schema 变了）
#   fingerprint            打印代码侧（离线）工具面指纹
#   stop                   只停不启
#
# 为什么 restart 之外还要 bluegreen：restart 的「杀旧 → 起新」之间有几十秒空窗
# （Django 冷启动 + 440+ 个工具模块导入），期间任何 agent 工具调用都直接失败。
# `python -m mcp_server` 在 HTTP 模式下用 SO_REUSEPORT 显式建监听，于是切换可以做成
# 「新实例先就位、旧实例后退休」：候选与旧实例**同时**绑 primary 端口、两边都能服务，
# 新连接的切换因此是原子的（不存在「两个都挂着」或「谁都没挂着」的空窗）。
# 就绪校验必须打 side 端口——primary 的新连接会在新旧实例间分摊（Linux 按 4 元组分流，
# macOS 可能「后 bind 者优先」），拿它判「候选起来了吗」可能打到旧进程，给出**假通过**；
# side 端口只有一个监听者，结论确定。顺序不能反：side 校验过了才让旧实例退休。
#
# 并发保护：bluegreen 与 restart 全程持一把**跨进程**锁（mkdir 原子锁，目录名带端口），
# 同一端口同一时刻只允许一个改运行态的操作，第二个立刻拒绝并打印持有者 pid。
# 没有它，两条并发蓝绿会挑到同一个 side 端口、双双「通过」side 校验，最后把两个候选
# 永久双绑在 primary 上（冒烟实测：2 个 LISTEN，且此后没有任何人会来收尾）。
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

# 候选实例的 side 端口（只有它自己在听，见文件头「为什么打 side 端口」）。只在
# bluegreen 期间用。起点默认 primary+1，可用 FACHUAN_MCP_SIDE_PORT 改；但**起点不是
# 死命令**——蓝绿每次都会重新挑一个当前空闲的端口（见 pick_side_port），因为上一轮
# 胜出的候选会一直听到它自己死，写死一个端口等于蓝绿只能成功一次。
MCP_SIDE_PORT="${FACHUAN_MCP_SIDE_PORT:-$((MCP_PORT + 1))}"
# side 端口的挑选宽度：从起点往后这么多个端口里取第一个空闲的。
MCP_SIDE_PORT_SPAN=20

# 蓝绿切换发给**候选**实例的 drain 上限（秒）。240 覆盖一次 200 秒的长工具调用
# （apps/agent/backends/toolface/constants.py 的 TOOL_TIMEOUT_SECONDS）。
# 注意它只对这个候选生效：正在服务的旧实例的 drain 是**它自己**启动时定下的。
BLUEGREEN_DRAIN="${FACHUAN_MCP_GRACEFUL_TIMEOUT:-240}"

# ── 小工具 ─────────────────────────────────────────────────────────────────
pids_on_port() {
  lsof -nP -ti tcp:"${1:-${MCP_PORT}}" -sTCP:LISTEN 2>/dev/null || true
}

port_open() {
  lsof -nP -i tcp:"${1:-${MCP_PORT}}" -sTCP:LISTEN >/dev/null 2>&1
}

say() { printf '[mcp] %s\n' "$*"; }
die() { printf '[mcp] 错误: %s\n' "$*" >&2; exit 1; }

# ── 跨进程运维互斥锁（同一端口同一时刻只允许一个改运行态的操作）────────────
# 为什么必须互斥：cmd_bluegreen 的每条判据都建立在「只有我在改运行态」这个前提上。
# 两条并发 bluegreen 会看到同一个 side 端口「空着」（pick_side_port 的判据就是「当前
# 没人听」），而 side socket 带 SO_REUSEPORT，候选 B 绑上 A 正在听的端口**不报错**；
# 两边的 `verify --port side` 还可能各自打到对方而「通过」——于是双方都 SIGTERM 旧
# 实例（第二刀打空）、都把候选留在 primary 上，之后无人收尾（primary 永久 2 个 LISTEN）。
# 为什么用 mkdir 而不是 flock(1)：macOS 只带 bash 3.2，系统里没有 flock(1)；mkdir 的
# 「不存在才创建」是 POSIX 规定必须原子的，失败即「已有人持有」，判据干净且无外部依赖。
# 为什么锁放 ${TMPDIR:-/tmp} 且文件名带端口：不进仓库，也不进 launchctl 或本脚本自己
# 会清的目录——锁要是被重启顺手清掉，互斥就形同虚设。
OP_LOCK_DIR="${LOG_DIR%/}/fachuan-mcp-op-${MCP_PORT}.lock"
OP_LOCK_HELD=0
# 蓝绿候选的 pid 与「要不要由 trap 收掉它」：候选用 nohup 起，脚本死了它不跟着死，
# 所以被打断时必须主动杀；但「旧实例已交出监听」之后候选是**唯一**服务者，再杀它就
# 等于把共享 MCP 打空——那一刻把开关关掉，只保留锁的清理。
OP_CAND_PID=""
OP_CAND_REAP=0

# 锁目录里的持有者 pid（缺失/不可读/非数字一律回显空 → 调用方按陈旧锁处理）。
op_lock_owner() {
  head -1 "${OP_LOCK_DIR}/owner" 2>/dev/null | tr -cd '0-9'
}

# 试一次 mkdir 抢锁。返回 0=拿到 / 1=目录已存在（没抢到）/ 2=抢到了但回读不是自己。
op_lock_try_mkdir() {
  mkdir "${OP_LOCK_DIR}" 2>/dev/null || return 1
  # 写 owner 是第二步（mkdir 之后）：它只用于「持有者还活着吗」的判断，写失败不算
  # 抢锁失败——下一个来的人会把它当陈旧锁，靠 mkdir 的原子性兜底。
  printf '%s\n' "$$" >"${OP_LOCK_DIR}/owner" 2>/dev/null || true
  # 抢到后回读确认锁里写的仍是自己：上面「清陈旧锁」可能与另一个正在 mkdir 的进程
  # 交错（它 mkdir 成功、owner 还没落地时被我们当陈旧清掉，它随后写 owner 写了个空）。
  # 确认不过就当场失败——宁可让人重跑一条命令，也不能带着一把假锁去改运行态。
  if [ "$(op_lock_owner)" != "$$" ]; then
    OP_LOCK_HELD=0
    return 2
  fi
  OP_LOCK_HELD=1
  return 0
}

# 拿运维锁：拿不到就读 owner 判持有者死活；已死/owner 缺失算陈旧锁，清掉后只重试一次
# （不循环重试：清完还抢不到说明真有人刚抢到，循环只会变成活锁）。
acquire_op_lock() {
  local owner rc
  op_lock_try_mkdir
  rc=$?
  if [ "${rc}" -eq 0 ]; then
    say "已持有运维锁（pid $$，锁目录: ${OP_LOCK_DIR}）"
    return 0
  fi
  [ "${rc}" -eq 2 ] && die "抢锁后回读确认失败（锁目录被别的进程清掉/改写）: ${OP_LOCK_DIR}；请重跑一次；仍失败就人工检查这个目录"
  owner="$(op_lock_owner)"
  if [ -z "${owner}" ]; then
    # owner 是 mkdir 成功后的第二步：留 0.2 秒给并发者写完，仍然缺失才判陈旧
    # （否则「刚 mkdir 完、owner 还没落地」会被误清）。
    sleep 0.2
    owner="$(op_lock_owner)"
  fi
  if [ -n "${owner}" ] && kill -0 "${owner}" 2>/dev/null; then
    die "另有一个 MCP 运维操作正在进行（pid ${owner}），请等它结束；确认它是否真在跑: ps -p ${owner} -o pid=,etime=,command="
  fi
  say "发现陈旧锁（owner=${owner:-缺失}，该进程已不存在；多半是上次被 kill -9 或机器重启），清掉后重试一次"
  rm -rf "${OP_LOCK_DIR}"
  op_lock_try_mkdir
  rc=$?
  if [ "${rc}" -ne 0 ]; then
    owner="$(op_lock_owner)"
    die "抢不到 MCP 运维锁: ${OP_LOCK_DIR}（当前持有者 pid ${owner:-未知}）—— 有别的运维操作正在开始，等它结束后重试"
  fi
  say "已持有运维锁（pid $$，锁目录: ${OP_LOCK_DIR}）"
}

# 释放（幂等）：trap 会被调用多次，靠 OP_LOCK_HELD 挡住重复 rm。
release_op_lock() {
  [ "${OP_LOCK_HELD}" -eq 1 ] || return 0
  OP_LOCK_HELD=0
  rm -rf "${OP_LOCK_DIR}" 2>/dev/null || true
}

# 挑本次蓝绿用的 side 端口（结果写回全局 MCP_SIDE_PORT）。
#
# 为什么必须「挑」而不是「占了就中止」：候选把 side 端口绑到**进程结束**（uvicorn
# 拿两个 socket 跑到底，见 mcp_server/__main__），而蓝绿成功后候选**就是**新的服务
# 实例 —— 于是上一轮的 side 端口必然被这一轮的旧实例占着。「占用即中止」等于蓝绿
# 只能成功一次，第二次敲 make mcp-bluegreen 会直接死在端口检查上。
#
# 规则（起点 start = 显式值或 primary+1）：
#   ① 没设 FACHUAN_MCP_SIDE_PORT：从 primary+1 往后 MCP_SIDE_PORT_SPAN 个端口里取
#      第一个没人听的；整段都被占才中止。
#   ② 设了且端口空着：就用它（配置优先）。
#   ③ 设了但有人听：监听者全属于 old_pids（= 当前服务实例，蓝绿预期残留）→ 从
#      start+1 起顺延挑；监听者里有无关进程 → 中止（不抢别人的端口，改配置要人决定）。
#
# 为什么不能靠「候选 bind 失败」兜底：side 监听 socket 也带 SO_REUSEPORT，候选**能**
# 绑上别人正在听的端口且不报 EADDRINUSE —— 撞上了不会以启动失败暴露，只会让「side
# 端口只有一个监听者」这个就绪判据失效（假通过）。所以端口必须由脚本先挑干净。
pick_side_port() {
  local old_pids="$1" start="${MCP_SIDE_PORT}" listeners expected owner port i
  case "${start}" in
    '' | *[!0-9]*) die "side 端口必须是数字：FACHUAN_MCP_SIDE_PORT=${start}（不设则自动从 primary+1 起挑）" ;;
  esac
  # 首尾各留一个空格：下面用 *" ${owner} "* 精确匹配 pid，避免 801 命中 8011。
  expected=" $(printf '%s' "${old_pids}" | tr '\n' ' ')"

  if [ -n "${FACHUAN_MCP_SIDE_PORT:-}" ]; then
    if ! port_open "${start}"; then
      return 0
    fi
    listeners="$(pids_on_port "${start}")"
    # 故意不加引号：${listeners} 是换行分隔的 pid 列表，要逐个比较。
    # shellcheck disable=SC2086
    for owner in ${listeners}; do
      case "${expected} " in
        *" ${owner} "*) ;;
        *) die "显式指定的 side 端口 ${start} 被无关进程（PID ${owner}）占用，拒绝抢占；请人工确认: lsof -nP -i tcp:${start}" ;;
      esac
    done
    say "显式指定的 side 端口 ${start} 由当前服务实例（PID $(printf '%s' "${listeners}" | tr '\n' ' ')）占着——蓝绿的预期残留，顺延挑下一个"
    start="$((start + 1))"
  fi

  i=0
  while [ "${i}" -lt "${MCP_SIDE_PORT_SPAN}" ]; do
    port="$((start + i))"
    if ! port_open "${port}"; then
      MCP_SIDE_PORT="${port}"
      return 0
    fi
    i="$((i + 1))"
  done
  die "side 端口 ${start}-$((start + MCP_SIDE_PORT_SPAN - 1)) 全被占用，没有端口能给候选做就绪校验；先确认: lsof -nP -i tcp:${start}"
}

# 等到端口开始监听；给了 pid 时进程提前退出立即失败（别白等满超时）。
wait_port_listening() {
  local port="$1" seconds="$2" pid="${3:-}" i
  for i in $(seq 1 "${seconds}"); do
    port_open "${port}" && return 0
    if [ -n "${pid}" ] && ! kill -0 "${pid}" 2>/dev/null; then
      return 1
    fi
    sleep 1
  done
  return 1
}

# 等到这些 pid 都不再监听 primary。uvicorn 收到 SIGTERM 会**立刻**关监听、再等在飞
# 请求收尾，所以这通常不到一秒；切换后的 primary 核对必须等它，否则可能打到还没退
# 的旧进程（那正是「假通过」）。
wait_listener_released() {
  local pids="$1" seconds="$2" i pid listening still
  for i in $(seq 1 "${seconds}"); do
    listening=" $(pids_on_port "${MCP_PORT}" | tr '\n' ' ') "
    still=0
    for pid in ${pids}; do
      case "${listening}" in
        *" ${pid} "*) still=1 ;;
      esac
    done
    [ "${still}" -eq 0 ] && return 0
    sleep 1
  done
  return 1
}

# 代码侧（离线）工具面指纹。`python -m mcp_server.tool_face` 只输出一行指纹，
# Django bootstrap 的 INFO 走 stderr（与 __main__ 同一条 stdout 改道），这里只在
# 失败时回显 stderr 尾部；成功路径保持一行干净输出。
code_fingerprint() {
  local err_tmp out rc
  err_tmp="$(mktemp)"
  out="$(
    cd "${BACKEND_DIR}" || exit 2
    "${PYTHON_BIN}" -m mcp_server.tool_face 2>"${err_tmp}"
  )"
  rc=$?
  if [ "${rc}" -ne 0 ] || [ -z "${out}" ]; then
    printf '[mcp] 错误: 代码侧指纹计算失败（rc=%s），stderr 尾部:\n' "${rc}" >&2
    grep -v ' INFO - ' "${err_tmp}" | tail -15 >&2
    rm -f "${err_tmp}"
    return 2
  fi
  rm -f "${err_tmp}"
  # 只取最后一行：万一某个工具模块在导入期往 stdout 写了东西（入口已把那个窗口
  # 改道到 stderr，这里是第二道保险），指纹永远在最后。
  printf '%s\n' "${out}" | tail -1
}

# 工具面有没有变（用来决定要不要重启/切换）：在 primary 上真握手核对，工具名
# **和**指纹都一致才算「没变」。服务没在跑（verify rc=2）→ 当作变了，照常重启。
tool_face_unchanged() {
  local out rc
  out="$(cmd_verify --port "${MCP_PORT}" 2>&1)"
  rc=$?
  [ "${rc}" -eq 0 ] && return 0
  say "线上与代码不一致（或线上不可核对），继续走切换："
  printf '%s\n' "${out}" | sed -e 's/^/    /'
  return 1
}

# 起一个候选实例（primary + side 同时监听），回显它的 pid。
# 用命令替换取 pid 时必须让候选与管道脱钩：它的 stdout/stderr/stdin 全部重定向，
# 所以 $(...) 会立刻返回（否则会被这个长驻进程一直挂住）。
spawn_candidate() {
  local drain="$1"
  (
    cd "${BACKEND_DIR}" || exit 1
    nohup env FACHUAN_MCP_TRANSPORT=streamable-http \
      FACHUAN_MCP_HTTP_HOST="${MCP_HOST}" \
      FACHUAN_MCP_HTTP_PORT="${MCP_PORT}" \
      FACHUAN_MCP_SIDE_PORT="${MCP_SIDE_PORT}" \
      FACHUAN_MCP_GRACEFUL_TIMEOUT="${drain}" \
      "${PYTHON_BIN}" -m mcp_server </dev/null >>"${LOG_FILE}" 2>&1 &
    printf '%s\n' "$!"
  )
}

# 切换过程中失败：把候选杀掉再退出，别留一个不服务任何东西的孤儿进程。
# （旧实例此时**没动过**，仍在正常服务，所以这里杀候选没有任何代价。）
abort_candidate() {
  local pid="$1" reason="$2" i
  # 候选已经在收拾了：关掉 trap 的开关，免得退出时再杀一遍（重复 TERM 只会多打一遍日志）。
  OP_CAND_REAP=0
  say "中止：${reason}"
  say "杀候选 ${pid}，旧实例保持服务（日志: ${LOG_FILE}）"
  kill -TERM "${pid}" 2>/dev/null || true
  for i in 1 2 3 4 5; do
    kill -0 "${pid}" 2>/dev/null || return 0
    sleep 1
  done
  kill -9 "${pid}" 2>/dev/null || true
  return 0
}

# 退出/中断的统一收尾（EXIT 与 INT/TERM/HUP 共用这一个函数，装 trap 的地方见文件尾）。
# 为什么必须统一：收尾有两件事（杀候选、删锁），分开写就会出现「锁放了但候选还在」
# 或「候选杀了但锁还占着」——前者正是双绑的成因，后者会让下一个人干等到人工清锁。
# 为什么候选会被打断就杀：候选用 nohup 起的，**不会**跟着脚本退出而死；留它下来就
# 会与旧实例长期双绑 primary、分摊新连接（SO_REUSEPORT 下两边都「正常」，没有任何
# 报错），等下一次切换才发现。这里只杀候选、**不动**旧实例（此刻旧实例仍在正常服务）。
# 顺序不可颠倒：**先杀候选、再删锁**。反过来的话，下一个抢到锁的人会在我们还没退
# 干净时开工，两条流水线仍可能同时改运行态。
on_op_teardown() {
  local reason="${1:-}" pid="${2:-}"
  trap - EXIT INT TERM HUP  # 先卸掉，免得清理途中又被信号打断再跑一遍
  if [ -n "${pid}" ] && [ "${OP_CAND_REAP}" -eq 1 ]; then
    abort_candidate "${pid}" "${reason:-脚本退出前收尾}"
  fi
  release_op_lock
  if [ -n "${reason}" ]; then
    exit 130  # 128+SIGINT，被信号打断的惯例退出码
  fi
}

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
    elapsed="$(ps -o etime= -p "${pid}" 2>/dev/null | tr -d ' ')"
    [ -n "${elapsed}" ] || elapsed='?'
    cmd="$(ps -o command= -p "${pid}" 2>/dev/null)"
    [ -n "${cmd}" ] || cmd='?'
    say "进程      : PID ${pid} · 已运行 ${elapsed}"
    say "  ↳ ${cmd}"
  done
  say "核对工具面: make mcp-verify"
}

cmd_stop() {
  # 故意不拿运维锁：stop 只停不启，且它是「把端口清空」的兜底动作——拿锁反而会在
  # 一个卡住的 bluegreen 持有锁时让人连停都停不掉，而那正是最需要 stop 的时刻。
  # 代价：stop 与 bluegreen 并发时结果不确定（可能把候选也停掉、让那次切换自然
  # 失败退出），但两种结果都不会像两条并发蓝绿那样留下永久双绑。
  local pids
  pids="$(pids_on_port)"
  if [ -z "${pids}" ]; then
    say "没有运行中的共享 MCP（端口 ${MCP_PORT}），无需停止"
    return 0
  fi
  # 端口被占 ≠ 就是我们的人：误杀外部进程（别的 MCP 实例/端口代理）不可逆。
  # 杀前逐个校验命令行确实属于 mcp_server，不符则拒绝并交给人工。
  local pid
  for pid in ${pids}; do
    case "$(ps -o command= -p "${pid}" 2>/dev/null)" in
      *mcp_server*) ;;
      *) die "端口 ${MCP_PORT} 上的 PID ${pid} 不像 mcp_server，拒绝误杀；请人工确认: lsof -nP -i tcp:${MCP_PORT}" ;;
    esac
  done
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
#
# 退出码：0 = 工具名与指纹都一致；1 = 有漂移（缺失/多出/描述或 schema 变了）；
# 2 = 核不了（握手失败、注册表枚举失败、端口上不是 MCP）。
# --port 默认 primary：蓝绿切换用它校验**候选**的 side 端口（只有一个监听者，
# 结论确定），切换后再用它确认 primary 上服务的是新实例。
cmd_verify() {
  local port="${MCP_PORT}" err_tmp rc detail
  while [ $# -gt 0 ]; do
    case "$1" in
      --port)
        shift
        port="${1:-}"
        [ -n "${port}" ] || die "verify --port 需要一个端口号"
        ;;
      *) die "verify 未知参数: $1（可用: --port N）" ;;
    esac
    shift
  done
  err_tmp="$(mktemp)"
  (
    cd "${BACKEND_DIR}" || exit 2
    "${PYTHON_BIN}" - "${MCP_HOST}" "${port}" <<'PYEOF' 2>"${err_tmp}"
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# heredoc 里 __file__ 未定义；cmd_verify 子进程已先 cd 到 backend/，用 cwd 即可
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


def registry_face() -> list[dict]:
    """代码侧工具面。

    走 `mcp_server.tool_face.tool_face_from_mcp` 而不是自己 `asyncio.run(mcp.list_tools())`：
    启动日志里那行 `tool_face=...` 也算这条路径，两边必须是同一个读法（含「list_tools
    不可用时退回 ToolManager 同步注册表」），否则同代码会算出两个指纹。
    """
    from mcp_server.server import mcp
    from mcp_server.tool_face import tool_face_from_mcp

    return tool_face_from_mcp(mcp)


def _ops_token() -> str:
    """为本机运维核对铸一个 token。

    共享 MCP 在 HTTP 模式下强制每请求带 Authorization（不允许回退服务账号，
    否则任意本机进程可越权读全所数据）。核对脚本属本机运维动作，用 .env 里
    的 FACHUAN_USERNAME/PASSWORD（服务账号）走 /token/pair 换 access token。
    """
    import httpx

    from mcp_server import config as mcp_config

    resp = httpx.post(
        f"{mcp_config.BASE_URL}/token/pair",
        json={"username": mcp_config.USERNAME, "password": mcp_config.PASSWORD},
        timeout=30,
        trust_env=False,
    )
    resp.raise_for_status()
    return str(resp.json()["access"])


async def live_face() -> list[dict]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    import httpx2

    from mcp_server.tool_face import tool_face_entries

    token = _ops_token()
    http_client = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"})
    async with http_client, streamable_http_client(URL, http_client=http_client) as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            return tool_face_entries((await session.list_tools()).tools)


def main() -> int:
    from mcp_server.tool_face import tool_face_fingerprint

    try:
        reg_face = registry_face()
    except Exception as exc:
        print(f"[verify] 注册表枚举失败: {exc}", file=sys.stderr)
        return 2
    try:
        live_entry = asyncio.run(live_face())
    except Exception as exc:
        print(f"[verify] 线上握手失败: {exc}")
        print(f"[verify] 端口 {PORT} 可能未就绪，或被非 MCP 进程占用（lsof -nP -i tcp:{PORT}）")
        return 2

    reg_fp, live_fp = tool_face_fingerprint(reg_face), tool_face_fingerprint(live_entry)
    reg = sorted(entry["name"] for entry in reg_face)
    live = sorted(entry["name"] for entry in live_entry)
    reg_set, live_set = set(reg), set(live)
    missing = sorted(reg_set - live_set)
    extra = sorted(live_set - reg_set)
    print(f"[verify] 代码注册表: {len(reg)} 个工具 · 线上: {len(live)} 个工具")
    print(f"[verify] 指纹 代码 {reg_fp} · 线上 {live_fp}（{'一致' if reg_fp == live_fp else '不一致'}）")
    if missing:
        print(f"[verify] 线上缺失 {len(missing)} 个（代码有、线上无 → 旧进程，跑 make mcp 重启）:")
        for name in missing:
            print(f"    - {name}")
    if extra:
        print(f"[verify] 线上多出 {len(extra)} 个（线上有、代码无 → 代码回退后未重启）:")
        for name in extra:
            print(f"    - {name}")
    if missing or extra:
        return 1
    if reg_fp != live_fp:
        # 工具名全对但指纹不同 = 某个工具的描述或 inputSchema 变了。描述是模型选工具
        # 的依据、schema 是它构造调用的依据，不重启就还是旧行为——所以同样算漂移。
        print("[verify] 工具名一致但描述/参数 schema 有变 → 重启才生效: make mcp（或 make mcp-bluegreen）")
        return 1
    print("[verify] 工具面一致 ✅")
    return 0


sys.exit(main())
PYEOF
  )
  rc=$?
  if [ "${rc}" -eq 2 ]; then
    detail="$(grep -v ' INFO - ' "${err_tmp}" | tail -15)"
    if [ -n "${detail}" ]; then
      echo "[verify] --- stderr 异常栈尾部（bootstrap INFO 已省略）---" >&2
      echo "${detail}" >&2
    fi
  fi
  rm -f "${err_tmp}"
  return "${rc}"
}

cmd_fingerprint() {
  local fp
  fp="$(code_fingerprint)" || return 2
  say "代码侧工具面指纹: ${fp}"
  say "线上指纹: make mcp-verify（两个不同 = 线上跑的不是这份代码）"
}

cmd_restart() {
  local if_stale=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --if-stale) if_stale=1 ;;
      *) die "restart 未知参数: $1（可用: --if-stale）" ;;
    esac
    shift
  done
  # 拿锁放在指纹判断**之前**：restart 会杀旧起新，与并发的 bluegreen 交错就会撞上
  # 「候选刚绑上 primary，旧的却被人先杀了」这类没人负责的中间态（见文件头「为什么
  # 必须互斥」）。--if-stale 的只读核对也一并纳入锁内，代价可以忽略。
  acquire_op_lock
  if [ "${if_stale}" -eq 1 ] && tool_face_unchanged; then
    say "工具面未变（线上指纹 = 代码指纹），跳过重启"
    return 0
  fi
  cmd_stop
  cmd_start
  say "核对工具面…"
  if cmd_verify; then
    say "重启完成，工具面与代码一致"
  else
    die "工具面核对未通过（见上方输出）——新进程可能没起来或注册表异常，排障: tail -50 ${LOG_FILE}"
  fi
}

# 蓝绿切换：候选与旧实例并存 → side 端口真握手 → 旧实例退休 → primary 复核。
# 顺序不可颠倒（见文件头）：「新实例真的起来了」只能由 side 端口回答，答完才能
# 让旧实例退休。
#
# 首次启用需先做一次普通重启：SO_REUSEPORT 要求同端口上**所有** socket 都带这个
# 选项，不带它起来的老进程会让候选 bind primary 直接 EADDRINUSE（候选会秒退，本
# 脚本会打印日志尾部并中止，旧实例不受影响）。所以升级后的第一条命令仍是 make mcp，
# 之后才用 make mcp-bluegreen。
cmd_bluegreen() {
  # if_stale 默认 0 = **默认强制切**：指纹只覆盖注册元数据（名字/描述/schema/注解），
  # 看不见「只改实现」——而「只改实现」恰恰是本仓最常见的一类变更。默认按指纹跳过
  # 会让人以为上线了，实际跑的还是旧代码（P1-3）。--force 保留为显式同义（老用法/文档
  # 引用它），语义就是默认行为。
  local if_stale=0 drain="${BLUEGREEN_DRAIN}" code_fp old_pids cand_pid pid primary_pids others
  while [ $# -gt 0 ]; do
    case "$1" in
      --if-stale) if_stale=1 ;;
      --force) if_stale=0 ;;
      --drain)
        shift
        drain="${1:-}"
        [ -n "${drain}" ] || die "--drain 需要一个正整数秒数"
        ;;
      *) die "bluegreen 未知参数: $1（可用: --if-stale / --force / --drain N）" ;;
    esac
    shift
  done

  # drain 必须是正整数：0/负数会变成 uvicorn 的 timeout_graceful_shutdown=None（无限等），
  # 退休实例就永不退出（监听虽已交出，进程与在飞请求会一直挂着）。非数字同理——
  # 行为未定比「等久一点」危险得多。来源是 --drain 或 FACHUAN_MCP_GRACEFUL_TIMEOUT，一并卡。
  case "${drain}" in
    0) die "drain 不允许 0：uvicorn 会把它翻成「无限等」，旧实例可能永挂；请给正整数秒（默认 ${BLUEGREEN_DRAIN}）" ;;
    *[!0-9]*) die "drain 只接受正整数秒数，收到: ${drain}（来源: --drain 或 FACHUAN_MCP_GRACEFUL_TIMEOUT）" ;;
  esac

  # 拿锁放在①之前：后面每一步（挑 side 端口 / 起候选 / 退休旧实例）都以「没有别人在
  # 同时改运行态」为前提——两条并发蓝绿双绑 primary 就是这么发生的（见文件头）。
  acquire_op_lock

  # ① 代码侧指纹：既是 --if-stale 的判据，也是切换完成后给人看的结果。
  code_fp="$(code_fingerprint)" || die "代码侧指纹算不出来，中止切换"
  say "代码侧工具面指纹: ${code_fp}"

  # ② 只有显式 --if-stale 才按指纹跳过（默认强制切，见函数头的理由）。
  if [ "${if_stale}" -eq 1 ] && tool_face_unchanged; then
    say "工具面未变（线上指纹 = 代码指纹），--if-stale 要求跳过切换；要强制切换就去掉 --if-stale"
    return 0
  fi

  old_pids="$(pids_on_port "${MCP_PORT}")"
  if [ -n "${old_pids}" ]; then
    say "旧实例: $(printf '%s' "${old_pids}" | tr '\n' ' ')"
  else
    say "primary ${MCP_PORT} 上没有旧实例，本次是纯启动（无需退休）"
  fi
  # 端口被占 ≠ 就是我们的人：与 cmd_stop 同一条理由，退休前逐个校验命令行。
  # 校验放在起候选**之前**：不符就直接中止，不留下任何待收拾的东西，也绝不可能
  # 已经把哪个不明进程 TERM 掉。
  for pid in ${old_pids}; do
    case "$(ps -o command= -p "${pid}" 2>/dev/null)" in
      *mcp_server*) ;;
      *) die "端口 ${MCP_PORT} 上的 PID ${pid} 不像 mcp_server，拒绝误杀；请人工确认: lsof -nP -i tcp:${MCP_PORT}" ;;
    esac
  done
  # side 端口由脚本挑（不能沿用「占用即中止」：上一轮胜出的候选会一直听到它自己死，
  # 见 pick_side_port）。挑完写回全局 MCP_SIDE_PORT。
  pick_side_port "${old_pids}"

  # ③ 起候选（primary 与 side 同时监听）。此刻 primary 上新旧两个实例并存。
  say "拉起候选实例（primary ${MCP_PORT} + side ${MCP_SIDE_PORT}，drain ${drain}s，日志: ${LOG_FILE}）"
  cand_pid="$(spawn_candidate "${drain}")"
  [ -n "${cand_pid}" ] || die "候选实例拉起失败（拿不到 pid）"
  say "候选 pid: ${cand_pid}"
  # 从这一刻起脚本可能在任何一步被打断（Ctrl+C / 外部 kill / 终端挂断）：候选用 nohup
  # 起的，**不会**跟着脚本死，留它下来就会与旧实例长期双绑 primary 并分摊新连接。
  # 写全局变量而不是靠 local：trap 在函数返回后仍可能触发（EXIT），那时 local 已经不
  # 存在了（set -u 下会直接报 unbound variable）。收尾逻辑在 on_op_teardown。
  OP_CAND_PID="${cand_pid}"
  OP_CAND_REAP=1

  # ④ 等 side 端口就绪：只有候选在听它，所以「端口开了」= 「候选起来了」。
  if ! wait_port_listening "${MCP_SIDE_PORT}" 30 "${cand_pid}"; then
    say "候选实例未在 30 秒内监听 side ${MCP_SIDE_PORT}，日志尾部:"
    tail -20 "${LOG_FILE}" >&2
    abort_candidate "${cand_pid}" "候选实例未就绪"
    return 1
  fi

  # ⑤ side 端口真握手：候选自己的工具面必须与代码一致（这是「值不值得切」的判据）。
  if ! cmd_verify --port "${MCP_SIDE_PORT}"; then
    abort_candidate "${cand_pid}" "候选实例的 side 端口工具面核对未通过"
    return 1
  fi
  say "候选通过 side 校验（指纹 ${code_fp}）"

  # ⑥ 旧实例退休：SIGTERM 让它关掉监听（不再接新连接），再等在飞请求收尾。
  if [ -n "${old_pids}" ]; then
    say "旧实例退休（SIGTERM，在飞请求由它自己收尾）: $(printf '%s' "${old_pids}" | tr '\n' ' ')"
    # 故意不加引号：${old_pids} 是换行分隔的 pid 列表，要逐个传给 kill。
    # shellcheck disable=SC2086
    kill -TERM ${old_pids} 2>/dev/null || true
    if wait_listener_released "${old_pids}" 20; then
      say "旧实例已交出 ${MCP_PORT} 的监听"
    else
      say "警告: 旧实例 20 秒内仍占着 ${MCP_PORT} 的监听，primary 核对仍可能落到旧进程"
    fi
  fi
  # 旧实例已交出监听：此刻候选是唯一服务者，再杀它就等于把共享 MCP 打空 —— 关掉
  # 候选清理并卸信号 trap（EXIT 槽位保留：锁仍必须在退出时放掉）。
  OP_CAND_REAP=0
  trap - INT TERM HUP

  # ⑦ primary 复核前先断言 primary 上的监听者**只有**候选。
  # 为什么：verify 只比「工具名 + 指纹」，SO_REUSEPORT 下还没退的旧实例照样答得上来——
  # 拿旧实例的答案当候选的，会把「切换成功」报成 ✅（假通过，且此后无人服务真新代码）。
  primary_pids="$(pids_on_port "${MCP_PORT}")"
  [ -n "${primary_pids}" ] || die "primary ${MCP_PORT} 上没有任何监听者（候选 ${cand_pid} 可能已退出），复核无从谈起；排障: tail -50 ${LOG_FILE}"
  others=""
  # 故意不加引号：${primary_pids} 是换行分隔的 pid 列表。
  # shellcheck disable=SC2086
  for pid in ${primary_pids}; do
    if [ "${pid}" != "${cand_pid}" ]; then
      others="${others} ${pid}"
    fi
  done
  [ -z "${others}" ] || die "primary ${MCP_PORT} 上除候选 ${cand_pid} 外还有监听者:${others} —— 复核结果不可信（多半是还没退的旧实例）；候选仍在服务（未杀），排障: lsof -nP -i tcp:${MCP_PORT}"

  # ⑦ primary 复核：此刻 primary 上的新连接只由候选承接。
  say "核对 primary ${MCP_PORT}（切换后服务的就是它）…"
  if ! cmd_verify --port "${MCP_PORT}"; then
    # 这里**不杀候选**：旧实例已经 TERM，候选是此刻唯一的服务者，杀它等于把共享 MCP
    # 彻底打空。保留进程、把 pid 与日志路径打出来，由人决定回滚（通常直接 make mcp）。
    die "切换后 primary 核对未通过：共享 MCP 只剩候选 ${cand_pid} 在服务。排障: make mcp-status / make mcp-logs；彻底重来: make mcp"
  fi

  # ⑧ 结果：新 pid 与已退休的旧 pid，方便事后对日志。
  if [ -n "${old_pids}" ]; then
    say "蓝绿切换完成 ✅ 新 pid=${cand_pid} · 已退休 pid=$(printf '%s' "${old_pids}" | tr '\n' ' ')"
  else
    say "蓝绿切换完成 ✅ pid=${cand_pid}（原本没有旧实例）"
  fi
}

# 收尾 trap 的唯一装配点。分两个**不相交**的信号槽位，所以不存在「后装的把先装的顶掉」
# （bash 的 trap 按信号名分槽位：EXIT 一个槽、INT/TERM/HUP 一个槽），收尾逻辑只有
# on_op_teardown 一处。信号槽位带上原因字符串：它决定是否以 130 退出（128+SIGINT）。
trap 'on_op_teardown "" "${OP_CAND_PID}"' EXIT
trap 'on_op_teardown "脚本被中断（Ctrl+C / kill / 终端挂断）" "${OP_CAND_PID}"' INT TERM HUP

case "${1:-restart}" in
  restart)
    if [ $# -gt 0 ]; then shift; fi
    cmd_restart "$@"
    ;;
  bluegreen)
    if [ $# -gt 0 ]; then shift; fi
    cmd_bluegreen "$@" || die "蓝绿切换未完成（见上方输出）"
    ;;
  status) cmd_status ;;
  logs)
    [ -f "${LOG_FILE}" ] || die "日志不存在: ${LOG_FILE}（还没启动过？）"
    say "跟随 ${LOG_FILE}（Ctrl+C 退出）"
    tail -n 200 -f "${LOG_FILE}"
    ;;
  verify)
    if [ $# -gt 0 ]; then shift; fi
    cmd_verify "$@" || die "工具面核对未通过"
    ;;
  fingerprint) cmd_fingerprint ;;
  stop) cmd_stop ;;
  *) die "未知子命令: ${1}（可用: restart/bluegreen/status/logs/verify/fingerprint/stop）" ;;
esac
