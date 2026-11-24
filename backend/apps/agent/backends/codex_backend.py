"""codex 后端：把「``codex app-server`` 跑一轮」接成 ``AgentBackend``。

## 为什么是 `app-server` 而不是 `exec --json`

两条通道都实测过（2026-11-24，codex-cli 0.161.0）：

| 通道 | 逐字流 | 执行前审批 | 结论 |
|:-|:-|:-|:-|
| ``exec --json`` | ❌ 只在 item 完成时出事件 | ❌ ``approval_policy = Never`` | 只能当「无闸门对照栏」 |
| **``app-server``** | ✅ ``item/agentMessage/delta`` | ✅ ``item/commandExecution/requestApproval`` / ``item/fileChange/requestApproval`` | **本模块走这条** |

``app-server`` 是 JSON-RPC over stdio：``initialize`` → ``thread/start``（把共享 MCP
一起挂上，实测 ``mcpServer/startupStatus → ready``）→ ``turn/start``；随后服务端推
``item/*`` 通知，并在需要人批时**反向发请求**给客户端。

**内置工具一律走人工闸门**：codex 自己那套 shell / 打补丁能力不经过我们的 MCP，
所以把它们命名成 ``codex_execute_command`` / ``codex_rewrite_file``——这两个名字命中
``services/approval/risk.py`` 的 ``DANGER_PATTERNS``（``execute_`` / ``rewrite_``），
于是**必然被判为 HIGH、必然弹审批卡**。这不是取名游戏：不用这两个前缀，分类器会
把 ``codex_shell`` 判成低风险直接放行，闸门等于没有。

## 实测出来的三件事（都带着证据写在这里，免得后人再踩）

1. **必须经 loopback 代理**：codex 的 reqwest 客户端 ``system_proxy_fallback: true``，
   会读 macOS 系统代理；内网网关被 Clash 一劫持就是 ``502 Bad Gateway``，
   而同一份请求体经本地反代转发就正常。``NO_PROXY`` / 删 ``HTTPS_PROXY`` 都无效
   （它读系统级配置）。见 :mod:`apps.agent.backends.codex_gateway`。
2. **只认 ``responses`` 协议**：``wire_api = "chat"`` 在 0.161 已被移除（配置直接
   报错退出），必须 ``wire_api = "responses"``。律所网关支持 ``/v1/responses``
   （实测 200，含 SSE 流）。
3. **``exec`` 不吐逐字流**：事件粒度是「一个 item 完成」，所以 ``streaming=False``。
   正文与工具结果都会到，只是没有 token 级增量——前端据此关掉打字机动画。

## 本模块管什么

1. **每会话一个 CODEX_HOME**（0700 / ``config.toml`` 0600）：provider、MCP、
   审批策略全部写在这份配置里，不碰用户的 ``~/.codex``。
2. **凭证**：网关 base_url / key 来自 ``LLMProvider``（复用 ``gateway_cache``），
   经 loopback 代理注入 ``Authorization``；律师 token 走 MCP 的请求头。
3. **事件翻译**：JSONL → ``sse_types.py`` 的契约事件。

**不接管**（留在编排层 ``services/chat/stream.py``）：造用户凭证、写
``AgentMessage`` / ``AgentRun``、发 ``meta`` / ``done``。与其它后端同一口径。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator

from asgiref.sync import sync_to_async

from .base import BackendCapabilities, BackendError, BackendErrorKind, LiveBackendHandle, RunContext, StreamFrame
from .codex_gateway import GatewayProxy
from .gateway_cache import get_gateway_settings, resolve_gateway_target
from .toolface import (
    SERVER_NAME,
    SESSION_HEADER,
    TIER_FULL,
    TIER_LITE,
    TOOL_TIER_HEADER,
    endpoint_from_env,
    port_open,
    shared_enabled,
)

logger = logging.getLogger(__name__)

KIND = "codex"

#: codex 可执行文件（``FACHUAN_CODEX_BIN`` 可覆盖）。
#: 审批开关（与 capabilities.approval 同源）。
APPROVAL_ENV = "FACHUAN_CODEX_APPROVAL"

BIN_ENV = "FACHUAN_CODEX_BIN"
DEFAULT_BIN = "codex"

#: 稳定目录根（与 pi / opencode 共用 ``FACHUAN_AGENT_HOME``）。
HOME_ENV = "FACHUAN_AGENT_HOME"
DEFAULT_AGENT_HOME = "~/.fachuan-agent"

#: 单轮等待上限（秒）。codex 首轮会把工具面全塞进 prompt（实测 17 万 token）。
ROUND_TIMEOUT = 600.0

#: 收尾事实保留条数。
MAX_KEPT_RESULTS = 32

#: codex 自带工具里我们不希望它用的那些（它自己的 shell / 打补丁 / 搜索）。
#: 注意：``exec`` 模式的工具集**无法像 opencode 那样按 agent 关掉**，所以这里
#: 只做「审批层拒绝」——见 :data:`BUILTIN_TOOLS` 与模块 docstring 的说明。
BUILTIN_TOOLS = frozenset(
    {"shell", "exec_command", "apply_patch", "read_file", "write_file", "update_plan", "web_search"}
)


def approval_enabled() -> bool:
    """本轮是否启用人工审批闸门（默认开）。

    **必须与 ``capabilities.approval`` 同源**：第一版把它写成「``exec`` 通道恒无审批 →
    恒返回 False」，而 capabilities 却硬编码 True，结果 capability 说有闸门、
    实现里 ``_ask_human`` 直接放行——实测 codex 的 ``touch`` 未经审批就执行了。
    现在两处都取这个函数的值。
    """
    raw = os.environ.get(APPROVAL_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def tool_tier() -> str:
    """MCP 工具面分层（``full`` / ``lite``）；**默认 full**。

    为什么默认不是 lite：实测 lite 下 codex 拿不到 ``fachuan_asean_law_countries``
    这类冷门工具，于是它**不调工具、直接编一句「当前会话没有这个工具」**——
    矩阵 e2e 里表现为 ``tool_call=0``，看着"有正文、done=1"像是通的，实际等于没干活。
    代价是每轮约 17 万 token（``cache_read≈167872``），所以本栏定位是**对照栏**：
    要省钱就显式 ``FACHUAN_CODEX_TOOL_TIER=lite``，并接受冷门工具不可用。
    """
    raw = os.environ.get("FACHUAN_CODEX_TOOL_TIER", "").strip().lower()
    if raw in {TIER_LITE, TIER_FULL}:
        return raw
    return TIER_FULL


def resolve_bin() -> str:
    explicit = os.environ.get(BIN_ENV, "").strip()
    if explicit:
        return explicit
    return shutil.which(DEFAULT_BIN) or DEFAULT_BIN


def is_available() -> bool:
    return shutil.which(resolve_bin()) is not None


def agent_home() -> Path:
    raw = os.environ.get(HOME_ENV, "").strip() or DEFAULT_AGENT_HOME
    return Path(raw).expanduser()


def session_dir(session_id: str) -> Path:
    """某会话的稳定目录（codex 的 ``CODEX_HOME`` 建在它下面）。"""
    path = agent_home() / "codex" / session_id
    (path / "home").mkdir(parents=True, exist_ok=True)
    (path / "work").mkdir(parents=True, exist_ok=True)
    for target in (path, path / "home"):
        try:
            target.chmod(0o700)
        except OSError:  # pragma: no cover - 非 POSIX
            logger.debug("codex 目录 chmod 0700 失败：%s", target)
    return path


def build_config(*, proxy_base_url: str, model: str, mcp_headers: dict[str, str] | None, mcp_url: str | None) -> str:
    """拼 ``config.toml``（TOML 文本；不引入 toml 依赖，字段极少且都是标量）。

    ``wire_api = "responses"`` 是硬要求：0.161 已移除 ``chat``，写错直接启动失败。
    """
    lines = [
        f'model = "{_toml_escape(model)}"',
        'model_provider = "fachuan"',
        "",
        "[model_providers.fachuan]",
        'name = "fachuan gateway"',
        f'base_url = "{_toml_escape(proxy_base_url)}"',
        'env_key = "OPENAI_API_KEY"',
        'wire_api = "responses"',
        "",
    ]
    if mcp_url:
        header_items = ", ".join(f'{_toml_escape(k)} = "{_toml_escape(v)}"' for k, v in (mcp_headers or {}).items())
        lines += [
            f"[mcp_servers.{SERVER_NAME}]",
            f'url = "{_toml_escape(mcp_url)}"',
            f"http_headers = {{ {header_items} }}",
            "",
        ]
    return "\n".join(lines)


def _toml_escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def write_config(home: Path, content: str) -> Path:
    """写 ``<home>/config.toml``（0600）。"""
    path = home / "config.toml"
    path.write_text(content, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:  # pragma: no cover
        logger.debug("codex config.toml chmod 0600 失败：%s", path)
    return path


def build_env(home: Path, api_key: str) -> dict[str, str]:
    """子进程环境：隔离 CODEX_HOME + 剔代理 + 塞 key。"""
    env = {k: v for k, v in os.environ.items() if k.lower() not in {"http_proxy", "https_proxy", "all_proxy"}}
    env["CODEX_HOME"] = str(home)
    env["OPENAI_API_KEY"] = api_key
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    return env


@dataclass(frozen=True)
class CodexRunResult:
    """收尾事实（``AgentRun.model`` 靠它回写）。"""

    model: str
    context_used: int | None = None
    context_total: int | None = None


def normalize_tool_name(item: dict[str, Any]) -> tuple[str, str]:
    """``mcpToolCall`` 的 ``(server, tool)`` → ``(短名, 审批用全名)``。

    codex 的事件里 server 与 tool 是分开的两个字段，比 opencode 的 ``title`` 可靠：
    ``{"server": "fachuan", "tool": "delete_case"}`` → ``("delete_case", "mcp__fachuan__delete_case")``。
    """
    tool = str(item.get("tool") or "").strip()
    server = str(item.get("server") or "").strip()
    if not tool:
        return "", ""
    if server == SERVER_NAME:
        return tool, f"mcp__{SERVER_NAME}__{tool}"
    return tool, f"{server}__{tool}" if server else tool


class _JsonRpc:
    """``codex app-server`` 的 JSON-RPC over stdio 客户端（只实现用到的那一小片）。

    三条通道分开：``request()`` 发请求等响应、``next_message()`` 取服务端推来的通知、
    ``on_request`` 处理**服务端反向发来的请求**（审批就走这条）。
    """

    def __init__(self, proc: asyncio.subprocess.Process, on_request: Any) -> None:
        self._proc = proc
        self._on_request = on_request
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._notifications: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._reader = asyncio.create_task(self._read_loop())
        self.closed = False

    async def _read_loop(self) -> None:
        assert self._proc.stdout is not None
        while True:
            raw = await self._proc.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            await self._dispatch(msg)
        self.closed = True
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(BackendError(BackendErrorKind.UNKNOWN, "codex app-server 已退出"))
        self._pending.clear()

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        msg_id = msg.get("id")
        if msg_id is not None and ("result" in msg or "error" in msg):
            fut = self._pending.pop(int(msg_id), None)
            if fut is not None and not fut.done():
                fut.set_result(msg)
            return
        if msg_id is not None and "method" in msg:
            await self._handle_server_request(msg)
            return
        if "method" in msg:
            await self._notifications.put(msg)

    async def _handle_server_request(self, msg: dict[str, Any]) -> None:
        try:
            result = await self._on_request(msg)
        except (BackendError, RuntimeError, ValueError, KeyError, TypeError) as exc:
            logger.exception("codex 审批回调失败：%s", msg.get("method"))
            result = {"decision": "decline"}
            logger.debug("审批回调异常按拒绝处理：%s", exc)
        await self._send({"jsonrpc": "2.0", "id": msg["id"], "result": result})

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._proc.stdin is None or self.closed:
            return
        try:
            self._proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            self.closed = True

    async def request(self, method: str, params: dict[str, Any], *, timeout: float = 60.0) -> dict[str, Any]:
        self._next_id += 1
        rid = self._next_id
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        await self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            msg = await asyncio.wait_for(fut, timeout=timeout)
        except TimeoutError:
            self._pending.pop(rid, None)
            raise BackendError(BackendErrorKind.UNKNOWN, f"codex {method} 超时（{timeout:.0f}s）") from None
        if "error" in msg:
            raise _error_from_rpc(method, msg["error"])
        return msg.get("result") or {}

    async def next_message(self) -> dict[str, Any] | None:
        if self.closed and self._notifications.empty():
            return None
        try:
            return await asyncio.wait_for(self._notifications.get(), timeout=1.0)
        except TimeoutError:
            return None

    async def close(self) -> None:
        try:
            if self._proc.stdin is not None:
                self._proc.stdin.close()
        except (BrokenPipeError, ConnectionResetError):
            # 子进程已退出：关 stdin 失败不影响收尾，后面统一 kill/wait。
            pass
        self._reader.cancel()
        if self._proc.returncode is None:
            self._proc.kill()
        await self._proc.wait()


def _error_from_rpc(method: str, error: Any) -> BackendError:
    """JSON-RPC error → 用户能看懂的 ``BackendError``。"""
    message = str((error or {}).get("message") or error) if isinstance(error, dict) else str(error)
    lowered = message.lower()
    if "auth" in lowered or "401" in message or "403" in message:
        return BackendError(BackendErrorKind.AUTH, f"codex {method} 鉴权失败：{message}")
    if "rate" in lowered or "429" in message:
        return BackendError(BackendErrorKind.RATE_LIMITED, f"codex {method} 被限流：{message}", retryable=True)
    if "context" in lowered or "token" in lowered:
        return BackendError(BackendErrorKind.CONTEXT_OVERFLOW, f"codex {method} 上下文超限：{message}")
    return BackendError(BackendErrorKind.UNKNOWN, f"codex {method} 失败：{message}")


class CodexHandle(LiveBackendHandle):
    """本轮控制柄：中止走 ``turn/interrupt``；插话走 ``turn/steer``（app-server 支持）。"""

    kind = KIND

    def __init__(self, *, run_id: str, thread_id: str, turn_id: str, rpc: _JsonRpc, state: _RunState) -> None:
        self.run_id = run_id
        self._thread_id = thread_id
        self._turn_id = turn_id
        self._rpc = rpc
        self._state = state

    async def steer(self, message: str) -> str:
        await self._rpc.request(
            "turn/steer",
            {"threadId": self._thread_id, "turnId": self._turn_id, "input": [{"type": "text", "text": message}]},
            timeout=30.0,
        )
        return "queued"

    async def follow_up(self, message: str) -> str:
        """app-server 没有「追加一轮」的独立语义：与插话同义。"""
        return await self.steer(message)

    async def abort(self) -> bool:
        await self._rpc.request("turn/interrupt", {"threadId": self._thread_id, "turnId": self._turn_id}, timeout=15.0)
        return True

    async def get_stats(self) -> dict[str, Any]:
        if self._state.input_tokens + self._state.output_tokens <= 0:
            return {}
        return {
            "input_tokens": self._state.input_tokens,
            "output_tokens": self._state.output_tokens,
            "cache_read_tokens": self._state.cache_read_tokens,
        }


@dataclass
class _RunState:
    """一轮的翻译状态。"""

    announced: set[str] = field(default_factory=set)
    tool_names: dict[str, str] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    #: 上一份累计用量：``thread/tokenUsage/updated`` 给的是**累计值**，
    #: 直接拿来记账会把整轮成本算成几倍（同 dsh 的教训）。
    last_total: int = 0


class CodexBackend:
    """codex 运行时（每次 ``stream()`` 拉起一条 ``codex app-server``）。"""

    kind = KIND
    capabilities: BackendCapabilities

    _results: OrderedDict[str, CodexRunResult]

    def __init__(self) -> None:
        self.capabilities = BackendCapabilities(
            streaming=True,  # app-server 有 item/agentMessage/delta（实测）
            tool_calls=True,
            approval=approval_enabled(),  # 与开关同源（第一版硬编码 True，实现却恒放行——已修）
            compaction=False,  # 每轮新 thread，历史由编排层渲染
            steer=True,  # turn/steer 在协议里
            concurrent_in_session=True,
        )
        self._results = OrderedDict()

    def result_for(self, run_id: str) -> CodexRunResult | None:
        return self._results.get(run_id)

    def _remember_result(self, run_id: str, result: CodexRunResult) -> None:
        self._results[run_id] = result
        self._results.move_to_end(run_id)
        while len(self._results) > MAX_KEPT_RESULTS:
            self._results.popitem(last=False)

    def stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        return self._stream(ctx)

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        resolved = await self._resolve_gateway(ctx)
        run_dir = session_dir(str(ctx.session.session_id))
        home, work = run_dir / "home", run_dir / "work"
        state = _RunState()
        with GatewayProxy() as proxy:
            proxy_base = proxy.lease(base_url=resolved["base_url"], api_key=resolved["api_key"])
            mcp_url, mcp_headers = self._mcp(ctx, str(ctx.session.session_id))
            write_config(
                home,
                build_config(
                    proxy_base_url=proxy_base, model=resolved["model"], mcp_url=mcp_url, mcp_headers=mcp_headers
                ),
            )
            async for frame in self._run(ctx, home=home, work=work, resolved=resolved, state=state):
                yield frame
        self._remember_result(ctx.run_id, CodexRunResult(model=resolved["model"]))

    async def _run(
        self,
        ctx: RunContext,
        *,
        home: Path,
        work: Path,
        resolved: dict[str, Any],
        state: _RunState,
    ) -> AsyncGenerator[StreamFrame, None]:
        binary = resolve_bin()
        try:
            proc = await asyncio.create_subprocess_exec(
                binary,
                "app-server",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=build_env(home, resolved["api_key"]),
                cwd=str(work),
            )
        except FileNotFoundError:
            raise BackendError(
                BackendErrorKind.UNAVAILABLE,
                f"找不到 codex 可执行文件（{binary}）；请先安装 codex 或设置 {BIN_ENV}",
            ) from None

        rpc = _JsonRpc(proc, self._make_approval_handler(ctx, state))
        failure: BackendError | None = None
        try:
            await rpc.request(
                "initialize", {"clientInfo": {"name": "fachuan", "version": "1"}, "capabilities": {}}, timeout=30.0
            )
            thread = await rpc.request(
                "thread/start",
                {
                    "cwd": str(work),
                    "model": resolved["model"],
                    "modelProvider": "fachuan",
                    # 严格模式：codex 自己的 shell / 打补丁**必须**先问我们
                    "approvalPolicy": "untrusted",
                    "sandbox": "read-only",
                },
                timeout=120.0,
            )
            thread_id = str((thread.get("thread") or {}).get("id") or "")
            if not thread_id:
                raise BackendError(BackendErrorKind.UNKNOWN, "codex 没有返回 thread id")
            turn = await rpc.request(
                "turn/start",
                {"threadId": thread_id, "input": [{"type": "text", "text": ctx.prompt}]},
                timeout=120.0,
            )
            turn_id = str((turn.get("turn") or {}).get("id") or "")
            registered = False
            handle: CodexHandle | None = None
            if not ctx.isolated:
                # 登记控制柄：用户可在本轮跑到一半时插话 / 中止（与 pi 同口径）。
                # **best-effort**：登记失败不能让本轮对话挂住（测试桩会话、并发占位都会抛）。
                from ..services.live_sessions import get_live_registry

                handle = CodexHandle(run_id=ctx.run_id, thread_id=thread_id, turn_id=turn_id, rpc=rpc, state=state)
                try:
                    await get_live_registry().register(str(ctx.session.session_id), handle)
                    registered = True
                except (RuntimeError, ValueError, KeyError) as exc:
                    logger.info("codex 登记运行中会话失败（不影响本轮）：%s", exc)
            try:
                async for frame in self._pump(ctx, rpc, state):
                    yield frame
            finally:
                if registered and handle is not None:
                    from ..services.live_sessions import get_live_registry

                    try:
                        await get_live_registry().unregister(str(ctx.session.session_id), handle)
                    except (BackendError, RuntimeError, ValueError):
                        logger.exception("codex 注销运行中会话失败：%s", ctx.session.session_id)
        finally:
            await rpc.close()
        if failure is not None:
            raise failure

    async def _pump(self, ctx: RunContext, rpc: _JsonRpc, state: _RunState) -> AsyncGenerator[StreamFrame, None]:
        """读通知直到 ``turn/completed``。"""
        while True:
            message = await rpc.next_message()
            if message is None:
                if rpc.closed:
                    return
                yield None
                continue
            method = str(message.get("method") or "")
            params = message.get("params") or {}
            if method == "turn/completed":
                return
            if method == "error":
                raise BackendError(BackendErrorKind.UNKNOWN, str(params.get("message") or "codex 本轮失败")[:300])
            for frame in self._translate(method, params, state):
                yield {**frame, "agent": self.kind, "run_id": ctx.run_id}

    # ── 审批 ────────────────────────────────────────────────────────────

    def _make_approval_handler(self, ctx: RunContext, state: _RunState) -> Any:
        async def handle(msg: dict[str, Any]) -> dict[str, Any]:
            method = str(msg.get("method") or "")
            params = msg.get("params") or {}
            tool_name, tool_args, call_id = _approval_identity(method, params)
            if tool_name is None:
                logger.info("codex 发来未支持的请求，直接放行（不改语义）：%s", method)
                return {"decision": "accept"}
            approved = await self._ask_human(ctx, tool_name, tool_args, call_id)
            # 取值来自 ``CommandExecutionApprovalDecision`` 枚举（实测踩过：写 ``denied``
            # 会解析失败，整个 turn 挂住不返回）。``decline`` = 拒绝但本轮继续；
            # ``cancel`` = 拒绝并中止本轮——我们只要前者（与其它后端的「拒绝后继续」同义）。
            return {"decision": "accept" if approved else "decline"}

        return handle

    async def _ask_human(self, ctx: RunContext, tool_name: str, tool_args: dict[str, Any], call_id: str) -> bool:
        """走四级判定；``codex_execute_command`` / ``codex_rewrite_file`` 必然 HIGH。"""
        if not approval_enabled():
            return True
        from ..services.approval import request_approval

        approved, _aid, _reason = await request_approval(
            tool_name=tool_name,
            tool_args=tool_args,
            user_id=ctx.user_id,
            session_id=str(ctx.session.session_id),
            run_id=ctx.run_id,
            tool_call_id=call_id,
        )
        return approved

    # ── 事件翻译 ────────────────────────────────────────────────────────

    def _translate(self, method: str, params: dict[str, Any], state: _RunState) -> list[dict[str, Any]]:
        if method == "item/agentMessage/delta":
            delta = params.get("delta")
            return [{"type": "delta", "content": delta}] if isinstance(delta, str) and delta else []
        if method == "item/started":
            return self._item_frames(params.get("item") or {}, started=True, state=state)
        if method == "item/completed":
            return self._item_frames(params.get("item") or {}, started=False, state=state)
        if method == "thread/tokenUsage/updated":
            usage = self._usage_frame(params.get("tokenUsage") or {}, state)
            return [usage] if usage else []
        return []

    def _item_frames(self, item: dict[str, Any], *, started: bool, state: _RunState) -> list[dict[str, Any]]:
        kind = str(item.get("type") or "")
        call_id = str(item.get("id") or "")
        if kind == "mcpToolCall":
            short, _full = normalize_tool_name(item)
            if started:
                if call_id in state.announced:
                    return []
                state.announced.add(call_id)
                state.tool_names[call_id] = short
                args = item.get("arguments")
                return [
                    {
                        "type": "tool_call",
                        "tool_call_id": call_id,
                        "name": short,
                        "arguments": json.dumps(args, ensure_ascii=False) if args else None,
                    }
                ]
            return [
                {
                    "type": "tool_result",
                    "tool_call_id": call_id,
                    "name": state.tool_names.get(call_id, short),
                    "result": _mcp_result_text(item.get("result")),
                    "is_error": str(item.get("status") or "") == "failed",
                }
            ]
        if kind == "commandExecution":
            command = str(item.get("command") or "")
            if started:
                if call_id in state.announced:
                    return []
                state.announced.add(call_id)
                state.tool_names[call_id] = "codex_execute_command"
                return [
                    {
                        "type": "tool_call",
                        "tool_call_id": call_id,
                        "name": "codex_execute_command",
                        "arguments": json.dumps({"command": command}, ensure_ascii=False),
                    }
                ]
            output = item.get("aggregatedOutput") or item.get("output") or ""
            return [
                {
                    "type": "tool_result",
                    "tool_call_id": call_id,
                    "name": "codex_execute_command",
                    "result": str(output)[:4000],
                    "is_error": bool(item.get("exitCode")) if item.get("exitCode") is not None else False,
                }
            ]
        return []

    @staticmethod
    def _usage_frame(token_usage: dict[str, Any], state: _RunState) -> dict[str, Any] | None:
        """``thread/tokenUsage/updated`` 给的是累计值，按差值记账。"""
        total = token_usage.get("total") or {}
        total_tokens = int(total.get("totalTokens") or 0)
        if total_tokens <= 0:
            return None
        delta = max(0, total_tokens - state.last_total)
        state.last_total = total_tokens
        input_tokens = max(
            0,
            int(total.get("inputTokens") or 0)
            - int(total.get("cachedInputTokens") or 0)
            - int(total.get("cacheWriteInputTokens") or 0),
        )
        cached = int(total.get("cachedInputTokens") or 0)
        cache_write = int(total.get("cacheWriteInputTokens") or 0)
        output = int(total.get("outputTokens") or 0)
        if delta <= 0:
            return None
        state.input_tokens, state.output_tokens = input_tokens, output
        state.cache_read_tokens, state.cache_write_tokens = cached, cache_write
        return {
            "type": "usage",
            "input_tokens": input_tokens,
            "output_tokens": output,
            "cache_read_tokens": cached,
            "cache_write_tokens": cache_write,
        }

    # ── 网关 / 工具面 ────────────────────────────────────────────────────

    async def _resolve_gateway(self, ctx: RunContext) -> dict[str, Any]:
        settings = await sync_to_async(get_gateway_settings, thread_sensitive=True)(ctx.model)
        target = resolve_gateway_target(settings, ctx.model, api_key=ctx.api_key)
        if settings is None or target is None:
            raise BackendError(
                BackendErrorKind.UNAVAILABLE,
                "未配置可用的 AI 平台（base_url / api_key），codex 无法启动；请联系管理员",
            )
        return {"base_url": target.base_url, "api_key": target.api_key, "model": target.model}

    def _mcp(self, ctx: RunContext, session_id: str) -> tuple[str | None, dict[str, str]]:
        token = (ctx.user_token or "").strip()
        if not token or not shared_enabled():
            logger.warning("codex 本轮无业务工具（token 缺失或共享 MCP 已禁用）")
            return None, {}
        endpoint = endpoint_from_env()
        if not port_open(endpoint.host, endpoint.port):
            logger.warning("共享 MCP 未监听 %s，codex 本轮无业务工具", endpoint.url)
            return None, {}
        return endpoint.url, {
            "Authorization": f"Bearer {token}",
            SESSION_HEADER: session_id,
            TOOL_TIER_HEADER: tool_tier(),
        }


def _approval_identity(method: str, params: dict[str, Any]) -> tuple[str | None, dict[str, Any], str]:
    """把 codex 的审批请求映射成 ``(工具名, 参数, call_id)``。

    名字带 ``codex_execute_command`` / ``codex_rewrite_file`` 是**故意的**：它们命中
    ``services/approval/risk.py`` 的 ``DANGER_PATTERNS``（``execute_`` / ``rewrite_``），
    因此必然判 HIGH、必然弹审批卡。换成 ``codex_shell`` 会被判低风险直接放行。
    """
    call_id = str(params.get("itemId") or "")
    if method == "item/commandExecution/requestApproval":
        return "codex_execute_command", {"command": str(params.get("command") or "")}, call_id
    if method in {"item/fileChange/requestApproval", "applyPatchApproval"}:
        return "codex_rewrite_file", {"paths": params.get("paths") or params.get("changes") or []}, call_id
    if method == "item/permissions/requestApproval":
        return "codex_execute_command", {"permissions": params.get("permissions") or {}}, call_id
    return None, {}, call_id


def _mcp_result_text(result: Any) -> str:
    if isinstance(result, dict):
        parts: list[str] = []
        for block in result.get("content") or []:
            text = block.get("text") if isinstance(block, dict) else None
            if isinstance(text, str):
                parts.append(text)
        if parts:
            return "\n".join(parts)
        return json.dumps(result, ensure_ascii=False)[:4000]
    return "" if result is None else str(result)[:4000]
