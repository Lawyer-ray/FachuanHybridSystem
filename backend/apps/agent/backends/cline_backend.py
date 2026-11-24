"""cline 后端：把「Node 桥 + ``@cline/core``」接成 ``AgentBackend``。

## 为什么要有 Node 桥

cline 只发 npm SDK（`@cline/core`），**没有可执行文件**；本后端是 Python。
`backend/devtools/cline_bridge.mjs` 就是那层薄桥：用 stdio 行分隔 JSON 收发我们
契约里的那几种帧。桥的职责只有三件（写 cline 的 MCP 设置文件、建 `ClineCore`、
翻事件），业务判断一律留在 Python 侧。

## 实测事实（2026-11-25，`@cline/core` 0.2.1）

| 能力 | 结论 |
|:-|:-|
| 无 VSCode 宿主可跑 | ✅ `ClineCore.create({backendMode:"local"})` |
| 指律所网关 | ✅ `providerId:"openai-compatible"` + `baseUrl` + `apiKey`（`providerId:"openai"` 会报 unknown provider） |
| 挂共享 MCP | ✅ 写 `$CLINE_DIR/data/settings/cline_mcp_settings.json`，`type:"streamableHttp"` + 自定义头 |
| 逐字流 | ✅ 每个 `content_start(contentType:"text")` 的 `text` 就是一段增量 |
| 工具事件 | ✅ `contentType:"tool"` 的 `content_start` / `content_end`，工具名形如 `fachuan__<tool>` |
| 执行前审批 | ❌ 未接：cline 的 `ToolApprovalRequest` 走它自己的 capabilities 通道，本桥暂未接线 |

所以 ``capabilities.approval = False`` 是**事实**：高危 MCP 工具仍由 **MCP 服务端闸门**
（``tool_approval_gate``）拦，与用哪个后端无关；cline 自己的内置工具当前没有人工闸门，
启用前需要合规确认（与 ``dsh`` 同待遇）。

## 隔离

`CLINE_DIR` 是 cline 的数据根（实测：`resolveDefaultMcpSettingsPath()` 直接跟着它走），
所以每个会话一份 `CLINE_DIR`（0700）＝ 会话数据、MCP 设置、sqlite 全隔离，PII 不出会话。
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

KIND = "cline"

#: Node 可执行文件（``FACHUAN_CLINE_NODE`` 可覆盖）。
NODE_ENV = "FACHUAN_CLINE_NODE"

#: 桥脚本路径（默认取仓库里的 ``backend/devtools/cline_bridge.mjs``）。
BRIDGE_ENV = "FACHUAN_CLINE_BRIDGE"

#: ``@cline/core`` 的位置：包名（默认）或 dist 绝对路径。
SDK_ENV = "FACHUAN_CLINE_SDK"

#: 工具面分层（默认 full：与 codex 的教训一致——lite 会让冷门工具「看起来不存在」）。
TIER_ENV = "FACHUAN_CLINE_TOOL_TIER"

#: 稳定目录根（与其它后端共用）。
HOME_ENV = "FACHUAN_AGENT_HOME"
DEFAULT_AGENT_HOME = "~/.fachuan-agent"

#: 单轮等待上限（秒）。cline 首轮会把整份工具面塞进 prompt（实测 ~76k token）。
ROUND_TIMEOUT = 600.0

#: 收尾事实保留条数。
MAX_KEPT_RESULTS = 32


def node_bin() -> str:
    explicit = os.environ.get(NODE_ENV, "").strip()
    if explicit:
        return explicit
    return shutil.which("node") or "node"


def bridge_path() -> Path:
    explicit = os.environ.get(BRIDGE_ENV, "").strip()
    if explicit:
        return Path(explicit).expanduser()
    # backend/apps/agent/backends/cline_backend.py → backend/devtools/cline_bridge.mjs
    return Path(__file__).resolve().parents[3] / "devtools" / "cline_bridge.mjs"


def sdk_specifier() -> str:
    return os.environ.get(SDK_ENV, "").strip() or "@cline/core"


def tool_tier() -> str:
    raw = os.environ.get(TIER_ENV, "").strip().lower()
    return raw if raw in {TIER_LITE, TIER_FULL} else TIER_FULL


def is_available() -> bool:
    """桥与 node 都在就算可用（**不拉进程、不查库**，切换器每次打开都会问）。"""
    return shutil.which(node_bin()) is not None and bridge_path().is_file()


def agent_home() -> Path:
    raw = os.environ.get(HOME_ENV, "").strip() or DEFAULT_AGENT_HOME
    return Path(raw).expanduser()


def session_dir(session_id: str) -> Path:
    """某会话的稳定目录（0700）：``<home>/cline/<session_id>``。"""
    path = agent_home() / "cline" / session_id
    (path / "work").mkdir(parents=True, exist_ok=True)
    (path / "data").mkdir(parents=True, exist_ok=True)
    for target in (path, path / "data"):
        try:
            target.chmod(0o700)
        except OSError:  # pragma: no cover - 非 POSIX
            logger.debug("cline 目录 chmod 0700 失败：%s", target)
    return path


def normalize_tool_name(raw: str) -> tuple[str, str]:
    """``fachuan__asean_law_countries`` → ``("asean_law_countries", "mcp__fachuan__asean_law_countries")``。

    cline 用 ``<server>__<tool>`` 双下划线拼接；审批口径要求 ``mcp__<server>__<tool>``。
    不归一化的话 ``short_tool_name`` 只认 ``mcp__fachuan__`` 前缀，写类工具会被判成
    低风险（静默失效家族，opencode 那栏踩过同一个坑）。
    """
    name = (raw or "").strip()
    if not name:
        return "", ""
    if name.startswith(tool_prefix()):
        return name[len(tool_prefix()) :], name
    server, sep, tool = name.partition("__")
    if sep and tool:
        if server == SERVER_NAME:
            return tool, f"{tool_prefix()}{tool}"
        return tool, name
    return name, name


def build_env(
    *,
    run_dir: Path,
    base_url: str,
    api_key: str,
    model: str,
    mcp_url: str | None,
    mcp_headers: dict[str, str],
) -> dict[str, str]:
    """桥子进程环境：隔离数据目录 + 剔代理 + 塞网关与 MCP 配置。"""
    env = {k: v for k, v in os.environ.items() if k.lower() not in {"http_proxy", "https_proxy", "all_proxy"}}
    env.update(
        {
            "CLINE_DIR": str(run_dir / "data"),
            "CLINE_SDK": sdk_specifier(),
            "CLINE_MODEL": model,
            "CLINE_BASE_URL": base_url,
            "CLINE_API_KEY": api_key,
            "CLINE_CWD": str(run_dir / "work"),
            "CLINE_SYSTEM_PROMPT": "你是法穿（律师事务系统）的业务助手，只用中文回答。",
            "CLINE_MCP_NAME": SERVER_NAME,
            "NO_PROXY": "*",
            "no_proxy": "*",
        }
    )
    if mcp_url:
        env["CLINE_MCP_URL"] = mcp_url
        env["CLINE_MCP_HEADERS"] = json.dumps(mcp_headers, ensure_ascii=False)
    return env


@dataclass(frozen=True)
class ClineRunResult:
    """收尾事实（``AgentRun.model`` 靠它回写）。"""

    model: str
    context_used: int | None = None
    context_total: int | None = None


class ClineHandle(LiveBackendHandle):
    """本轮控制柄：cline 只有 abort，没有插话。"""

    kind = KIND

    def __init__(self, *, run_id: str, proc: asyncio.subprocess.Process) -> None:
        self.run_id = run_id
        self._proc = proc

    async def steer(self, message: str) -> str:
        return "unsupported"

    async def follow_up(self, message: str) -> str:
        return "unsupported"

    async def abort(self) -> bool:
        """给桥发 ``{"type":"abort"}``；桥再调 ``cline.abort(sessionId)``。"""
        if self._proc.stdin is None or self._proc.returncode is not None:
            return False
        try:
            self._proc.stdin.write(b'{"type":"abort"}\n')
            await self._proc.stdin.drain()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False

    async def get_stats(self) -> dict[str, Any]:
        return {}


class ClineBackend:
    """cline 运行时（每次 ``stream()`` 拉起一条 ``node cline_bridge.mjs``）。"""

    kind = KIND
    capabilities: BackendCapabilities

    _results: OrderedDict[str, ClineRunResult]

    def __init__(self) -> None:
        self.capabilities = BackendCapabilities(
            streaming=True,  # content_start(text) 的 text 就是增量（实测）
            tool_calls=True,  # contentType:"tool" 的 start/end（实测）
            approval=False,  # 未接 cline 自己的 ToolApprovalRequest（事实，不是待办）
            compaction=False,  # 每轮新会话上下文，历史由编排层渲染
            steer=False,  # 只有 abort
            concurrent_in_session=True,
        )
        self._results = OrderedDict()

    def result_for(self, run_id: str) -> ClineRunResult | None:
        return self._results.get(run_id)

    def _remember_result(self, run_id: str, result: ClineRunResult) -> None:
        self._results[run_id] = result
        self._results.move_to_end(run_id)
        while len(self._results) > MAX_KEPT_RESULTS:
            self._results.popitem(last=False)

    def stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        return self._stream(ctx)

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        resolved = await self._resolve_gateway(ctx)
        run_dir = session_dir(str(ctx.session.session_id))
        mcp_url, mcp_headers = self._mcp(ctx, str(ctx.session.session_id))
        env = build_env(
            run_dir=run_dir,
            base_url=resolved["base_url"],
            api_key=resolved["api_key"],
            model=resolved["model"],
            mcp_url=mcp_url,
            mcp_headers=mcp_headers,
        )
        binary = node_bin()
        bridge = bridge_path()
        if not bridge.is_file():
            raise BackendError(BackendErrorKind.UNAVAILABLE, f"找不到 cline 桥脚本：{bridge}")
        try:
            proc = await asyncio.create_subprocess_exec(
                binary,
                str(bridge),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
                cwd=str(run_dir / "work"),
            )
        except FileNotFoundError:
            raise BackendError(
                BackendErrorKind.UNAVAILABLE,
                f"找不到 node 可执行文件（{binary}）；cline 需要 Node 运行时，请先安装或用 {NODE_ENV} 指定",
            ) from None

        state: set[str] = set()
        try:
            await self._send(proc, {"type": "prompt", "text": ctx.prompt, "model": resolved["model"]})
            async for frame in self._pump(ctx, proc, state):
                yield frame
        finally:
            await self._shutdown(proc)
        self._remember_result(ctx.run_id, ClineRunResult(model=resolved["model"]))

    async def _pump(
        self,
        ctx: RunContext,
        proc: asyncio.subprocess.Process,
        announced: set[str],
    ) -> AsyncGenerator[StreamFrame, None]:
        """读桥的每一行 JSON，翻成契约帧；收到 ``done`` 结束。"""
        assert proc.stdout is not None
        while True:
            raw = await asyncio.wait_for(proc.stdout.readline(), timeout=ROUND_TIMEOUT)
            if not raw:
                return
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("{"):
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = str(message.get("type") or "")
            if kind in {"ready"}:
                continue
            if kind == "done":
                return
            if kind == "error":
                raise BackendError(BackendErrorKind.UNKNOWN, str(message.get("message") or "cline 失败")[:300])
            frame = self._frame(kind, message, announced)
            if frame is not None:
                yield {**frame, "agent": self.kind, "run_id": ctx.run_id}

    def _frame(self, kind: str, message: dict[str, Any], announced: set[str]) -> dict[str, Any] | None:
        """桥帧 → 契约帧（工具名在这里归一化）。"""
        if kind == "delta":
            text = message.get("content")
            return {"type": "delta", "content": text} if isinstance(text, str) and text else None
        if kind == "thinking":
            text = message.get("content")
            return {"type": "thinking", "content": text} if isinstance(text, str) and text else None
        if kind == "usage":
            return {
                "type": "usage",
                "input_tokens": max(0, int(message.get("input_tokens") or 0)),
                "output_tokens": max(0, int(message.get("output_tokens") or 0)),
                "cache_read_tokens": max(0, int(message.get("cache_read_tokens") or 0)),
                "cache_write_tokens": max(0, int(message.get("cache_write_tokens") or 0)),
            }
        if kind == "tool_call":
            call_id = str(message.get("tool_call_id") or "")
            short, _full = normalize_tool_name(str(message.get("name") or ""))
            if not call_id or call_id in announced:
                return None
            announced.add(call_id)
            args = message.get("arguments")
            return {
                "type": "tool_call",
                "tool_call_id": call_id,
                "name": short,
                "arguments": json.dumps(args, ensure_ascii=False) if args else None,
            }
        if kind == "tool_result":
            call_id = str(message.get("tool_call_id") or "")
            short, _full = normalize_tool_name(str(message.get("name") or ""))
            return {
                "type": "tool_result",
                "tool_call_id": call_id,
                "name": short,
                "result": str(message.get("result") or ""),
                "is_error": bool(message.get("is_error")),
            }
        return None

    @staticmethod
    async def _send(proc: asyncio.subprocess.Process, payload: dict[str, Any]) -> None:
        if proc.stdin is None:
            return
        proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
        await proc.stdin.drain()

    async def _shutdown(self, proc: asyncio.subprocess.Process) -> None:
        try:
            if proc.stdin is not None and proc.returncode is None:
                proc.stdin.write(b'{"type":"shutdown"}\n')
                await proc.stdin.drain()
                proc.stdin.close()
        except (BrokenPipeError, ConnectionResetError):
            pass
        if proc.returncode is None:
            proc.kill()
        await proc.wait()

    async def _resolve_gateway(self, ctx: RunContext) -> dict[str, Any]:
        settings = await sync_to_async(get_gateway_settings, thread_sensitive=True)(ctx.model)
        target = resolve_gateway_target(settings, ctx.model, api_key=ctx.api_key)
        if settings is None or target is None:
            raise BackendError(
                BackendErrorKind.UNAVAILABLE,
                "未配置可用的 AI 平台（base_url / api_key），cline 无法启动；请联系管理员",
            )
        return {"base_url": target.base_url, "api_key": target.api_key, "model": target.model}

    def _mcp(self, ctx: RunContext, session_id: str) -> tuple[str | None, dict[str, str]]:
        token = (ctx.user_token or "").strip()
        if not token or not shared_enabled():
            logger.warning("cline 本轮无业务工具（token 缺失或共享 MCP 已禁用）")
            return None, {}
        endpoint = endpoint_from_env()
        if not port_open(endpoint.host, endpoint.port):
            logger.warning("共享 MCP 未监听 %s，cline 本轮无业务工具", endpoint.url)
            return None, {}
        return endpoint.url, {
            "Authorization": f"Bearer {token}",
            SESSION_HEADER: session_id,
            TOOL_TIER_HEADER: tool_tier(),
        }


__all__ = [
    "KIND",
    "ClineBackend",
    "ClineHandle",
    "ClineRunResult",
    "bridge_path",
    "build_env",
    "is_available",
    "node_bin",
    "normalize_tool_name",
    "sdk_specifier",
    "session_dir",
    "tool_tier",
]
