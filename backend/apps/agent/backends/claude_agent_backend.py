"""claude-agent —— 第五个 agent 运行时（Claude Agent SDK 驱动 ``claude`` 子进程）。

## 为什么是它（三条硬约束，与 ``apps/agent/README.md §2`` 同口径）

| 约束 | 满足方式 |
|:-|:-|
| 工具调用前能**阻塞**等人工审批 | ``ClaudeAgentOptions.can_use_tool`` 是 ``async`` 回调 |
| 能**挂起**等外部系统决策 | 回调内 ``await request_approval(...)``（实测 300s 不超时、不取消） |
| 能挂**共享 MCP** | ``mcp_servers`` 支持 ``type="http"`` + 自定义 headers |

它跟 pi 是同一类东西：**拉起一个 CLI 子进程、把消息流回 Python**。区别是它说的是
**Anthropic Messages 协议**，而 pi / dsh / openai-agents / antigravity 都走
OpenAI 兼容端点——这正是它在四栏并答里的对照价值。

## 五条实测事实（2026-11-22，网关 LiteLLM 1.85.1）

1. **``ANTHROPIC_BASE_URL`` 不能带 ``/v1``**：库里 ``LLMProvider.base_url`` 存的是
   ``.../v1``，CLI 会自己追加 ``/v1/messages``，直接照抄会得到
   ``/v1/v1/messages``（404）。同型坑见 ``antigravity_gateway.py``。
2. **Anthropic 协议下只有部分模型可用**：``glm53`` 把思考塞进 ``text`` 块 →
   正文为空（空回合）；``kimi-2.6`` 不带思考参数时正常。所以模型必须按
   :data:`ANTHROPIC_MODEL_MARKER` 过滤，**不能**把 OpenAI 通道的模型清单直接搬过来。
3. **``can_use_tool`` 会被三种配置静默跳过**：``permission_mode="bypassPermissions"``、
   整工具级 ``allowed_tools``、settings 文件里的 ``permissions.allow``。所以本模块
   把 ``permission_mode="default"`` / ``allowed_tools=[]`` / ``setting_sources=[]``
   写死成常量（:data:`_HARDENED_PERMISSION_MODE` 等），**不暴露给调用方**。
4. **内置工具必须四件套才关得干净**：``tools=[]`` + ``setting_sources=[]`` +
   ``strict_mcp_config=True`` + ``skills=[]``。少任何一个，CLI 仍会带出文件 / 命令 /
   子 agent 工具（antigravity 踩过同一个坑：默认 18 个内置工具）。
5. **``env`` 是叠加语义**（与 codex 相反）：宿主 ``os.environ`` 里的
   ``ANTHROPIC_*`` 与代理变量会渗进子进程。所以本模块显式覆盖全部相关变量，
   并把代理变量置空——律所网关是内网地址，带着 Clash 去访问是「502 无 body」
   （见 ``dsh_config.without_proxy_env`` 的记录）。

## 与其它后端的口径差异（都是刻意的）

- **``steer=False``**：SDK 支持 ``client.query(priority=...)``，但「运行中插话可能被
  并入当前 turn」的语义与 pi 的 ``queued`` 不同，且需要 :class:`LiveBackendHandle`
  接线。能力声明必须如实——先 False，接线并验证后再改。
- **``compaction=True``**：CLI 自带 autocompact（``PreCompact`` 钩子 + 水位 API），
  编排层不必再渲染 transcript。代价是**事件面无压缩信号**，只能从 ``usage`` 看水位。
- **不发 ``done``**：与 ``pi_backend`` / ``openai_agents_backend`` / ``antigravity``
  同口径，``done`` 由编排层铸（后端再发一条会让单栏出现两条 ``done``）。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import tempfile
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from asgiref.sync import sync_to_async

from .base import BackendCapabilities, BackendError, BackendErrorKind, RunContext, StreamFrame
from .gateway_cache import GatewaySettings, get_gateway_settings, resolve_gateway_target
from .toolface import SERVER_NAME, TIER_FULL, TIER_LITE, TOOL_TIER_HEADER, endpoint_from_env, port_open, shared_enabled

logger = logging.getLogger(__name__)

#: 后端标识。进事件流的 ``agent`` 字段与 ``AgentRun`` 归因，**改名等于历史数据对不上**。
KIND = "claude-agent"

#: 审批闸门开关（默认开）。关掉时 ``approval`` 能力声明同步为 ``False``——
#: 「声明与实现同源」，见 ``openai_agents_backend.approval_enabled`` 的同款说明。
APPROVAL_ENV = "FACHUAN_CLAUDE_APPROVAL"

#: 显式指定 CLI 路径（离线部署把自己放的二进制指过来）。留空则用 SDK 随 wheel
#: 分发的内置二进制，再退回 PATH 上的 ``claude``。
CLI_PATH_ENV = "FACHUAN_CLAUDE_CLI_PATH"

#: 工具面档位（``lite`` / ``full``）。**默认 ``lite``**：Anthropic 协议的
#: ``tools`` 声明比 OpenAI 通道更占预算（full 档实测 8.3 万 token/轮），而
#: 我们只在 ``lite`` 档验证过这条通道能稳定工作。
TOOL_TIER_ENV = "FACHUAN_CLAUDE_TOOL_TIER"

#: 一段通用的拒绝文案（律师拒绝时作为工具结果回给模型）。
APPROVAL_REJECTED_MESSAGE = "律师未批准该操作（已拒绝），请换一个只读方案或告知用户需要人工处理。"

#: 等下一个消息的上限（秒）。超时 ``yield None`` 让出一个 tick——编排层只在后端
#: yield 时排空事件总线，而审批卡正是从那条总线来的。与其它后端同一取值。
TICK_TIMEOUT_SECONDS = 0.2

#: 一轮内最多模型循环次数。与 ``openai_agents_backend.MAX_TURNS`` 同值同因：
#: 超限的代价是**这一栏一个字都不产出**，不是降级。
MAX_TURNS = 24

#: Anthropic 协议下可用的模型名特征（小写子串匹配 ``LLMProvider.extra_models``）。
#:
#: 为什么必须有这道过滤：同一个网关，``glm53`` 走 ``/v1/messages`` 会把思考
#: 塞进 ``text`` 块，正文为空（实测 3/3 次空回合）。把 OpenAI 通道的模型清单
#: 直接搬过来，用户会看到「空白答案」而不是报错。
ANTHROPIC_MODEL_MARKER = "anthropic"

#: 权限三件套（写死，不给调用方覆盖）。理由见模块 docstring 第 3 条。
_HARDENED_PERMISSION_MODE = "default"

#: 共享 MCP 的连接超时（秒）。与 ``TOOL_TIMEOUT_SECONDS`` 对齐。
MCP_CLIENT_TIMEOUT_SECONDS = 200.0

#: 明确危险、不该交给模型的工具（MCP 原始名，不带 ``mcp__fachuan__`` 前缀）。
#: 与 ``openai_agents_backend.BLOCKED_TOOL_NAMES`` 同口径；SDK 没有工具过滤器，
#: 所以在审批回调里直接拒。
BLOCKED_TOOL_NAMES: frozenset[str] = frozenset({"delete_case"})


# ── 配置解析（纯函数，便于离线测试）────────────────────────────────────


def approval_enabled() -> bool:
    """审批闸门是否启用（默认启用）。"""
    raw = os.environ.get(APPROVAL_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def tool_tier() -> str:
    """本轮工具面档位；未知取值一律回落 ``lite``（fail-safe）。"""
    raw = os.environ.get(TOOL_TIER_ENV, TIER_LITE).strip().lower()
    return TIER_FULL if raw == TIER_FULL else TIER_LITE


def backend_capabilities() -> BackendCapabilities:
    """能力声明。``approval`` 与开关同源，其余是静态事实。"""
    return BackendCapabilities(
        streaming=True,
        tool_calls=True,
        approval=approval_enabled(),
        # CLI 自带 autocompact（PreCompact + 水位 API），编排层不必再渲染 transcript。
        compaction=True,
        # SDK 支持 client.query(priority=...)，但需要 LiveBackendHandle 接线；
        # 未接线前声明 True 会让前端渲染出「敲进去也没人接」的插话框。
        steer=False,
        # 每轮一条独立子进程，无进程级共享状态（与 openai-agents 同口径）。
        concurrent_in_session=True,
    )


def anthropic_base_url(base_url: str) -> str:
    """``LLMProvider.base_url`` → ``ANTHROPIC_BASE_URL``（**剥掉尾部 ``/v1``**）。

    CLI 自己拼 ``/v1/messages``，这里再留一个 ``/v1`` 就会得到
    ``/v1/v1/messages``（实测 404）。同时剥掉尾部斜杠，避免 ``/v1/`` 这种写法漏网。
    """
    url = (base_url or "").strip().rstrip("/")
    if url.endswith("/v1"):
        url = url[: -len("/v1")].rstrip("/")
    return url


def select_anthropic_model(settings: GatewaySettings | None, model_hint: str | None) -> str | None:
    """挑一个 Anthropic 协议下可用的模型；没有则 ``None``。

    解析顺序：

    1. ``model_hint`` 非空 → 只有它命中特征才返回，**否则直接 ``None``**；
    2. ``model_hint`` 为空 → 试 ``default_model``，再试白名单里第一个命中的。

    ## 为什么显式指定不命中时**不回落**到别的模型

    ``resolve_gateway_target`` 的口径是「白名单表达有哪些可选，显式指定但不在
    白名单里照用」——那边模型名错了只会让网关报错，用户看得见。这里不行：
    这条路上一旦拿到不兼容的模型会**静默产出空答案**（``glm53`` 实测 3/3 次空
    正文），比报错难查得多。而「回落成另一个能用的模型」又违反 ``RunContext.model``
    的「不要静默换模型」——用户以为跑的是 glm53，账上也记成 glm53。
    两种坏结果都比「入口报错」差，所以选报错。
    """
    if settings is None:
        return None

    def ok(name: str) -> bool:
        return ANTHROPIC_MODEL_MARKER in name.lower()

    if model_hint:
        return model_hint if ok(model_hint) else None
    if settings.default_model and ok(settings.default_model):
        return settings.default_model
    for name in settings.models:
        if ok(name):
            return name
    return None


def build_env(*, base_url: str, api_key: str, model: str, cli_path: str | None) -> dict[str, str]:
    """给 ``claude`` 子进程的环境变量（**覆盖**宿主同名变量）。

    ## 为什么每一项都是必须的

    - ``ANTHROPIC_BASE_URL`` / ``ANTHROPIC_API_KEY`` / ``ANTHROPIC_MODEL``：走自家网关
      的唯一方式（SDK 没有 base_url 参数，只有 env 透传）。
    - 代理变量**置空**：SDK 的 ``env`` 是叠加语义，宿主的 ``HTTPS_PROXY``（本机
      Clash）会渗进来，导致访问内网网关得到「502 无 body」且重试 5 次。
      ``NO_PROXY`` 也一并写上（双保险：空串在某些客户端里语义不稳）。
    - ``CLAUDE_CONFIG_DIR``：会话配置目录独立，避免加载开发机上的 user settings
      （那里可能有 hooks / permissions.allow —— 后者会**绕过**我们的审批回调）。
    - ``DISABLE_TELEMETRY`` / ``DISABLE_ERROR_REPORTING``：不往厂商侧发送会话内容。
    """
    cfg_dir = Path(tempfile.gettempdir()) / "fachuan-claude-config"
    cfg_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    env = {
        "ANTHROPIC_BASE_URL": anthropic_base_url(base_url),
        "ANTHROPIC_API_KEY": api_key,
        "ANTHROPIC_MODEL": model,
        "CLAUDE_CONFIG_DIR": str(cfg_dir),
        "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1",
        # 代理变量置空：内网网关必须直连。
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
        "ALL_PROXY": "",
        "http_proxy": "",
        "https_proxy": "",
        "all_proxy": "",
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    }
    if cli_path:
        env["FACHUAN_CLAUDE_CLI_PATH"] = cli_path
    return env


def build_mcp_servers(*, url: str, user_token: str, session_id: str) -> dict[str, dict[str, Any]]:
    """共享 MCP 的 ``mcp_servers`` 配置（``type="http"`` + headers）。

    ``Authorization`` 与 ``x-fachuan-session`` 都是**必须**的：
    - 前者是律师本人的业务读权限凭据（:8011 强制 Bearer，且刻意不回退服务账号）；
    - 后者让 MCP 服务端的审批闸门把审批卡投到正确会话，不带时会建「无会话单」，
      只有超管能批 → 等于高危工具全拒。

    工具名会被 SDK 暴露成 ``mcp__fachuan__<原始名>``，与审批链的匹配口径一致
    （见 ``toolface/constants.py`` 的说明）。
    """
    return {
        SERVER_NAME: {
            "type": "http",
            "url": url,
            "headers": {
                "Authorization": f"Bearer {user_token}",
                "x-fachuan-session": session_id,
                TOOL_TIER_HEADER: tool_tier(),
            },
        }
    }


def short_tool_name(tool_name: str) -> str:
    """``mcp__fachuan__delete_case`` → ``delete_case``（非 MCP 名原样返回）。"""
    prefix = f"mcp__{SERVER_NAME}__"
    return tool_name[len(prefix) :] if tool_name.startswith(prefix) else tool_name


# ── 收尾事实 ────────────────────────────────────────────────────────────


@dataclass
class ClaudeAgentRunResult:
    """一轮跑完后的事实（编排层用它回写会话模型与 ``AgentRun``）。"""

    model: str
    context_used: int = 0
    context_total: int = 0


@dataclass
class _RunState:
    """单轮的事件翻译状态。**按 run_id 归集**：后端是单例且允许多会话并发。"""

    #: 本轮**是否见过流式 text delta**（只由 ``text_delta`` 置真）。
    #:
    #: 判据是「流式通道通不通」，**不是**「发过没有」：
    #:
    #: - 流式通（``include_partial_messages`` 生效）→ 正文已逐块发过，
    #:   ``AssistantMessage`` 兜底必须**完全关掉**，否则同一段正文出现两遍；
    #: - 流式不通（网关不吐 partial）→ 每一轮 ``AssistantMessage`` 的 TextBlock
    #:   都要发——工具循环里第 2、3 轮才有正文。
    #:
    #: 2026-11-22 会话 335 的事故正是把判据写成了「发过任何帧」：第一轮的
    #: ``tool_call`` 帧把标志置真，后续所有正文被当成"已发过"丢掉，症状是
    #: 「只有工具卡片、一个字正文都没有，但 AgentRun 记了 1745 output token」。
    saw_stream_text: bool = False
    #: ``content_block`` index → 该块的状态（type / tool 名 / 累积的 JSON 片段）。
    blocks: dict[int, dict[str, Any]] = field(default_factory=dict)
    #: 累计用量（``message_start`` 与 ``message_delta`` 分两处给）。
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reported_usage: bool = False
    #: ``tool_use_id`` → 工具名（``tool_result`` 只有 id）。
    tool_names: dict[str, str] = field(default_factory=dict)


class ClaudeAgentBackend:
    """Claude Agent SDK 运行时（每次 ``stream()`` 拉起一条 ``claude`` 子进程）。"""

    kind = KIND

    capabilities: BackendCapabilities

    #: 按 ``run_id`` 归集的收尾事实（并发两轮互不覆盖）。
    _results: dict[str, ClaudeAgentRunResult]
    #: 按 ``run_id`` 归集的翻译状态。
    _states: dict[str, _RunState]

    def __init__(self) -> None:
        self.capabilities = backend_capabilities()
        self._results = {}
        self._states = {}

    def result_for(self, run_id: str) -> ClaudeAgentRunResult | None:
        """取某一轮的收尾事实；未跑过 / 本轮异常时为 ``None``。"""
        return self._results.get(run_id)

    def stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        """跑一轮，产出 SSE 事件（``agent`` / ``run_id`` 已带）。

        Raises:
            BackendError: 网关不可用 / 模型不支持 Anthropic 通道 / SDK 异常。
                ``asyncio.CancelledError`` 原样上抛（用户按停止不是错误）。
        """
        return self._stream(ctx)

    # ── 主流程 ──────────────────────────────────────────────────────────

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        # 延迟 import：SDK 未安装时本模块仍可被注册表 import（见 builtin 的说明）。
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        resolved = await self._resolve_gateway(ctx)
        self._results.pop(ctx.run_id, None)
        self._states[ctx.run_id] = _RunState()
        session_id = str(ctx.session.session_id)

        options = ClaudeAgentOptions(
            env=build_env(
                base_url=resolved["base_url"],
                api_key=resolved["api_key"],
                model=resolved["model"],
                cli_path=(os.environ.get(CLI_PATH_ENV, "").strip() or None),
            ),
            model=resolved["model"],
            # 内置工具全关（四件套见模块 docstring 第 4 条）。业务工具全部来自 MCP。
            tools=[],
            skills=[],
            setting_sources=[],
            strict_mcp_config=True,
            permission_mode=_HARDENED_PERMISSION_MODE,
            allowed_tools=[],
            mcp_servers=resolved["mcp_servers"],
            system_prompt=_instructions(ctx),
            max_turns=MAX_TURNS,
            # 逐 token 增量：不开只有「整段 assistant 消息」一种粒度，
            # 前端表现为长时间空白后突然出现一大段。兜底路径见 ``_translate``。
            include_partial_messages=True,
            can_use_tool=_can_use_tool,
        )

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(ctx.prompt)
                async for msg in _with_ticks(client.receive_response()):
                    if msg is None:
                        # 本 tick 无新消息：让出一帧，编排层借它把审批事件推进来。
                        yield None
                        continue
                    for frame in self._translate(msg, ctx.run_id):
                        yield {**frame, "agent": self.kind, "run_id": ctx.run_id}

                    result_msg = _result_message(msg)
                    if result_msg is not None:
                        usage = self._usage_frame(result_msg)
                        self._results[ctx.run_id] = ClaudeAgentRunResult(model=resolved["model"])
                        if usage is not None:
                            yield {**usage, "agent": self.kind, "run_id": ctx.run_id}
                        break
        except BackendError:
            raise
        except BaseException as exc:
            # 边界处统一转 ``BackendError``（base.py 的硬要求）。用 ``BaseException``
            # 而不是 ``Exception`` 是为了**把取消显式放行**：``CancelledError`` 必须
            # 原样上抛——包成 BackendError 会让编排层把「用户按了停止」记成运行失败，
            # ``AgentRun`` 的成功率统计就废了。与 ``openai_agents_backend._run`` /
            # ``dsh_backend`` 的同类边界同口径。
            if isinstance(exc, (asyncio.CancelledError, GeneratorExit)):
                raise
            logger.warning("claude-agent 本轮失败 session=%s run=%s", session_id, ctx.run_id, exc_info=True)
            raise self._wrap_error(exc) from exc
        finally:
            self._states.pop(ctx.run_id, None)

    async def _resolve_gateway(self, ctx: RunContext) -> dict[str, Any]:
        """解析网关 + 模型 + MCP 配置；不可用时抛可读的 ``BackendError``。"""
        # 读库走 ``sync_to_async``：``get_gateway_settings`` 未命中时会读同步 ORM，
        # 直接在事件循环里调会抛 ``SynchronousOnlyOperation``。它内部已把查询异常
        # 吞成 warning + ``None``（见 ``gateway_cache._load``），所以这里不必再包一层
        # ``except``——真正「没有可用平台」由下面的 ``None`` 分支报可读错误。
        settings = await sync_to_async(get_gateway_settings, thread_sensitive=True)(ctx.model)

        target = resolve_gateway_target(settings, ctx.model, api_key=ctx.api_key)
        if settings is None or target is None:
            raise BackendError(
                BackendErrorKind.UNAVAILABLE,
                "未配置可用的 AI 平台（base_url / api_key），claude-agent 无法启动；请联系管理员",
            )

        model = select_anthropic_model(settings, ctx.model)
        if model is None:
            raise BackendError(
                BackendErrorKind.UNAVAILABLE,
                "当前 AI 平台没有 Anthropic 协议可用的模型"
                f"（模型名需含 {ANTHROPIC_MODEL_MARKER!r}），claude-agent 无法启动；"
                "请在「AI 平台」里补一个 Anthropic 格式的模型名后重试",
            )

        return {
            "base_url": target.base_url,
            "api_key": target.api_key,
            "model": model,
            "mcp_servers": self._mcp_servers(ctx),
        }

    def _mcp_servers(self, ctx: RunContext) -> dict[str, dict[str, Any]]:
        """本轮该连哪个 MCP；不该连/连不上返回空 dict（降级为「无工具但能对话」）。"""
        token = (ctx.user_token or "").strip()
        if not token:
            logger.warning("claude-agent 本轮没有律师 token，无业务工具（仍可对话）")
            return {}
        if not shared_enabled():
            logger.warning("共享 MCP 已禁用（FACHUAN_MCP_SHARED=0），claude-agent 本轮无业务工具")
            return {}
        endpoint = endpoint_from_env()
        if not port_open(endpoint.host, endpoint.port):
            logger.warning("共享 MCP %s 不可连，claude-agent 本轮无业务工具", endpoint.url)
            return {}
        return build_mcp_servers(url=endpoint.url, user_token=token, session_id=str(ctx.session.session_id))

    # ── 事件翻译 ────────────────────────────────────────────────────────

    def _translate(self, msg: Any, run_id: str) -> list[dict[str, Any]]:
        """SDK 消息 → 0..n 个 SSE 事件（契约见 ``sse_types.py``）。

        正文/思考走 ``StreamEvent``（``include_partial_messages`` 打开时的原始 API
        事件）；工具调用在 ``content_block_stop`` 时才发（此时 ``input_json_delta``
        已拼完）；工具结果走 ``UserMessage`` 里的 ``ToolResultBlock``。
        """
        from claude_agent_sdk import (
            AssistantMessage,
            StreamEvent,
            TextBlock,
            ToolResultBlock,
            ToolUseBlock,
            UserMessage,
        )

        state = self._states.get(run_id)
        if state is None:
            return []

        if isinstance(msg, StreamEvent):
            event = msg.event if isinstance(msg.event, dict) else {}
            return self._translate_stream_event(event, state)

        if isinstance(msg, AssistantMessage):
            frames: list[dict[str, Any]] = []
            for block in msg.content:
                if isinstance(block, TextBlock) and block.text and not state.saw_stream_text:
                    # 兜底：仅当流式通道没吐过正文时，把整段补上。
                    # 工具循环里每一轮 assistant 消息都可能带正文，所以这里
                    # **不复位任何标志**——不置真，下一轮继续能发。
                    frames.append({"type": "delta", "content": block.text})
                elif isinstance(block, ToolUseBlock) and block.id not in state.tool_names:
                    # 同理兜底：没有 stream 事件时也要让前端看到工具调用。
                    state.tool_names[block.id] = block.name
                    frames.append(
                        {
                            "type": "tool_call",
                            "tool_call_id": block.id,
                            "name": block.name,
                            "arguments": json.dumps(block.input, ensure_ascii=False) if block.input else None,
                        }
                    )
            return frames

        if isinstance(msg, UserMessage):
            frames = []
            content = msg.content if isinstance(msg.content, list) else []
            for block in content:
                if isinstance(block, ToolResultBlock):
                    frames.append(
                        {
                            "type": "tool_result",
                            "tool_call_id": block.tool_use_id,
                            "name": state.tool_names.get(block.tool_use_id, ""),
                            "result": _stringify(block.content),
                            "is_error": bool(getattr(block, "is_error", False)),
                        }
                    )
            return frames

        return []

    @staticmethod
    def _translate_stream_event(event: dict[str, Any], state: _RunState) -> list[dict[str, Any]]:
        """一个 Anthropic 原始流事件 → 0..n 帧。

        只认四种事件；其余（``message_start`` / ``content_block_stop`` /
        ``message_stop`` …）只更新状态、不发帧，避免把生命周期事件刷进前端。
        """
        etype = str(event.get("type") or "")

        if etype == "message_start":
            usage = (event.get("message") or {}).get("usage") or {}
            state.input_tokens += int(usage.get("input_tokens") or 0)
            state.cache_read_tokens += int(usage.get("cache_read_input_tokens") or 0)
            state.cache_write_tokens += int(usage.get("cache_creation_input_tokens") or 0)
            if usage:
                state.reported_usage = True
            return []

        if etype == "content_block_start":
            index = int(event.get("index") or 0)
            block = event.get("content_block") or {}
            btype = str(block.get("type") or "")
            state.blocks[index] = {
                "type": btype,
                "name": block.get("name") or "",
                "id": block.get("id") or "",
                "json": "",
            }
            return []

        if etype == "content_block_delta":
            index = int(event.get("index") or 0)
            block = state.blocks.get(index) or {}
            delta = event.get("delta") or {}
            dtype = str(delta.get("type") or "")
            if dtype == "text_delta":
                text = str(delta.get("text") or "")
                if not text:
                    return []
                state.saw_stream_text = True
                return [{"type": "delta", "content": text}]
            if dtype == "thinking_delta" and block.get("type") == "thinking":
                # 只在真正的 thinking 块里转发。网关的部分路由会把 thinking_delta
                # 塞进 text 块（协议违例），那种一律不转——转了会让前端把思考当正文。
                text = str(delta.get("thinking") or "")
                return [{"type": "thinking", "content": text}] if text else []
            if dtype == "input_json_delta":
                block["json"] = str(block.get("json") or "") + str(delta.get("partial_json") or "")
                state.blocks[index] = block
            return []

        if etype == "content_block_stop":
            index = int(event.get("index") or 0)
            block = state.blocks.pop(index, None) or {}
            if block.get("type") != "tool_use":
                return []
            call_id = str(block.get("id") or "")
            name = str(block.get("name") or "")
            if not call_id or not name:
                return []
            state.tool_names[call_id] = name
            raw = str(block.get("json") or "")
            return [
                {
                    "type": "tool_call",
                    "tool_call_id": call_id,
                    "name": name,
                    "arguments": raw or None,
                }
            ]

        if etype == "message_delta":
            usage = event.get("usage") or {}
            state.output_tokens += int(usage.get("output_tokens") or 0)
            # 部分路由只在 message_delta 里给 input_tokens（message_start 恒 0）。
            state.input_tokens = max(state.input_tokens, int(usage.get("input_tokens") or 0))
            state.cache_read_tokens = max(state.cache_read_tokens, int(usage.get("cache_read_input_tokens") or 0))
            state.cache_write_tokens = max(state.cache_write_tokens, int(usage.get("cache_creation_input_tokens") or 0))
            if usage:
                state.reported_usage = True
            return []

        return []

    @staticmethod
    def _usage_frame(result_msg: Any) -> dict[str, Any] | None:
        """一轮结束时的 ``usage`` 帧（一轮**只发一帧**）。

        优先用 ``ResultMessage.usage``（SDK 汇总的整轮值）；它缺失时退回流事件
        累加值。**拿不到就返回 ``None``**（不发 0/0 假帧：编造的 0 无法与真实 0 区分）。
        """
        usage = getattr(result_msg, "usage", None) or {}
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        cache_read = int(usage.get("cache_read_input_tokens") or 0)
        cache_write = int(usage.get("cache_creation_input_tokens") or 0)
        if input_tokens + output_tokens <= 0:
            return None
        return {
            "type": "usage",
            "input_tokens": max(0, input_tokens),
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read,
            "cache_write_tokens": cache_write,
        }

    # ── 错误分类 ────────────────────────────────────────────────────────

    @staticmethod
    def _wrap_error(exc: BaseException) -> BackendError:
        """SDK / CLI 异常 → ``BackendError``（分类口径见 ``base.py`` 的映射表）。"""
        if isinstance(exc, BackendError):
            return exc
        name = type(exc).__name__
        text = (str(exc) or name).lower()

        if "notfound" in name.lower() or "not found" in text:
            return BackendError.wrap(exc, BackendErrorKind.UNAVAILABLE)
        if "connection" in name.lower() or "timeout" in name.lower():
            return BackendError.wrap(exc, BackendErrorKind.UNAVAILABLE, retryable=True)
        if "401" in text or "403" in text or "api key" in text or "unauthorized" in text:
            return BackendError.wrap(exc, BackendErrorKind.AUTH)
        if "429" in text or "rate limit" in text:
            return BackendError.wrap(exc, BackendErrorKind.RATE_LIMITED, retryable=True)
        if "context" in text and ("window" in text or "length" in text or "overflow" in text):
            return BackendError.wrap(exc, BackendErrorKind.CONTEXT_OVERFLOW)
        return BackendError.wrap(exc, BackendErrorKind.UNKNOWN)


# ── 审批回调（模块级：SDK 只要求 callable）──────────────────────────────


def _instructions(ctx: RunContext) -> str:
    """本轮的 system prompt（全量替换 CLI 默认预设，**不是追加**）。"""
    del ctx
    return (
        "你是法穿法律事务系统的助手。用户是执业律师。"
        "需要事实时必须调用工具查询，不得编造案件、当事人、金额、期限或法条。"
        "回答简洁、直接给结论，再给依据。"
    )


async def _can_use_tool(tool_name: str, tool_input: dict[str, Any], context: Any) -> Any:
    """高危工具执行前的审批闸门。

    **这是本后端能声明 ``approval=True`` 的唯一依据**，但只有在
    ``permission_mode="default"`` + ``allowed_tools=[]`` + ``setting_sources=[]``
    同时成立时才真的会被调用（其余组合会静默跳过，见模块 docstring 第 3 条）。

    拒绝一律返回 ``PermissionResultDeny``（**不抛异常**）：抛异常会被 SDK 包成
    「工具故障」，而真实语义是「律师拒了，本轮继续，模型换个只读方案」。
    """
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

    from ..services.approval import RiskLevel, classify_risk, request_approval
    from ..services.approval.policy import multi_lane_write_refusal

    args = tool_input if isinstance(tool_input, dict) else {}
    short = short_tool_name(tool_name)

    # 1) 不可逆删除类：连审批卡都不该弹，直接不给。
    if short in BLOCKED_TOOL_NAMES:
        return PermissionResultDeny(message=f"该操作（{short}）已被系统禁用，请换只读方案。")

    ctx: RunContext | None = getattr(context, "context", None)
    session_id = str(getattr(getattr(ctx, "session", None), "session_id", "") or "")
    run_id = str(getattr(ctx, "run_id", "") or "")
    user_id = getattr(ctx, "user_id", None)

    # 2) 多栏并答时禁止写（结构性冲突，不是偏好问题）。
    refusal = multi_lane_write_refusal(session_id=session_id or None, tool_name=tool_name)
    if refusal:
        return PermissionResultDeny(message=refusal)

    # 3) 分级：只有高危 / 紧急才停下来问人。
    if classify_risk(tool_name, args) not in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return PermissionResultAllow()

    approved, _approval_id, _reason = await request_approval(
        tool_name=tool_name,
        tool_args=args,
        user_id=user_id,
        session_id=session_id,
        run_id=run_id,
    )
    if approved:
        return PermissionResultAllow()
    return PermissionResultDeny(message=APPROVAL_REJECTED_MESSAGE)


# ── 杂项 ────────────────────────────────────────────────────────────────


def _stringify(value: Any) -> str:
    """工具结果 → 文本（字符串原样，其余 JSON 序列化）。"""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _result_message(msg: Any) -> Any | None:
    """``ResultMessage`` 判定（延迟 import，避免模块级依赖 SDK）。"""
    try:
        from claude_agent_sdk import ResultMessage
    except ImportError:  # pragma: no cover - SDK 缺失时不会跑到这里
        return None
    return msg if isinstance(msg, ResultMessage) else None


async def _with_ticks(source: AsyncIterator[Any]) -> AsyncGenerator[Any | None, None]:
    """把 SDK 的消息流包成「有消息给消息、静默给 ``None``」的 tick 流。

    为什么必须让出：编排层只在后端 yield 时排空审批事件总线，而工具正在等
    ``_can_use_tool`` 的那段时间 SDK 一个消息都不产——不让出就表现为「工具在等
    审批，前端的审批卡永远不出现」。
    """
    pending: asyncio.Task[Any] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(source.__anext__())
            await asyncio.wait({pending}, timeout=TICK_TIMEOUT_SECONDS)
            if not pending.done():
                yield None
                continue
            task, pending = pending, None
            try:
                yield task.result()
            except StopAsyncIteration:
                return
    finally:
        if pending is not None:
            # 提前退出（done / 取消）时可能还挂着一次 __anext__，必须收掉，
            # 否则任务泄漏并在事件循环关闭时刷 "Task was destroyed" 警告。
            pending.cancel()
            with contextlib.suppress(BaseException):
                await pending


__all__ = [
    "ANTHROPIC_MODEL_MARKER",
    "APPROVAL_ENV",
    "APPROVAL_REJECTED_MESSAGE",
    "BLOCKED_TOOL_NAMES",
    "CLI_PATH_ENV",
    "ClaudeAgentBackend",
    "ClaudeAgentRunResult",
    "KIND",
    "TOOL_TIER_ENV",
    "anthropic_base_url",
    "approval_enabled",
    "backend_capabilities",
    "build_env",
    "build_mcp_servers",
    "select_anthropic_model",
    "short_tool_name",
    "tool_tier",
]
