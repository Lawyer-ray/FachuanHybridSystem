"""opencode 后端：把「``opencode acp`` 子进程跑一轮」接成 ``AgentBackend``。

第六个运行时（pi / dsh / openai-agents / antigravity / claude-agent 之后）。
走 opencode 的 **ACP**（Agent Client Protocol，stdio 上的 JSON-RPC），
不是它的 HTTP API —— 选型依据是实测，见
``docs/harness/backend/opencode-probe.md``：

| | HTTP（``opencode serve`` + ``/api/*``） | **ACP（``opencode acp``）** |
|:-|:-|:-|
| 430 个 MCP 工具进工具面 | ❌ 只有 12 个内置工具 | ✅ 实测 ``inputTokens=80810``，模型逐条报出 ``fachuan_*`` |
| 逐字流 | 正文还要另拉 ``/message`` | ✅ 一轮 630 个 ``agent_message_chunk`` |
| 审批往返 | 未接通 | ✅ ``session/request_permission`` 阻塞往返 |
| usage | 有 | ✅ ``prompt`` 的 result 直接带 token |

## 本模块管什么

1. **ACP 客户端**：拉起子进程 → ``initialize`` → ``session/new``（挂共享 MCP）
   → ``session/prompt`` → 读通知流。JSON-RPC 全部在本模块内实现（stdlib，无新依赖）。
2. **事件翻译**：``session/update`` 的通知 → ``sse_types.py`` 的契约事件。
3. **人工审批**：``session/request_permission`` 转给 ``services/approval`` 的四级判定，
   按结果回 ``once`` / ``reject``。

**不接管**（留在编排层 ``services/chat/stream.py``）：铸造用户凭证、写
``AgentMessage`` / ``AgentRun``、发 ``meta`` / ``done``、订阅事件总线。边界与
``pi_backend`` / ``claude_agent_backend`` 完全一致，理由见 ``base.py``。

## 能力声明是事实，不是愿望（每条都有实测依据）

- ``streaming=True``：``agent_message_chunk`` 逐块到达（实测一轮 630 块）。
- ``tool_calls=True``：``tool_call`` / ``tool_call_update`` 两种通知都在。
- ``approval``：由 :data:`APPROVAL_ENV` 决定，默认 ``True``。关掉时既不处理
  ``session/request_permission`` 也不声明能力（两处写死一份必然说谎）。
- ``compaction=True``：会话历史归 opencode 自己管（它自带 compaction agent，
  每轮同一会话复用**稳定目录**），编排层不渲染 transcript —— 与 pi 同口径。
- ``steer=False``：ACP 只有 ``session/cancel``，没有插话入口。
- ``concurrent_in_session=True``：每次 ``stream()`` 自建进程与目录，无跨请求可变状态。

## 三条实测出来的坑（写在这里防止后人踩回去）

1. **审批请求里没有工具名**，也没有参数：``toolCall`` 只有 ``title`` / ``kind`` /
   ``rawInput``，而 MCP 工具在审批那一刻 ``rawInput`` 是**空的**（参数要等批准后
   ``tool_call_update`` 才有）。所以：
   - 名字只能从 ``title`` 取（MCP 工具恰好等于工具 id，见 :func:`normalize_tool_name`）；
   - **带参数的判定必须留在 MCP 服务端闸门**（``tool_approval_gate``）——与
     ``dsh_backend`` 注释里的既有口径一致。
2. **工具名带 ``fachuan_`` 前缀**（``fachuan_delete_case``），而四级审批按
   ``mcp__fachuan__delete_case`` 匹配。不做归一化会**静默降级成低风险**
   （``short_tool_name`` 只剥 ``mcp__fachuan__``），闸门形同虚设。
3. **配置目录隔离会打断 provider**：provider 的 npm 包（``@ai-sdk/openai-compatible``）
   从配置目录的 ``node_modules`` 解析，新目录里没有就报
   ``ModelUnavailableError``。所以每个会话目录都软链一份共享 ``node_modules``。
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
    tool_prefix,
)

logger = logging.getLogger(__name__)

KIND = "opencode"

#: ``APPROVAL_ENV`` 为假时既不处理审批请求、也不声明 ``approval`` 能力。
APPROVAL_ENV = "FACHUAN_OPENCODE_APPROVAL"

#: opencode 二进制（``FACHUAN_OPENCODE_BIN`` 可覆盖，与 claude-agent 的 CLI 同思路）。
BIN_ENV = "FACHUAN_OPENCODE_BIN"
DEFAULT_BIN = "opencode"

#: 共享 ``node_modules`` 目录（provider 的 npm 包从配置目录解析，见模块 docstring 第 3 条）。
MODULES_ENV = "FACHUAN_OPENCODE_MODULES"

#: 稳定工作目录根（默认跟随 pi 的 ``FACHUAN_AGENT_HOME``）。
HOME_ENV = "FACHUAN_AGENT_HOME"

#: 兜底默认值（与 pi 同口径）。
DEFAULT_AGENT_HOME = "~/.fachuan-agent"

#: 单轮模型循环上限，写进 opencode 的 agent 配置。
MAX_TURNS = 40

#: 收尾事实的保留条数（并发两轮互不覆盖；超出丢最旧）。
MAX_KEPT_RESULTS = 32

#: ACP 协议版本（``initialize`` 里协商，实测 opencode 1.18.30 回 1）。
ACP_PROTOCOL_VERSION = 1

#: 内置工具一律不进业务面（我们要的是「只能通过 MCP 碰数据」）。
#: 实测 opencode 1.18.30 的内置工具全集见探针记录；这里是**要拒绝**的那批。
BUILTIN_TOOLS = frozenset(
    {
        "bash",
        "read",
        "write",
        "edit",
        "patch",
        "apply_patch",
        "glob",
        "grep",
        "task",
        "webfetch",
        "websearch",
        "todowrite",
        "skill",
        "question",
        "invalid",
    }
)

#: 只有共享 MCP 工具的自定义 agent 名（写进 ``opencode.json`` 的 ``agent`` 段）。
#:
#: **为什么必须自定义 agent**：opencode 自带 14 个内置工具（``bash`` / ``edit`` /
#: ``read`` / ``grep`` / ``task`` / ``webfetch`` …），实测全部会进模型工具面。
#: 顶层 ``tools`` 字段对它**无效**（实测：写了也照样出现），必须写在 agent 上；
#: 而且 agent 还得被 ``session/set_config_option(mode=...)`` 选中才生效。
#: 实测结果：切到这个 agent 后工具面 = 430 个 ``fachuan_*``，内置工具 0 个。
FACHUAN_AGENT = SERVER_NAME

#: 审批被拒时回给模型的话（与 antigravity 同一句，避免同一语义两种文案）。
APPROVAL_REJECTED_MESSAGE = "该操作需要律师确认，已被拒绝；请换一种不需要写操作的方式继续。"

#: ``session/new`` 之后等 MCP 工具发现的上限（秒）。430 工具实测 ~1s。
MCP_DISCOVERY_TIMEOUT = 15.0

#: 单条 JSON-RPC 请求（``session/new`` / ``session/prompt`` 之外）的超时。
REQUEST_TIMEOUT = 60.0


def approval_enabled() -> bool:
    """本轮是否启用人工审批闸门（默认开）。"""
    raw = os.environ.get(APPROVAL_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def tool_tier() -> str:
    """MCP 工具面分层（``full`` / ``lite``），与 claude-agent 的同一口径。"""
    raw = os.environ.get("FACHUAN_OPENCODE_TOOL_TIER", "").strip().lower()
    if raw in {TIER_LITE, TIER_FULL}:
        return raw
    return TIER_FULL


def resolve_bin() -> str:
    """opencode 可执行文件路径；找不到时返回原名（交给 ``FileNotFoundError`` 兜底）。"""
    explicit = os.environ.get(BIN_ENV, "").strip()
    if explicit:
        return explicit
    return shutil.which(DEFAULT_BIN) or DEFAULT_BIN


def normalize_tool_name(title: str) -> tuple[str, str]:
    """把 ACP 的 ``title`` 解成 ``(短名, 审批用全名)``。

    实测形状（opencode 1.18.30）：

    - MCP 工具：``title == "fachuan_asean_law_search"`` → 短名 ``asean_law_search``，
      全名 ``mcp__fachuan__asean_law_search``（与 pi / dsh 的匹配口径一致）；
    - 内置工具：``title == "echo hello-probe"``（bash 的 title 是命令原文）——
      认不出工具名，返回短名 ``""`` 让调用方 fail-closed。

    前缀取自 :func:`toolface.tool_prefix` 的 server 名，不硬编码字面量（改名的唯一
    来源见 ``toolface/constants.py``）。
    """
    raw = (title or "").strip()
    prefix = f"{SERVER_NAME}_"
    if not raw:
        return "", ""
    if raw.startswith(prefix):
        short = raw[len(prefix) :]
        return short, f"{tool_prefix()}{short}"
    if "__" in raw:
        return raw.rsplit("__", 1)[-1], raw
    if raw in BUILTIN_TOOLS:
        return raw, raw
    return "", ""


def agent_home() -> Path:
    """稳定目录根（与 pi 共用 ``FACHUAN_AGENT_HOME``）。"""
    raw = os.environ.get(HOME_ENV, "").strip() or DEFAULT_AGENT_HOME
    return Path(raw).expanduser()


def session_dir(session_id: str) -> Path:
    """某会话的稳定目录：``<home>/opencode/<session_id>``（0700）。

    为什么按**会话**而不是按轮：opencode 自己管会话历史（``compaction=True``），
    每轮换目录等于每轮失忆。律师数据隔离靠「一会话一目录 + 0700」，不靠「用完即删」。
    """
    path = agent_home() / "opencode" / session_id
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:  # pragma: no cover - 非 POSIX 或权限受限时保持原样
        logger.debug("opencode 会话目录 chmod 0700 失败：%s", path)
    return path


def shared_modules_dir() -> Path | None:
    """共享 ``node_modules``（放 provider 的 npm 包）；找不到返回 ``None``。"""
    explicit = os.environ.get(MODULES_ENV, "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_dir() else None
    candidate = Path("~/.config/opencode/node_modules").expanduser()
    return candidate if candidate.is_dir() else None


def build_provider_config(*, base_url: str, api_key: str, model: str, models: list[str]) -> dict[str, Any]:
    """写进 ``opencode.json`` 的 provider 段（OpenAI 兼容通道，实测可指律所网关）。

    ``models`` 里带上网关白名单的前几项，让 ``configOptions.model`` 里有备选；
    模型名**不写死**——全部来自 ``LLMProvider``。
    """
    names = [m for m in dict.fromkeys([model, *models]) if m][:8]
    return {
        "provider": {
            SERVER_NAME: {
                "npm": "@ai-sdk/openai-compatible",
                "name": "fachuan gateway",
                "options": {"baseURL": base_url, "apiKey": api_key},
                "models": {name: {"name": name} for name in names},
            }
        },
        "model": f"{SERVER_NAME}/{model}",
    }


def build_env(run_dir: Path) -> dict[str, str]:
    """子进程环境：隔离配置/数据目录 + 剔代理。

    **代理必须剔**：律所网关是内网地址，``HTTPS_PROXY`` 指向本地 Clash 时会
    「502 无 body」——与 ``dsh_config.without_proxy_env`` 是同一个坑。
    """
    env = {k: v for k, v in os.environ.items() if k.lower() not in {"http_proxy", "https_proxy", "all_proxy"}}
    env["XDG_CONFIG_HOME"] = str(run_dir / "cfg")
    env["XDG_DATA_HOME"] = str(run_dir / "data")
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    # 不让它开遥测（默认关，这里显式一次防止用户级配置打开）
    env["GOOSE_TELEMETRY_ENABLED"] = "0"
    return env


def _write_config(run_dir: Path, config: dict[str, Any], modules: Path | None) -> None:
    """写 ``<cfg>/opencode/opencode.json``（0600）并软链共享 ``node_modules``。"""
    cfg_dir = run_dir / "cfg" / "opencode"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / "opencode.json"
    payload = {"$schema": "https://opencode.ai/config.json", **config}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:  # pragma: no cover
        logger.debug("opencode.json chmod 0600 失败：%s", path)
    link = cfg_dir / "node_modules"
    if modules is not None and not link.exists():
        try:
            link.symlink_to(modules, target_is_directory=True)
        except OSError:  # pragma: no cover - 软链失败不致命（会退化成「模型不可用」）
            logger.warning("共享 node_modules 软链失败：%s -> %s", link, modules)


@dataclass
class _RunState:
    """一轮的翻译状态。"""

    #: 已发过 ``tool_call`` 的 id（``tool_call_update`` 不重复发名字）。
    announced: set[str] = field(default_factory=set)
    #: ``tool_call_id`` → 短名（``tool_call_update`` 只有 id）。
    tool_names: dict[str, str] = field(default_factory=dict)
    #: 被审批拒掉的 id：``tool_result`` 只发我们的拒绝文案，避免再来一个气泡。
    denied: set[str] = field(default_factory=set)
    #: 待发的帧。审批回调发生在「读事件」的调用栈里（不是生成器里），没法直接
    #: ``yield``，所以先排队，由 ``_pump`` 的下一 tick 发出去。
    pending: list[dict[str, Any]] = field(default_factory=list)
    #: 累计用量（`prompt` 的 result 只有一份，但失败轮也要报）。
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


@dataclass(frozen=True)
class OpenCodeRunResult:
    """一轮的收尾事实（编排层在生成器结束后按 ``run_id`` 取）。

    为什么要有它：异步生成器的 return 值取不到，而 ``AgentRun.model`` 与
    ``AgentSession.llm_model`` 都靠这个值回写（见 ``services/chat/stream.py``
    的 ``result_for`` 段）。不实现它，账上 ``model`` 是空串，按模型聚合的用量
    统计就落不到这一栏（实测确认：e2e 第一次跑的 AgentRun.model == ""）。
    """

    model: str
    #: 上下文水位：opencode 的 ACP 只回「本轮 token 用量」，不报窗口上限，
    #: 所以两个字段都留 ``None``——宁可不显示，也不编一个错的数。
    context_used: int | None = None
    context_total: int | None = None


class _AcpConnection:
    """`opencode acp` 子进程 + JSON-RPC over stdio。

    只实现本后端用到的那一小片：请求/响应配对、通知入队、**服务端发起的请求**
    交给回调（审批）。认不出的服务端请求一律回 ``-32601``（fail-closed：
    我们没在 ``clientCapabilities`` 里声明文件系统/终端能力，它本就不该发）。
    """

    def __init__(self, proc: asyncio.subprocess.Process, on_request: Any) -> None:
        self._proc = proc
        self._on_request = on_request
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._reader = asyncio.create_task(self._read_loop())
        self.closed = False

    async def _read_loop(self) -> None:
        """读 stdout 的 ndjson，分发到 future 或事件队列。"""
        assert self._proc.stdout is not None
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", "replace").strip()
            if not text:
                continue
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                logger.debug("opencode acp 非 JSON 行（忽略）：%s", text[:200])
                continue
            await self._dispatch(msg)
        self.closed = True
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(BackendError(BackendErrorKind.UNKNOWN, "opencode acp 子进程已退出"))
        self._pending.clear()

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        """一条消息 → future / 事件队列 / 服务端请求回调。"""
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
            await self._events.put(msg)

    async def _handle_server_request(self, msg: dict[str, Any]) -> None:
        """服务端发起的请求。审批以外的（fs/terminal）一律拒绝。"""
        try:
            result = await self._on_request(msg)
        except (BackendError, RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
            # 审批回调里的任何业务失败都不能拖死读循环（否则整轮静默挂住）。
            # 不写 ``except Exception``：本仓有「新增宽异常捕获」棘轮，且
            # ``CancelledError`` 属于 BaseException，不在这些类型里，停止仍能穿透。
            logger.exception("opencode 请求处理失败：%s", msg.get("method"))
            await self._send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32603, "message": str(exc)}})
            return
        if result is None:
            await self._send(
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "error": {"code": -32601, "message": f"client does not support {msg.get('method')}"},
                }
            )
            return
        await self._send({"jsonrpc": "2.0", "id": msg["id"], "result": result})

    async def _send(self, payload: dict[str, Any]) -> None:
        """写一行 JSON-RPC（进程已退出时静默丢弃）。"""
        if self._proc.stdin is None or self.closed:
            return
        try:
            self._proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            self.closed = True

    async def request(self, method: str, params: dict[str, Any], *, timeout: float = REQUEST_TIMEOUT) -> dict[str, Any]:
        """发请求并等响应；``error`` 转成 :class:`BackendError`。"""
        self._next_id += 1
        rid = self._next_id
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        await self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            msg = await asyncio.wait_for(fut, timeout=timeout)
        except TimeoutError:
            self._pending.pop(rid, None)
            raise BackendError(BackendErrorKind.UNKNOWN, f"opencode {method} 超时（{timeout:.0f}s）") from None
        if "error" in msg:
            raise _error_from_jsonrpc(method, msg["error"])
        return msg.get("result") or {}

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        """发通知（不需响应）。"""
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def next_event(self) -> dict[str, Any] | None:
        """取一条通知；子进程已退出且队列空时返回 ``None``。"""
        if self.closed and self._events.empty():
            return None
        try:
            return await asyncio.wait_for(self._events.get(), timeout=1.0)
        except TimeoutError:
            return None

    async def close(self) -> None:
        """收尾：关 stdin → 等退出 → 强杀。"""
        try:
            if self._proc.stdin is not None:
                self._proc.stdin.close()
        except (BrokenPipeError, ConnectionResetError):
            pass
        self._reader.cancel()
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=5.0)
        except TimeoutError:
            self._proc.kill()
            await self._proc.wait()


def _error_from_jsonrpc(method: str, error: Any) -> BackendError:
    """JSON-RPC error → 用户能看懂的 :class:`BackendError`。"""
    message = ""
    if isinstance(error, dict):
        message = str(error.get("message") or "")
        data = error.get("data")
        if data:
            message = f"{message} {data}" if message else str(data)
    else:
        message = str(error)
    lowered = message.lower()
    if "auth" in lowered or "401" in message or "403" in message:
        return BackendError(BackendErrorKind.AUTH, f"opencode {method} 鉴权失败：{message}")
    if "rate" in lowered or "429" in message:
        return BackendError(BackendErrorKind.RATE_LIMITED, f"opencode {method} 被限流：{message}", retryable=True)
    if "context" in lowered or "token" in lowered:
        return BackendError(BackendErrorKind.CONTEXT_OVERFLOW, f"opencode {method} 上下文超限：{message}")
    return BackendError(BackendErrorKind.UNKNOWN, f"opencode {method} 失败：{message}")


class OpenCodeHandle(LiveBackendHandle):
    """本轮控制柄：中止走 ACP 的 ``session/cancel``，没有插话入口。"""

    kind = KIND

    def __init__(self, *, run_id: str, session_id: str, conn: _AcpConnection, state: _RunState) -> None:
        self.run_id = run_id
        self._session_id = session_id
        self._conn = conn
        self._state = state
        self._aborted = False

    async def steer(self, message: str) -> str:
        """不支持插话：返回 ``unsupported``（编排层只透传，不做语义分支）。"""
        return "unsupported"

    async def follow_up(self, message: str) -> str:
        """不支持追加轮：返回 ``unsupported``。"""
        return "unsupported"

    async def abort(self) -> bool:
        """中止本轮：发 ``session/cancel``。"""
        self._aborted = True
        await self._conn.notify("session/cancel", {"sessionId": self._session_id})
        return True

    async def get_stats(self) -> dict[str, Any]:
        """本轮用量（拿不到时返回空 dict，前端隐藏水位）。"""
        if self._state.input_tokens + self._state.output_tokens <= 0:
            return {}
        return {
            "input_tokens": self._state.input_tokens,
            "output_tokens": self._state.output_tokens,
            "cache_read_tokens": self._state.cache_read_tokens,
        }


def backend_capabilities() -> BackendCapabilities:
    """能力声明（``approval`` 与开关同源，其余是静态事实）。"""
    return BackendCapabilities(
        streaming=True,
        tool_calls=True,
        approval=approval_enabled(),
        compaction=True,
        steer=False,
        concurrent_in_session=True,
    )


class OpenCodeBackend:
    """opencode 运行时（每次 ``stream()`` 拉起一条 ``opencode acp`` 子进程）。"""

    kind = KIND
    capabilities: BackendCapabilities

    #: 按 ``run_id`` 归集的收尾事实（并发两轮互不覆盖）。
    _results: OrderedDict[str, OpenCodeRunResult]

    def __init__(self) -> None:
        self.capabilities = backend_capabilities()
        self._results = OrderedDict()

    def result_for(self, run_id: str) -> OpenCodeRunResult | None:
        """取某一轮的收尾事实；未跑过 / 已被挤出保留窗口时为 ``None``。"""
        return self._results.get(run_id)

    def _remember_result(self, run_id: str, result: OpenCodeRunResult) -> None:
        """记下本轮收尾事实，只保留最近 :data:`MAX_KEPT_RESULTS` 条。"""
        self._results[run_id] = result
        self._results.move_to_end(run_id)
        while len(self._results) > MAX_KEPT_RESULTS:
            self._results.popitem(last=False)

    def stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        """跑一轮，产出 SSE 事件（``agent`` / ``run_id`` 由本模块补）。

        Raises:
            BackendError: 二进制缺失 / 网关不可用 / 子进程异常。
                ``asyncio.CancelledError`` 原样上抛（用户按停止不是错误）。
        """
        return self._stream(ctx)

    # ── 主流程 ──────────────────────────────────────────────────────────

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        resolved = await self._resolve_gateway(ctx)
        state = _RunState()
        sid = str(ctx.session.session_id)
        run_dir = session_dir(sid)
        conn: _AcpConnection | None = None
        session_id = ""
        try:
            _write_config(run_dir, self._config_payload(resolved), shared_modules_dir())
            proc = await self._spawn(run_dir)
            conn = _AcpConnection(proc, self._make_request_handler(ctx, state))
            await self._handshake(conn)
            created = await conn.request(
                "session/new",
                {"cwd": str(run_dir / "work"), "mcpServers": self._mcp_servers(ctx, sid)},
                timeout=MCP_DISCOVERY_TIMEOUT + REQUEST_TIMEOUT,
            )
            session_id = str(created.get("sessionId") or "")
            if not session_id:
                raise BackendError(BackendErrorKind.UNKNOWN, "opencode 没有返回 sessionId")
            await self._apply_session_config(conn, session_id, resolved["model"])
            # **不登记到 live_sessions**：那张表是「同一会话只允许一个运行」的单槽表
            # （``live_sessions.register`` 会抛 ``SessionBusyError``），而本后端声明
            # ``concurrent_in_session=True``——多栏并答时三栏共用同一个会话，登记就撞车
            # （实测：pi 先登记，opencode 这一栏直接 SessionBusyError 挂掉）。
            # 中止走编排层取消生成器 → ``_pump`` 发 ``session/cancel``，不依赖那张表。
            async for frame in self._pump(ctx, conn, session_id, state):
                yield frame
            self._remember_result(ctx.run_id, OpenCodeRunResult(model=resolved["model"]))
        finally:
            if conn is not None:
                await conn.close()

    async def _pump(
        self,
        ctx: RunContext,
        conn: _AcpConnection,
        session_id: str,
        state: _RunState,
    ) -> AsyncGenerator[StreamFrame, None]:
        """发 prompt，边读通知边翻译；收到 prompt 的 result 即收尾。"""
        prompt_task = asyncio.create_task(
            conn.request(
                "session/prompt",
                {"sessionId": session_id, "prompt": [{"type": "text", "text": ctx.prompt}]},
                timeout=60.0 * 30,
            )
        )
        try:
            while True:
                while state.pending:
                    frame = state.pending.pop(0)
                    yield {**frame, "agent": self.kind, "run_id": ctx.run_id}
                if prompt_task.done():
                    break
                event = await conn.next_event()
                if event is None:
                    yield None
                    continue
                for frame in self._translate(event, state):
                    yield {**frame, "agent": self.kind, "run_id": ctx.run_id}
            result = await prompt_task
        except asyncio.CancelledError:
            await conn.notify("session/cancel", {"sessionId": session_id})
            prompt_task.cancel()
            raise
        finally:
            if not prompt_task.done():
                prompt_task.cancel()
        self._record_usage(state, result.get("usage"))
        usage = self._usage_frame(state)
        if usage is not None:
            yield {**usage, "agent": self.kind, "run_id": ctx.run_id}

    async def _spawn(self, run_dir: Path) -> asyncio.subprocess.Process:
        """拉起 ``opencode acp --pure``。"""
        binary = resolve_bin()
        (run_dir / "work").mkdir(parents=True, exist_ok=True)
        try:
            return await asyncio.create_subprocess_exec(
                binary,
                "acp",
                "--pure",
                "--cwd",
                str(run_dir / "work"),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=str(run_dir / "work"),
                env=build_env(run_dir),
            )
        except FileNotFoundError:
            raise BackendError(
                BackendErrorKind.UNAVAILABLE,
                f"找不到 opencode 可执行文件（{binary}）；请先安装 opencode 或设置 {BIN_ENV}",
            ) from None

    async def _handshake(self, conn: _AcpConnection) -> None:
        """``initialize``：只声明我们真的支持的能力（不声明 fs / terminal）。"""
        await conn.request(
            "initialize",
            {"protocolVersion": ACP_PROTOCOL_VERSION, "clientCapabilities": {}},
            timeout=REQUEST_TIMEOUT,
        )

    async def _apply_session_config(self, conn: _AcpConnection, session_id: str, model: str) -> None:
        """钉死本轮模型 + 切到业务 agent。

        **``mode`` 必须设成功**：切不过去就还是 ``build`` agent，那 14 个内置工具
        （``bash`` / ``edit`` / …）会回到工具面，模型就能绕过 MCP 直接改文件。
        所以这一步失败要**报错中止本轮**，不能像模型那样只留痕。
        """
        await conn.request(
            "session/set_config_option",
            {"sessionId": session_id, "configId": "mode", "value": FACHUAN_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        try:
            await conn.request(
                "session/set_config_option",
                {"sessionId": session_id, "configId": "model", "value": f"{SERVER_NAME}/{model}"},
                timeout=REQUEST_TIMEOUT,
            )
        except BackendError as exc:
            # 配置文件里已经写了同一个 model，设不上不影响本轮；这里只留痕。
            logger.info("opencode 设置模型失败（沿用配置默认）：%s", exc)

    # ── 网关 / 工具面 ────────────────────────────────────────────────────

    async def _resolve_gateway(self, ctx: RunContext) -> dict[str, Any]:
        """解析网关 + 模型；不可用时抛可读的 ``BackendError``。"""
        settings = await sync_to_async(get_gateway_settings, thread_sensitive=True)(ctx.model)
        target = resolve_gateway_target(settings, ctx.model, api_key=ctx.api_key)
        if settings is None or target is None:
            raise BackendError(
                BackendErrorKind.UNAVAILABLE,
                "未配置可用的 AI 平台（base_url / api_key），opencode 无法启动；请联系管理员",
            )
        return {
            "base_url": target.base_url,
            "api_key": target.api_key,
            "model": target.model,
            "models": list(settings.models),
        }

    def _config_payload(self, resolved: dict[str, Any]) -> dict[str, Any]:
        """``opencode.json`` 的内容：provider + 审批策略。"""
        payload = build_provider_config(
            base_url=resolved["base_url"],
            api_key=resolved["api_key"],
            model=resolved["model"],
            models=resolved["models"],
        )
        # 让 opencode 自己永远不要自行放行：所有工具都先问 client，再由四级判定决定。
        # 关掉审批开关时退回 allow（此时 capabilities.approval 也是 False，两处同源）。
        effect = "ask" if approval_enabled() else "allow"
        payload["permission"] = {"*": effect}
        # 业务 agent：只留共享 MCP 的工具。``tools: false`` 是 V1 的写法
        # （V2 的 ``permissions`` 规则集会被 1.18.30 直接判非法并拒绝整个配置）。
        payload["agent"] = {
            FACHUAN_AGENT: {
                "mode": "primary",
                "description": "法穿业务助手：工具全部来自共享 MCP",
                "tools": dict.fromkeys(sorted(BUILTIN_TOOLS), False),
            }
        }
        return payload

    def _mcp_servers(self, ctx: RunContext, session_id: str) -> list[dict[str, Any]]:
        """本轮该挂哪个 MCP；不挂时返回空列表（降级为「无工具但能对话」）。"""
        token = (ctx.user_token or "").strip()
        if not token:
            logger.warning("opencode 本轮没有律师 token，无业务工具（仍可对话）")
            return []
        if not shared_enabled():
            logger.warning("共享 MCP 已禁用（FACHUAN_MCP_SHARED=0），opencode 本轮无业务工具")
            return []
        endpoint = endpoint_from_env()
        if not port_open(endpoint.host, endpoint.port):
            logger.warning("共享 MCP 未监听 %s，opencode 本轮无业务工具", endpoint.url)
            return []
        return [
            {
                "type": "http",
                "name": SERVER_NAME,
                "url": endpoint.url,
                "headers": [
                    {"name": "Authorization", "value": f"Bearer {token}"},
                    {"name": SESSION_HEADER, "value": session_id},
                    {"name": TOOL_TIER_HEADER, "value": tool_tier()},
                ],
            }
        ]

    # ── 事件翻译 ────────────────────────────────────────────────────────

    def _translate(self, event: dict[str, Any], state: _RunState) -> list[dict[str, Any]]:
        """一条 ACP 通知 → 零个或多个契约事件。"""
        params = event.get("params") or {}
        update = params.get("update") or {}
        kind = str(update.get("sessionUpdate") or "")
        if kind == "agent_message_chunk":
            return self._text_frames(update, "delta")
        if kind == "agent_thought_chunk":
            return self._text_frames(update, "thinking")
        if kind == "tool_call":
            return self._tool_call_frame(update, state)
        if kind == "tool_call_update":
            return self._tool_update_frames(update, state)
        return []

    @staticmethod
    def _text_frames(update: dict[str, Any], frame_type: str) -> list[dict[str, Any]]:
        """``agent_message_chunk`` / ``agent_thought_chunk`` → ``delta`` / ``thinking``。"""
        content = update.get("content") or {}
        text = content.get("text") if isinstance(content, dict) else None
        if not text:
            return []
        return [{"type": frame_type, "content": text}]

    def _tool_call_frame(self, update: dict[str, Any], state: _RunState) -> list[dict[str, Any]]:
        """``tool_call`` → ``tool_call`` 事件（含短名与参数）。"""
        call_id = str(update.get("toolCallId") or "")
        if not call_id or call_id in state.announced:
            return []
        short, _full = normalize_tool_name(str(update.get("title") or ""))
        state.announced.add(call_id)
        if short:
            state.tool_names[call_id] = short
        args = update.get("rawInput")
        return [
            {
                "type": "tool_call",
                "tool_call_id": call_id,
                "name": short or str(update.get("title") or ""),
                "arguments": json.dumps(args, ensure_ascii=False) if args else None,
            }
        ]

    def _tool_update_frames(self, update: dict[str, Any], state: _RunState) -> list[dict[str, Any]]:
        """``tool_call_update`` → 只在 ``completed`` / ``failed`` 时发 ``tool_result``。"""
        call_id = str(update.get("toolCallId") or "")
        status = str(update.get("status") or "")
        if status not in {"completed", "failed"}:
            return []
        if call_id in state.denied:
            # 审批已拒：拒绝文案已经发过，别再补一条工具自身的结果。
            return []
        text = self._content_text(update.get("content"))
        return [
            {
                "type": "tool_result",
                "tool_call_id": call_id,
                "name": state.tool_names.get(call_id, ""),
                "result": text,
                "is_error": status == "failed",
            }
        ]

    @staticmethod
    def _content_text(content: Any) -> str:
        """``tool_call_update.content`` 是块数组，拼成一段文本。"""
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for block in content:
            inner = block.get("content") if isinstance(block, dict) else None
            if isinstance(inner, dict) and isinstance(inner.get("text"), str):
                parts.append(inner["text"])
        return "\n".join(parts)

    # ── 审批 ────────────────────────────────────────────────────────────

    def _make_request_handler(self, ctx: RunContext, state: _RunState) -> Any:
        """构造「服务端请求 → 我们怎么答」的回调（目前只有审批）。"""

        async def handle(msg: dict[str, Any]) -> dict[str, Any] | None:
            method = str(msg.get("method") or "")
            if method != "session/request_permission":
                logger.info("opencode 发来未支持的请求，已拒绝：%s", method)
                return None
            return await self._decide(ctx, state, msg.get("params") or {})

        return handle

    async def _decide(self, ctx: RunContext, state: _RunState, params: dict[str, Any]) -> dict[str, Any]:
        """四级判定 → ``once`` / ``reject``。

        **只按工具名判**：ACP 的审批请求里没有参数（见模块 docstring 第 1 条），
        带参数的判定由 MCP 服务端闸门兜底。
        """
        tool_call = params.get("toolCall") or {}
        call_id = str(tool_call.get("toolCallId") or "")
        short, full = normalize_tool_name(str(tool_call.get("title") or ""))
        if not full:
            logger.warning("opencode 审批请求认不出工具名，fail-closed 拒绝：%s", tool_call.get("title"))
            self._mark_denied(state, call_id, short)
            return _reject_outcome()
        if short in BUILTIN_TOOLS and full == short:
            logger.warning("opencode 试图使用内置工具，已拒绝：%s", short)
            self._mark_denied(state, call_id, short)
            return _reject_outcome()
        if not approval_enabled():
            return _allow_outcome()

        from ..services.approval import RiskLevel, classify_risk, request_approval

        if classify_risk(full, None) not in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return _allow_outcome()

        approved, _approval_id, _reason = await request_approval(
            tool_name=full,
            tool_args=None,
            user_id=ctx.user_id,
            session_id=str(ctx.session.session_id),
            run_id=ctx.run_id,
            tool_call_id=call_id,
        )
        if approved:
            return _allow_outcome()
        self._mark_denied(state, call_id, short)
        return _reject_outcome()

    @staticmethod
    def _mark_denied(state: _RunState, call_id: str, short: str) -> None:
        """记下拒绝并排一条 ``tool_result``。

        **必须自己发**：opencode 收到 ``reject`` 后只会推一条 ``status=failed`` 的
        ``tool_call_update``（不带我们的话术），随后就结束本轮——不补这条，前端只会
        看到一张永远转圈的工具卡，律师不知道「自己刚拒了它」。
        """
        state.denied.add(call_id)
        state.pending.append(
            {
                "type": "tool_result",
                "tool_call_id": call_id,
                "name": short,
                "result": APPROVAL_REJECTED_MESSAGE,
                "is_error": True,
            }
        )

    # ── 用量 ────────────────────────────────────────────────────────────

    @staticmethod
    def _record_usage(state: _RunState, usage: Any) -> None:
        """把 ``prompt`` 的 result.usage 记到状态（字段名见 ACP ``Usage``）。"""
        if not isinstance(usage, dict):
            return
        state.input_tokens = int(usage.get("inputTokens") or 0)
        state.output_tokens = int(usage.get("outputTokens") or 0)
        state.cache_read_tokens = int(usage.get("cachedReadTokens") or 0)

    @staticmethod
    def _usage_frame(state: _RunState) -> dict[str, Any] | None:
        """token 用量帧；全 0 时不发（宁可不报，也不要报一个假的 0）。"""
        if state.input_tokens + state.output_tokens <= 0:
            return None
        return {
            "type": "usage",
            "input_tokens": max(0, state.input_tokens),
            "output_tokens": state.output_tokens,
            "cache_read_tokens": max(0, state.cache_read_tokens),
            "cache_write_tokens": 0,
        }


def _allow_outcome() -> dict[str, Any]:
    """批准一次（``once`` 而不是 ``always``：不给模型留「以后都别问」的口子）。"""
    return {"outcome": {"outcome": "selected", "optionId": "once"}}


def _reject_outcome() -> dict[str, Any]:
    """拒绝一次。"""
    return {"outcome": {"outcome": "selected", "optionId": "reject"}}


#: 注册表用的探针：``builtin.py`` 据此判断「opencode 装了没」。
def is_available() -> bool:
    """opencode 二进制是否可用（``shutil.which`` 一次，不拉进程）。"""
    return shutil.which(resolve_bin()) is not None


__all__ = [
    "KIND",
    "OpenCodeBackend",
    "OpenCodeHandle",
    "agent_home",
    "approval_enabled",
    "backend_capabilities",
    "build_env",
    "build_provider_config",
    "is_available",
    "normalize_tool_name",
    "resolve_bin",
    "session_dir",
    "shared_modules_dir",
    "tool_tier",
]
