"""codex 后端：把「``codex exec --json`` 子进程跑一轮」接成 ``AgentBackend``。

## 为什么是 `exec --json` 而不是 `app-server`

codex 0.161 有两条可编程通道：

| 通道 | 能力 | 取舍 |
|:-|:-|:-|
| ``codex exec --json`` | JSONL 事件流（``item.started`` / ``item.completed`` / ``turn.completed``） | **本轮选它**：无状态、一行一条事件、失败面小 |
| ``codex app-server`` | JSON-RPC + **外部审批回调**（``CommandExecutionRequestApproval`` / ``ApplyPatchApprovalRequest``，实测由 ``generate-json-schema`` 列出） | 能拿到「执行前问客户端」，但要维护长连接与协议状态；留作下一步 |

所以本模块的能力声明里 ``approval=False``——**这是事实，不是待办**：
``exec`` 模式的实际值就是 ``approval_policy = Never``（日志实测）。
高危动作的强制闸门仍在 **MCP 服务端**（``tool_approval_gate``），与用哪个
agent 后端无关，codex 绕不过去。

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator

from asgiref.sync import sync_to_async

from .base import BackendCapabilities, BackendError, BackendErrorKind, RunContext, StreamFrame
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
    """codex 的 ``exec`` 通道**没有**外部审批回调，恒为 ``False``（如实声明）。"""
    return False


def tool_tier() -> str:
    """MCP 工具面分层（``full`` / ``lite``）。codex 的 prompt 更贵，默认给 lite。"""
    raw = os.environ.get("FACHUAN_CODEX_TOOL_TIER", "").strip().lower()
    if raw in {TIER_LITE, TIER_FULL}:
        return raw
    return TIER_LITE


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
    """``mcp_tool_call`` 的 ``(server, tool)`` → ``(短名, 审批用全名)``。

    codex 的事件里 server 与 tool 是分开的两个字段，比 opencode 的 ``title`` 可靠得多：
    ``{"server": "fachuan", "tool": "delete_case"}`` → ``("delete_case", "mcp__fachuan__delete_case")``。
    """
    tool = str(item.get("tool") or "").strip()
    server = str(item.get("server") or "").strip()
    if not tool:
        return "", ""
    if server == SERVER_NAME:
        return tool, f"mcp__{SERVER_NAME}__{tool}"
    return tool, f"{server}__{tool}" if server else tool


class CodexBackend:
    """codex 运行时（每次 ``stream()`` 拉起一条 ``codex exec --json``）。"""

    kind = KIND
    capabilities: BackendCapabilities

    _results: OrderedDict[str, CodexRunResult]

    def __init__(self) -> None:
        self.capabilities = BackendCapabilities(
            streaming=False,  # exec 只按 item 完成出事件（实测）
            tool_calls=True,
            approval=approval_enabled(),  # exec 没有外部审批回调，恒 False
            compaction=False,  # 每轮新 thread，历史由编排层渲染
            steer=False,
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
        sid = str(ctx.session.session_id)
        run_dir = session_dir(sid)
        home = run_dir / "home"
        work = run_dir / "work"
        with GatewayProxy() as proxy:
            proxy_base = proxy.lease(base_url=resolved["base_url"], api_key=resolved["api_key"])
            mcp_url, mcp_headers = self._mcp(ctx, sid)
            write_config(
                home,
                build_config(
                    proxy_base_url=proxy_base, model=resolved["model"], mcp_url=mcp_url, mcp_headers=mcp_headers
                ),
            )
            async for frame in self._run(ctx, home=home, work=work, resolved=resolved):
                yield frame
        self._remember_result(ctx.run_id, CodexRunResult(model=resolved["model"]))

    async def _run(
        self,
        ctx: RunContext,
        *,
        home: Path,
        work: Path,
        resolved: dict[str, Any],
    ) -> AsyncGenerator[StreamFrame, None]:
        """拉起 codex，逐行读 JSONL 并翻译。"""
        binary = resolve_bin()
        try:
            proc = await asyncio.create_subprocess_exec(
                binary,
                "exec",
                "--json",
                "--skip-git-repo-check",
                "-C",
                str(work),
                ctx.prompt,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=build_env(home, resolved["api_key"]),
                cwd=str(work),
            )
        except FileNotFoundError:
            raise BackendError(
                BackendErrorKind.UNAVAILABLE,
                f"找不到 codex 可执行文件（{binary}）；请先安装 codex 或设置 {BIN_ENV}",
            ) from None

        started: set[str] = set()
        failure: BackendError | None = None
        try:
            assert proc.stdout is not None
            while True:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=ROUND_TIMEOUT)
                if not raw:
                    break
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("{"):
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for frame in self._translate(event, started):
                    if frame.get("type") == "error":
                        failure = failure or BackendError(BackendErrorKind.UNKNOWN, str(frame.get("message") or ""))
                        continue
                    yield {**frame, "agent": self.kind, "run_id": ctx.run_id}
        finally:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()

        if failure is not None:
            raise failure

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
        """本轮 MCP 的 (url, headers)；不该挂时返回 ``(None, {})``。"""
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

    # ── 事件翻译 ────────────────────────────────────────────────────────

    def _translate(self, event: dict[str, Any], started: set[str]) -> list[dict[str, Any]]:
        """一条 codex JSONL → 零个或多个契约事件。"""
        kind = str(event.get("type") or "")
        if kind == "turn.failed":
            message = ((event.get("error") or {}).get("message")) or "codex 本轮失败"
            return [{"type": "error", "message": str(message)[:300], "code": "backend_failed"}]
        if kind == "turn.completed":
            usage = self._usage(event.get("usage"))
            return [usage] if usage else []
        if kind not in {"item.started", "item.completed"}:
            return []
        item = event.get("item") or {}
        item_type = str(item.get("type") or "")
        if item_type == "agent_message" and kind == "item.completed":
            text = str(item.get("text") or "")
            return [{"type": "delta", "content": text}] if text else []
        if item_type == "mcp_tool_call":
            return self._tool_frames(item, kind, started)
        return []

    def _tool_frames(self, item: dict[str, Any], event_kind: str, started: set[str]) -> list[dict[str, Any]]:
        """``mcp_tool_call``：``item.started`` 发 ``tool_call``，``item.completed`` 发 ``tool_result``。"""
        short, _full = normalize_tool_name(item)
        call_id = str(item.get("id") or "")
        if not call_id:
            return []
        if event_kind == "item.started":
            if call_id in started:
                return []
            started.add(call_id)
            args = item.get("arguments")
            return [
                {
                    "type": "tool_call",
                    "tool_call_id": call_id,
                    "name": short,
                    "arguments": json.dumps(args, ensure_ascii=False) if args else None,
                }
            ]
        text = self._result_text(item.get("result"))
        error = item.get("error")
        return [
            {
                "type": "tool_result",
                "tool_call_id": call_id,
                "name": short,
                "result": text if error is None else f"{text}\n{error}".strip(),
                "is_error": error is not None,
            }
        ]

    @staticmethod
    def _result_text(result: Any) -> str:
        """MCP 结果里的 ``content`` 数组 → 一段文本。"""
        if not isinstance(result, dict):
            return "" if result is None else str(result)[:4000]
        parts: list[str] = []
        for block in result.get("content") or []:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)

    @staticmethod
    def _usage(usage: Any) -> dict[str, Any] | None:
        """``turn.completed.usage`` → ``usage`` 帧。"""
        if not isinstance(usage, dict):
            return None
        input_tokens = int(usage.get("input_tokens") or 0)
        cached = int(usage.get("cached_input_tokens") or 0)
        write = int(usage.get("cache_write_input_tokens") or 0)
        output = int(usage.get("output_tokens") or 0)
        if input_tokens + output <= 0:
            return None
        return {
            "type": "usage",
            "input_tokens": max(0, input_tokens - cached - write),
            "output_tokens": output,
            "cache_read_tokens": cached,
            "cache_write_tokens": write,
        }


__all__ = [
    "KIND",
    "CodexBackend",
    "CodexRunResult",
    "approval_enabled",
    "build_config",
    "build_env",
    "is_available",
    "normalize_tool_name",
    "resolve_bin",
    "session_dir",
    "tool_tier",
]
