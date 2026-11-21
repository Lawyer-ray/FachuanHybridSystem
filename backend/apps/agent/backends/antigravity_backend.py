"""antigravity 后端：把「一轮 ``Agent.chat()`` → SSE 事件」接成 ``AgentBackend``。

第四个后端（pi / DeepSeek Harness / openai-agents 之后）。走
`Google Antigravity SDK <https://github.com/google-antigravity/antigravity-sdk-python>`_：
Python 侧只管配置与事件，真正的 agent 循环在随 wheel 分发的 Go 二进制
``bin/localharness`` 里（每次 ``stream()`` 起一个进程，实测 118MB RSS / 冷启 0.2s）。

## 本模块管什么

1. **网关**：base_url / key / 模型**全部来自数据库 ``LLMProvider``**
   （``gateway_cache.get_gateway_settings`` + ``resolve_gateway_target``，与
   pi / dsh / openai-agents 同一份解析，不另写一套）。
2. **鉴权补丁**：SDK 的 OpenAI 兼容通道**不发任何 auth 头**，而律所网关强制
   Bearer——所以走 :mod:`antigravity_gateway` 的 loopback 反向代理补头。
   这是本后端与其它三个后端最大的结构差异，细节见该模块 docstring。
3. **事件翻译**：SDK 的 ``Text`` / ``Thought`` 增量 + 工具钩子 →
   ``sse_types.py`` 的契约事件（见 :meth:`AntigravityBackend._translate_chunk`）。
4. **人工审批**：``PreToolCallDecideHook`` 里走 ``services/approval`` 的四级判定
   （与其它入口同一张审批卡、同一份阈值），拒绝时返回
   ``HookResult(allow=False)``——工具不执行、本轮继续。

**不接管**（留在编排层 ``services/chat/stream.py``）：铸造用户凭证、写
``AgentMessage`` / ``AgentRun``、发 ``meta`` / ``done``、订阅事件总线。边界与
``pi_backend`` / ``dsh_backend`` / ``openai_agents_backend`` 完全一致

## 能力声明是事实，不是愿望

- ``streaming=True``：真的逐 token 产出 ``delta`` / ``thinking``（``Text`` /
  ``Thought`` 分块，不是整段补发）。
- ``tool_calls=True``：真的产出 ``tool_call`` / ``tool_result``（来自钩子，见下）。
- ``approval``：由 :data:`APPROVAL_ENV` 决定，默认 ``True``。关掉时**既不挂钩子、
  能力声明也同时变 False**——前端「有闸门」徽标据此显示，两处各写一份必然说谎。
- ``compaction=False``：本轮不配 ``CompactionConfig``，由编排层负责上下文
  （``RunContext.prompt`` 已渲染好历史）。
- ``steer=False``：SDK 只有 ``cancel``，没有插话接口（全仓 ``steer|interrupt``
  只命中 ``Conversation.cancel``）。声明 ``True`` 会让前端渲染出一个敲进去就被
  丢弃的输入框，比禁用更糟。
- ``concurrent_in_session=True``：每次 ``stream()`` 自建 Agent + 独立 Go 进程，
  没有跨请求共享的可变状态，同会话并行两轮互不干扰。

## 工具面：为什么默认 ``lite``

harness 的 MCP 客户端**只有一条通道**：把 ``call_mcp_tool`` 交给模型，或
``force_all_tools_eager=True`` 把服务端 ``tools/list`` 的全部工具注册成
``mcp_<server>_<tool>`` 原生工具。后者在 ``full`` 档是 424 个工具 / 244KB /
8.3 万 token **每轮**——四个后端里最贵的一份 prefill。

所以：

- 默认请求头 ``x-fachuan-tool-tier: lite``（61 个直连工具 / 33KB / 1.1 万 token，
  与 dsh 默认一致，见 ``toolface/constants.py``），模型拿到的是**带 schema 的原生
  工具**（``force_all_tools_eager=True``）；
- ``FACHUAN_ANTIGRAVITY_TOOL_TIER=full`` 可放开到全量（代价就是上面那 8.3 万 token）；
- ``delete_case`` 这类「不可逆且不该由模型自主发起」的工具在**工具面**上就摘掉
  （``McpStreamableHttpServer.disabled_tools``），不靠审批兜底——审批拦的是模型
  **已经决定**要调的动作，而这类工具连审批卡都不该弹。
- ``asked`` 的惰性通道（``call_mcp_tool``）只在 ``lite`` 都没配好时才会出现：
  那时模型必须先用 ``view_file`` 读 ``<appDataDir>/brain/<conv>/mcp/<server>/<tool>.json``
  才知道参数，而 ``view_file`` 在本后端是关闭的（无文件工具面）。**因此不允许
  降级成惰性通道**：``force_all_tools_eager`` 恒为 True。

## 事件来源（踩过的坑，别改回去）

- 正文 / 思考：``resp.chunks`` 的 ``Text`` / ``Thought``（``str`` 增量）；
- 工具：**钩子**，不是 ``resp.chunks``。实测本地 harness 路径下 ``chunks`` 只吐
  ``Text``，工具事件要么在钩子里拿（``PreToolCallDecideHook`` /
  ``PostToolCallHook``），要么干脆没有。而且钩子给的 ``ToolCall.id`` 与
  ``chunks`` 里 ``ToolCall.id`` **不是同一个值**（前者是 wire 的 ``call_id``，
  后者是 harness 的 step id）——两处各取一半会让 ``tool_call`` 与 ``tool_result``
  在审计库里对不上。所以两个事件都从钩子出，``id`` 同源。
- ``usage``：``resp.usage_metadata``（一轮一段，不是快照流）。

## 收尾：本后端**不发** ``done``

``done`` 由编排层铸造且单栏只允许一条（``services/chat/stream.py`` 的
``if follow_ok: yield done``）。后端再发一条会让单栏路径出现两条 ``done``
（``openai_agents_backend`` 的既有 bug，见 ``test_backend_extensibility`` 的断言）。
本后端与 ``pi_backend`` 同口径：只交出 ``result_for(run_id)`` 的收尾事实，
由编排层发 ``done``。

## 错误分类

SDK 除 ``AntigravityCancelledError`` 外没有类型化错误（HTTP 错误被包成
``AntigravityConnectionError`` + 文本），因此与 pi 同策：先按类型（取消 → 原样
上抛；连接类 → ``UNAVAILABLE``），再按 401/403、429、context 关键词分类。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from asgiref.sync import sync_to_async
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError
from google.antigravity import Agent, LocalOpenAIAgentConfig, types
from google.antigravity.hooks import hooks as hook_types

from .antigravity_gateway import get_loopback_gateway
from .base import BackendCapabilities, BackendError, BackendErrorKind, RunContext, StreamFrame
from .dsh_config import without_proxy_env
from .gateway_cache import get_gateway_settings, resolve_gateway_target
from .toolface import (
    SERVER_NAME,
    SESSION_HEADER,
    TIER_FULL,
    TIER_LITE,
    TOOL_TIER_HEADER,
    TOOL_TIMEOUT_SECONDS,
    endpoint_from_env,
    port_open,
    shared_enabled,
    tool_prefix,
)

logger = logging.getLogger(__name__)

#: 等 harness 下一个事件的单次上限（秒）。超时就 ``yield None`` 让出一个 tick——
#: 编排层只在后端 yield 时排空事件总线，而审批卡正是从那条总线来的；不让出就
#: 表现为「工具在等审批、前端的卡永远不出现」。与 pi / openai-agents 同值。
TICK_TIMEOUT_SECONDS = 0.2

#: 明确危险、**不交给模型**的 MCP 工具（原始名，不带 ``mcp__fachuan__`` 前缀）。
#: 与 ``openai_agents_backend.BLOCKED_TOOL_NAMES`` 同口径：只摘「不可逆且不该由
#: 模型自主发起」的动作，不做能力收窄。
BLOCKED_TOOL_NAMES: tuple[str, ...] = ("delete_case",)

#: 审批闸门开关。默认 on；``off`` / ``0`` / ``false`` / ``no`` 时既不挂钩子、
#: 能力声明里的 ``approval`` 也同时为 False（与 ``openai_agents_backend`` 同构）。
APPROVAL_ENV = "FACHUAN_ANTIGRAVITY_APPROVAL"

#: 工具面档位（``lite`` / ``full``），默认 ``lite``。取值语义见 ``toolface/constants.py``。
TOOL_TIER_ENV = "FACHUAN_ANTIGRAVITY_TOOL_TIER"

#: 同时在跑的 antigravity 进程数上限。每轮一个 Go 进程（118MB RSS），与
#: ``budget`` 的执行位默认值（4）同口径；超出排队而不是拒绝。
MAX_RUNS_ENV = "FACHUAN_ANTIGRAVITY_MAX_RUNS"
DEFAULT_MAX_RUNS = 4

#: 拒绝后喂回模型的文案。与 openai-agents 同一句话：律师拒绝是可以谈的，
#: 写明「改用只读方案」模型才会接着干活，而不是直接终止本轮。
APPROVAL_REJECTED_MESSAGE = "用户拒绝了该操作，请改用只读方案或提出替代方案。"

#: 惰性 MCP 通道的工具名（``call_mcp_tool``）。只在 ``force_all_tools_eager``
#: 失效时才会出现，这里仍做解包，保证审批判定用真实工具名而不是这个壳。
LAZY_MCP_TOOL = "call_mcp_tool"

#: ``done`` 里不编造上下文水位：SDK 的 ``UsageMetadata`` 只有 token 计数，
#: 没有模型窗口大小（与 ``dsh_backend`` / ``openai_agents_backend`` 同口径）。
_CONTEXT_UNKNOWN: int | None = None


@dataclass(frozen=True)
class AntigravityRunResult:
    """一轮跑完后交回编排层的事实（与 ``PiRunResult`` / ``DshRunResult`` 同构）。"""

    model: str | None
    context_used: int | None = None
    context_total: int | None = None


@dataclass(frozen=True)
class ResolvedTarget:
    """本轮真正要用的网关目标（解析结果，供构造 harness 配置与日志使用）。"""

    base_url: str
    api_key: str
    model: str
    #: 本轮要注入请求体的思考字段（空 = 该模型/平台不开思考）。
    #: harness 自己不发这些字段，只能由 loopback 代理补（见 ``antigravity_gateway``）。
    thinking: dict[str, Any]


# ── 开关与能力声明 ────────────────────────────────────────────────────────


def approval_enabled() -> bool:
    """审批闸门是否启用（默认启用，解析口径与 ``toolface.shared_enabled`` 一致）。"""
    raw = os.environ.get(APPROVAL_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def tool_tier() -> str:
    """本轮请求头里的工具面档位（``lite`` / ``full``）。非法值一律回落 ``lite``。"""
    raw = os.environ.get(TOOL_TIER_ENV, TIER_LITE).strip().lower()
    return TIER_FULL if raw == TIER_FULL else TIER_LITE


def max_runs() -> int:
    """并发上限（>=1）；解析失败回落 :data:`DEFAULT_MAX_RUNS` 并记一条 warning。"""
    raw = os.environ.get(MAX_RUNS_ENV, "").strip()
    if not raw:
        return DEFAULT_MAX_RUNS
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r 无法解析，使用默认 %s", MAX_RUNS_ENV, raw, DEFAULT_MAX_RUNS)
        return DEFAULT_MAX_RUNS
    return max(1, value)


def backend_capabilities() -> BackendCapabilities:
    """本轮实例的能力声明（``approval`` 与开关同源，其余是静态事实）。"""
    return BackendCapabilities(
        streaming=True,
        tool_calls=True,
        approval=approval_enabled(),
        compaction=False,
        steer=False,
        concurrent_in_session=True,
    )


def thinking_extra(settings: Any, model: str) -> dict[str, Any]:
    """本轮该注入网关的思考字段；不该开思考时返回空 dict。

    ## 为什么必须在这里补（而不是指望 SDK）

    harness 的 OpenAI 兼容通道**不发任何思考参数**（实测请求体只有
    ``max_completion_tokens / messages / model / stream / stream_options /
    tool_choice / tools``）。而网关（LiteLLM → vLLM）要两个字段才开思考：

    - ``chat_template_kwargs.thinking``（布尔）；
    - ``reasoning_effort``（字符串，服务端白名单 ``low|high|xhigh|max``）。

    不补的症状是**静默的**：不报错、回答照出，只是明显变浅、
    ``thoughts_token_count`` 恒 0——用户只会觉得「换个 agent 回答差一截」。
    这也正是 pi / dsh / openai-agents 三个后端都各自补过一遍的同一件事。

    ## 口径与其它后端严格同源

    - 开关取 ``LLMProvider.enable_thinking``（平台级，Admin 里可关）；
    - 模型能力取 :func:`gateway_cache.model_supports_thinking`（与 ``pi.model_config``
      同一张特征表）；
    - 档位取 ``pi.model_config`` 的 ``DEFAULT_THINKING_LEVEL`` 并经
      :func:`gateway_effort` 归一（原样发 ``medium`` 会被网关 400）。

    Returns:
        ``{"reasoning_effort": ..., "chat_template_kwargs": {"thinking": True}}``；
        平台未开或模型不是推理模型时返回 ``{}``（**不注入任何字段**——给非推理模型
        发思考参数会被网关 400）。
    """
    from ..pi.model_config import DEFAULT_THINKING_LEVEL, gateway_effort
    from .gateway_cache import model_supports_thinking

    if settings is None or not getattr(settings, "enable_thinking", False):
        return {}
    if not model_supports_thinking(model):
        return {}
    effort = gateway_effort(DEFAULT_THINKING_LEVEL)
    extra: dict[str, Any] = {"chat_template_kwargs": {"thinking": True}}
    if effort:
        extra["reasoning_effort"] = effort
    return extra


# ── 运行目录 ──────────────────────────────────────────────────────────────


def agent_home() -> Path:
    """antigravity 的稳定目录（``FACHUAN_AGENT_HOME`` 下的 ``antigravity/``）。

    为什么必须显式指定：SDK 默认的 ``app_data_dir`` 是 ``~/.gemini/antigravity``，
    ``save_dir`` 为空时还会在 ``/tmp`` 建一个临时目录（``_get_or_create_save_dir``）。
    前者把运行时状态写进用户主目录（多 worker 不共享、清理时找不到），后者每次
    运行泄漏一个目录。与 pi 的会话目录同策：集中在 ``FACHUAN_AGENT_HOME`` 下，
    多 worker 部署共享同一份。
    """
    raw = os.environ.get("FACHUAN_AGENT_HOME", "").strip()
    base = Path(raw).expanduser() if raw else Path.home() / ".fachuan-agent"
    return base / "antigravity"


def _ensure_dir(path: Path) -> Path:
    """建目录（0700）。会话/工具 schema 里可能有案件内容，不给同机其他用户读。"""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


# ── 工具名与参数解包 ──────────────────────────────────────────────────────


def _as_text(value: Any) -> str:
    """把工具名 / 结果这类 ``BuiltinTools | str | None`` 统一成字符串。"""
    return "" if value is None else str(value)


def tool_identity(name: Any, server_name: str | None, args: dict[str, Any] | None) -> tuple[str, dict[str, Any], str]:
    """把一次工具调用拆成 ``(短名, 真实入参, 审批用的全名)``。

    ## 为什么要剥一层

    ``force_all_tools_eager`` 生效时钩子拿到的是**已解包**的真实工具
    （实测：模型调 ``mcp_pirate_math_pirate_multiply`` → 钩子里
    ``name='pirate_multiply'``、``server_name='pirate_math'``）。但 harness 也可能
    退回惰性通道 ``call_mcp_tool``，那种情况下真实工具名藏在
    ``args["ToolName"]`` / 入参在 ``args["Arguments"]`` —— 不解包的话：

    - 审批分级只看得到 ``call_mcp_tool``（永远判「低危」）→ **闸门静默失效**；
    - 前端工具链只显示一个壳子，律师看不到「查了哪个案件」。

    解包失败（字段缺失/类型不对）时退回原样：宁可让审批按壳名判低危再由 MCP
    服务端的闸门兜底，也不要把一次正常调用判成错误。

    Returns:
        短名（进 ``tool_call`` / ``tool_result`` 事件与审批卡）、真实入参、
        审批用的全名（``mcp__fachuan__<短名>``，与 pi / dsh 的匹配口径一致）。
    """
    raw_name = _as_text(name)
    raw_args = dict(args or {})
    if raw_name != LAZY_MCP_TOOL:
        short = raw_name
        full = f"{tool_prefix(server_name or SERVER_NAME)}{short}" if short else short
        return short, raw_args, full

    inner_name = _as_text(raw_args.get("ToolName"))
    inner_args = raw_args.get("Arguments")
    inner_server = _as_text(raw_args.get("ServerName")) or (server_name or SERVER_NAME)
    if not inner_name:
        return raw_name, raw_args, f"{tool_prefix(inner_server)}{raw_name}"
    parsed = inner_args if isinstance(inner_args, dict) else {}
    return inner_name, dict(parsed), f"{tool_prefix(inner_server)}{inner_name}"


def _result_text(value: Any) -> str | None:
    """把工具结果转成事件里的 ``result``（``ToolResultEvent.result`` 是 ``str|None``）。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):  # pragma: no cover - 极端兜底
        return str(value)


# ── 事件出口 ──────────────────────────────────────────────────────────────


class _EventSink:
    """钩子 → 事件流的有界队列。

    钩子是 SDK 在同一事件循环里回调的，主循环在读 ``resp.chunks``；两边靠这个
    队列汇合（钩子只 ``put_nowait``，绝不阻塞——阻塞会把 harness 的工具执行卡住）。

    ``maxsize`` 与编排层共用一个数量级（``multi.py`` 的 256）：工具密集的一轮
    可能瞬间刷出几十条 ``tool_call``/``tool_result``，无界队列在「前端很慢 +
    模型狂调工具」时会吃内存；满了就丢**最旧的**并记 warning——丢的是可展示的
    证据链，不是正文与审批。
    """

    MAXSIZE = 256

    def __init__(self, ctx: RunContext, kind: str) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self.MAXSIZE)
        self._ctx = ctx
        self._kind = kind
        self._dropped = 0

    def push(self, frame: dict[str, Any]) -> None:
        """带信封地入队（``agent`` / ``run_id`` 由这里统一补，钩子里不用重复写）。"""
        tagged = {**frame, "agent": self._kind, "run_id": self._ctx.run_id}
        try:
            self.queue.put_nowait(tagged)
        except asyncio.QueueFull:
            self._dropped += 1
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
                self.queue.put_nowait(tagged)
            if self._dropped == 1 or self._dropped % 50 == 0:
                logger.warning(
                    "antigravity 事件队列满（已丢 %d 条，队列上限 %d）：run=%s",
                    self._dropped,
                    self.MAXSIZE,
                    self._ctx.run_id,
                )

    def drain_nowait(self) -> list[dict[str, Any]]:
        """取走当前所有已入队的事件（不阻塞）。"""
        frames: list[dict[str, Any]] = []
        while True:
            try:
                frames.append(self.queue.get_nowait())
            except asyncio.QueueEmpty:
                return frames


# ── 钩子 ──────────────────────────────────────────────────────────────────


class _ToolDecideHook(hook_types.PreToolCallDecideHook):
    """工具执行前的两道事：发 ``tool_call`` 事件 + 人工审批闸门。"""

    def __init__(self, sink: _EventSink, ctx: RunContext) -> None:
        self._sink = sink
        self._ctx = ctx
        #: 被拒的 ``tool_call_id``。SDK 对「策略拒绝」可能仍回调 ``PostToolCallHook``，
        #: 不记账就会发出**两条** ``tool_result``（一条我们的拒绝文案、一条 SDK 的），
        #: 前端会出现两个结果气泡、审计库里同一调用记两次。
        self.denied: set[str] = set()

    async def run(self, context: hook_types.HookContext, data: types.ToolCall) -> types.HookResult:
        """判定并（必要时）等律师确认；拒绝时返回 ``allow=False``。"""
        short_name, tool_args, full_name = tool_identity(data.name, data.server_name, data.args)
        call_id = _as_text(data.id)
        self._sink.push(
            {
                "type": "tool_call",
                "tool_call_id": call_id,
                "name": short_name,
                "arguments": json.dumps(tool_args, ensure_ascii=False) if tool_args else None,
            }
        )
        if not approval_enabled():
            return types.HookResult(allow=True)

        # 函数内 import：``backends`` 在 AppConfig 阶段被导入，而 ``services.approval``
        # 要初始化 Django 模型层与事件总线，模块级 import 会把两边串成启动期环
        # （同 ``openai_agents_backend._approval_guardrail`` 的处理）。
        from ..services.approval import RiskLevel, classify_risk, request_approval

        if classify_risk(full_name, tool_args) not in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return types.HookResult(allow=True)

        approved, _approval_id, _reason = await request_approval(
            tool_name=full_name,
            tool_args=tool_args,
            user_id=self._ctx.user_id,
            session_id=str(self._ctx.session.session_id),
            run_id=self._ctx.run_id,
        )
        if approved:
            return types.HookResult(allow=True)

        self.denied.add(call_id)
        self._sink.push(
            {
                "type": "tool_result",
                "tool_call_id": call_id,
                "name": short_name,
                "result": APPROVAL_REJECTED_MESSAGE,
                "is_error": True,
            }
        )
        # 用 ``allow=False + message`` 而不是抛异常：抛异常会被 harness 包成工具
        # 故障（前端标红、看板记成错误），而这里要的是「工具不执行、本轮继续」。
        return types.HookResult(allow=False, message=APPROVAL_REJECTED_MESSAGE)


class _ToolResultHook(hook_types.PostToolCallHook):
    """工具执行完发 ``tool_result``（带上 ``is_error``）。"""

    def __init__(self, sink: _EventSink, decide: _ToolDecideHook) -> None:
        self._sink = sink
        self._decide = decide

    async def run(self, context: hook_types.HookContext, data: types.ToolResult) -> None:
        """翻译成 ``tool_result``；被审批拒掉的调用不重复发。"""
        call_id = _as_text(data.id)
        if call_id and call_id in self._decide.denied:
            self._decide.denied.discard(call_id)
            return
        short_name, _args, _full = tool_identity(data.name, data.server_name, None)
        error = _as_text(data.error) or None
        self._sink.push(
            {
                "type": "tool_result",
                "tool_call_id": call_id,
                "name": short_name,
                "result": error or _result_text(data.result),
                "is_error": bool(error),
            }
        )


# ── 并发执行位 ────────────────────────────────────────────────────────────


class _RunSlots:
    """并发闸门：同时在跑的 antigravity 进程数上限（超出排队，不拒绝）。

    ## 为什么要自己数

    pi 有进程池（``pi/pool.py``）负责排队与占位，本后端**没有池**——每轮一个
    一次性 Go 进程。缺了闸门，四位律师同时提问就是四个 118MB 进程 + 四份
    244KB 工具面，机器先倒。用 ``asyncio.Semaphore`` 而不是队列：``acquire``
    的等待语义与"排队"一致，且不需要额外的任务管理。

    ``_waiting`` 只用于发 ``activity: queued`` 的位次播报（前端显示「排队中」），
    不做调度——真正的先来先到由 ``Semaphore`` 的 FIFO 保证。
    """

    def __init__(self) -> None:
        self._sem: asyncio.Semaphore | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._waiting = 0
        self._limit = 0

    def _ensure(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        limit = max_runs()
        if self._sem is None or self._loop is not loop or self._limit != limit:
            # 换事件循环（pytest 每例一个新循环）或改了上限都要重建：把旧循环上的
            # Semaphore 拿到新循环里 await，Python 3.12 会直接抛
            # "is bound to a different event loop"。
            self._sem = asyncio.Semaphore(limit)
            self._loop = loop
            self._limit = limit
        return self._sem

    async def acquire(self) -> tuple[bool, int]:
        """占一个执行位；返回 ``(是否等了, 排队位次)``（位次 1 = 队首）。"""
        sem = self._ensure()
        position = self._waiting + 1
        waited = sem.locked()
        self._waiting += 1
        try:
            await sem.acquire()
        finally:
            self._waiting -= 1
        return waited, position

    def release(self) -> None:
        """归还执行位（``acquire`` 成功后必须调用）。"""
        if self._sem is not None:
            self._sem.release()


_slots = _RunSlots()


# ── 后端 ──────────────────────────────────────────────────────────────────


class AntigravityBackend:
    """antigravity 运行时（每次 ``stream()`` 自建 Agent + Go 进程，跑完即关）。"""

    kind = "antigravity"

    #: 能力声明（:func:`backend_capabilities`）。实例属性而不是类属性：
    #: ``approval`` 与 ``APPROVAL_ENV`` 同源，类属性只能在 import 时取一次值。
    capabilities: BackendCapabilities

    #: 按 ``run_id`` 归集的收尾事实。键控而不是单值——注册表里存的是单例，而
    #: ``stream()`` 并发（``concurrent_in_session=True``），实例属性会让两栏互相
    #: 覆盖对方的结果（pi / openai-agents 同因同解）。
    _results: dict[str, AntigravityRunResult]

    def __init__(self) -> None:
        self.capabilities = backend_capabilities()
        self._results = {}

    def result_for(self, run_id: str) -> AntigravityRunResult | None:
        """取某一轮的收尾事实；未跑过 / 本轮异常时为 ``None``。"""
        return self._results.get(run_id)

    def stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        """跑一轮，产出一轮全部 SSE 事件（``agent`` / ``run_id`` 已补齐）。

        Raises:
            BackendError: 网关不可用 / harness 异常，均在边界处转换。
                ``asyncio.CancelledError`` / ``GeneratorExit`` 原样上抛——用户按
                停止不是错误，包成 ``BackendError`` 会让 ``AgentRun`` 把取消记成失败。
        """
        return self._stream(ctx)

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        try:
            target = await self._resolve_target(ctx)
            async for frame in self._run(ctx, target):
                yield frame
        except (BackendError, asyncio.CancelledError, GeneratorExit):
            raise
        except ANTIGRAVITY_FAILURES as exc:
            # 边界处统一转 BackendError（见 base.py 契约）。**只接 SDK 自家异常 +
            # 传输层 + RuntimeError/ValueError**，不接宽异常：真正的程序 bug 应当
            # 带着堆栈冒到编排层的兜底 except（那里会记 error_kind=unexpected 并投影
            # 人话），把它一并压成「后端错误」会让 bug 看起来像上游抖动。
            logger.warning("antigravity 本轮失败 run=%s", ctx.run_id, exc_info=True)
            raise self._wrap_error(exc) from exc

    async def _resolve_target(self, ctx: RunContext) -> ResolvedTarget:
        """解析本轮的网关目标；不可用时报可读错误（``UNAVAILABLE``）。

        读库走 ``sync_to_async``：``get_gateway_settings`` 未命中缓存时是同步 ORM，
        直接在事件循环里调会抛 ``SynchronousOnlyOperation``——那个异常会被兜底
        ``except`` 吞成「未知错误」，排查方向完全被带偏（``agent-runtime.md`` 记过）。
        """
        try:
            settings = await sync_to_async(get_gateway_settings, thread_sensitive=True)(ctx.model)
        except (DatabaseError, ImproperlyConfigured, RuntimeError) as exc:
            # 与 ``gateway_cache.load_api_keys`` 同一组类型：读库失败 / Django 未就绪 /
            # 线程切换失败，都是「本进程此刻拿不到平台配置」，不是编程错误。
            raise BackendError.wrap(exc, BackendErrorKind.UNAVAILABLE) from exc
        resolved = resolve_gateway_target(settings, ctx.model, api_key=ctx.api_key)
        if resolved is None:
            raise BackendError(
                BackendErrorKind.UNAVAILABLE,
                "未配置可用的 AI 平台（base_url / api_key / 模型），antigravity 无法启动；请联系管理员",
            )
        return ResolvedTarget(
            base_url=resolved.base_url,
            api_key=resolved.api_key,
            model=resolved.model,
            thinking=thinking_extra(settings, resolved.model),
        )

    async def _run(self, ctx: RunContext, target: ResolvedTarget) -> AsyncGenerator[StreamFrame, None]:
        """占执行位 → 起 harness → 合并「增量 + 钩子事件」→ 发 usage。"""
        waited, position = await _slots.acquire()
        try:
            if waited:
                # 排队播报必须在真正启动之前发：之后这条协程就卡在 harness 启动上，
                # 前端会长时间空白（pi_backend 同一处理）。
                yield {
                    "type": "activity",
                    "status": "queued",
                    "position": position,
                    "agent": self.kind,
                    "run_id": ctx.run_id,
                }
            async for frame in self._drive(ctx, target):
                yield frame
        finally:
            _slots.release()

    async def _drive(self, ctx: RunContext, target: ResolvedTarget) -> AsyncGenerator[StreamFrame, None]:
        """真正与 SDK 打交道的那一段（所有退出路径都要注销代理路由）。"""
        gateway = get_loopback_gateway()
        lease = await gateway.register(base_url=target.base_url, api_key=target.api_key, extra_body=target.thinking)
        sink = _EventSink(ctx, self.kind)
        decide = _ToolDecideHook(sink, ctx)
        result_hook = _ToolResultHook(sink, decide)
        chat_task: asyncio.Task[Any] | None = None
        agent: Agent | None = None
        try:
            config = self._build_config(
                ctx, target, lease.base_url, hooks=[decide, result_hook], mcp_servers=self._mcp_servers(ctx)
            )
            # 代理剔除只覆盖「起进程 + 建 WS 连接」这一段：websockets 会读
            # ``ALL_PROXY``/``HTTPS_PROXY`` 并把连 127.0.0.1 的 WS 也发去 SOCKS 代理
            # （实测报 "connecting through a SOCKS proxy requires python-socks"）。
            # 窗口越大越危险（``without_proxy_env`` 改的是进程全局环境）。
            with without_proxy_env():
                agent = Agent(config)
                await agent.__aenter__()
            chat_task = asyncio.create_task(self._chat(agent, ctx.prompt, sink), name=f"antigravity:{ctx.run_id}")
            async for frame in self._merge(chat_task, sink):
                yield frame
            usage = await self._collect_usage(chat_task)
            if usage is not None:
                yield {**usage, "agent": self.kind, "run_id": ctx.run_id}
            self._results[ctx.run_id] = AntigravityRunResult(model=target.model)
        finally:
            if chat_task is not None and not chat_task.done():
                # 客户端断开 / 取消：让 harness 停下来，否则它会继续跑模型循环
                # （烧 token 且占着 118MB 进程）。不 await——取消路径上等它收尾
                # 只会让「停止」按钮变慢。
                chat_task.cancel()
            if agent is not None:
                # ``__aexit__`` 负责关进程与 WS。取消时也要走，否则 118MB 进程泄漏。
                with contextlib.suppress(Exception):
                    await agent.__aexit__(None, None, None)
            gateway.unregister(lease.token)

    def _build_config(
        self,
        ctx: RunContext,
        target: ResolvedTarget,
        loopback_base_url: str,
        *,
        hooks: list[Any],
        mcp_servers: list[types.McpServerConfig],
    ) -> LocalOpenAIAgentConfig:
        """组装 harness 配置（工具面、系统提示、目录、环境）。

        ## 系统提示必须**全量替换**

        传 ``str`` 只会「追加一节」，Antigravity 自己的身份（``<identity> You are
        Antigravity, ... designed by the Google DeepMind team``）仍在最前面——律师会
        得到一个自称程序员的助手，且会试图读文件、跑命令。``CustomSystemInstructions``
        是唯一的全量替换入口，代价是 MCP 工具清单**也不再自动注入**（那本就是
        ``force_all_tools_eager`` 下由原生工具 schema 承担的事，不需要提示词复述）。

        ## 工具面

        - ``enabled_tools=[]``：内置工具一个都不给（无文件读写、无 shell、无子 agent、
          无联网——法务对话不需要，全是额外的越权面）；
        - ``enable_subagents=False``；
        - MCP 只挂 ``fachuan``，``force_all_tools_eager=True``（理由见模块 docstring），
          ``disabled_tools=BLOCKED_TOOL_NAMES``；
        - ``workspaces`` 指向 ``FACHUAN_AGENT_HOME`` 下的空目录：文件工具已关，
          这里只是不让 harness 把 cwd（仓库根）当工作区。
        """
        home = agent_home()
        return LocalOpenAIAgentConfig(
            model=target.model,
            base_url=loopback_base_url,
            system_instructions=types.CustomSystemInstructions(text=_instructions(ctx)),
            capabilities=types.CapabilitiesConfig(
                enabled_tools=[],  # 内置工具一个都不给（见 docstring）
                enable_subagents=False,
            ),
            # 空白策略列表：审批由本模块的 decide 钩子负责。SDK 默认的
            # ``confirm_run_command`` 只认识内置 ``run_command``，对 MCP 工具无效，
            # 留着只会让「看起来有闸门」这件事变成错觉。
            policies=[],
            hooks=hooks,
            mcp_servers=mcp_servers,
            workspaces=[str(_ensure_dir(home / "workspace"))],
            app_data_dir=str(_ensure_dir(home)),
            save_dir=str(_ensure_dir(home / "store")),
            # harness 自己也要访问 127.0.0.1（loopback 代理 + 共享 MCP）：把内网/
            # 环回地址从代理里摘出去，否则本机 Clash 会把它们也代理走（502）。
            env={"NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"},
        )

    async def _chat(self, agent: Agent, prompt: str, sink: _EventSink) -> Any:
        """跑一轮并把 ``Text`` / ``Thought`` 增量推进队列；返回 ``ChatResponse``。

        正文走队列而不是直接 yield：主循环同时在等「增量」和「钩子事件」两条来源，
        直接 yield 需要两套游标，而 ``ChatResponse`` 的游标只能有一个消费者在跑。
        """
        response = await agent.chat(prompt)
        async for chunk in response.chunks:
            frames = self._translate_chunk(chunk)
            for frame in frames:
                sink.push(frame)
        return response

    @staticmethod
    def _mcp_servers(ctx: RunContext) -> list[types.McpServerConfig]:
        """本轮的 MCP 工具面；拿不到就**降级为「无工具但能对话」**。

        三种「不接工具」的情况都记 warning 而不是抛错（与 ``dsh_mcp`` /
        ``openai_agents_backend._mcp_target`` 同策）——工具面缺失是用户可感知的
        能力变化，不能静默；但「本来能对话」也不该变成「整轮失败」：

        1. 没有律师 token：:8011 强制每请求 Bearer 且**刻意不回退服务账号**
           （越权修复），硬连只会 401；
        2. 共享 MCP 被显式关掉（``FACHUAN_MCP_SHARED=0``）；
        3. 端口不通（服务还没起来 / 崩了）。**不在这里拉起**：冷启动实测约 6s，
           会卡住整个事件循环，而下一轮自然会由 pi/dsh 的 acquire 路径自愈拉起。
        """
        token = (ctx.user_token or "").strip()
        if not token:
            logger.warning("antigravity 本轮没有律师 token，无法接入法穿 MCP 工具（无工具但可对话）")
            return []
        if not shared_enabled():
            logger.warning("共享 MCP 已禁用（FACHUAN_MCP_SHARED=0），antigravity 本轮无业务工具")
            return []
        endpoint = endpoint_from_env()
        if not port_open(endpoint.host, endpoint.port):
            logger.warning("共享 MCP %s 不可连，antigravity 本轮无业务工具", endpoint.url)
            return []
        return [
            types.McpStreamableHttpServer(
                name=SERVER_NAME,
                url=endpoint.url,
                headers={
                    # 会话标识：MCP 服务端的审批闸门靠它把审批卡投到正确会话；不带会
                    # 建「无会话单」，只有超管能批，等于高危工具全拒（与 pi/dsh 同源）。
                    SESSION_HEADER: str(ctx.session.session_id),
                    # token 只进 header，**绝不进日志**（它是律师本人的业务读权限凭据）。
                    "Authorization": f"Bearer {token}",
                    TOOL_TIER_HEADER: tool_tier(),
                },
                timeout=TOOL_TIMEOUT_SECONDS,
                sse_read_timeout=TOOL_TIMEOUT_SECONDS,
                # 恒为 True：惰性通道要 ``view_file`` 读 schema 文件，而本后端没有
                # 文件工具面（见模块 docstring「工具面」）。
                force_all_tools_eager=True,
                disabled_tools=list(BLOCKED_TOOL_NAMES),
            )
        ]

    @staticmethod
    def _translate_chunk(chunk: Any) -> list[dict[str, Any]]:
        """``Text`` → ``delta``；``Thought`` → ``thinking``；其余丢掉。

        **不翻译 ``ToolCall`` / ``ToolResult``**：本地 harness 路径下 ``chunks``
        只吐文本（实测），工具事件统一从钩子来，且两处的 ``id`` 不是同一个值
        （见模块 docstring「事件来源」）。
        """
        if isinstance(chunk, types.Text):
            text = chunk.text or ""
            return [{"type": "delta", "content": text}] if text else []
        if isinstance(chunk, types.Thought):
            text = chunk.text or ""
            return [{"type": "thinking", "content": text}] if text else []
        return []

    async def _merge(self, chat_task: asyncio.Task[Any], sink: _EventSink) -> AsyncGenerator[StreamFrame, None]:
        """把「钩子队列」与「chat 任务完成」合流成本轮事件序列。

        每个 tick：先排空队列，再看 chat 是否结束；都没动静就 ``yield None`` 让出
        一帧（编排层借这个间隙把审批事件从外部总线推进来）。与 ``pi_backend`` /
        ``openai_agents_backend`` 的 tick 口径一致。
        """
        getter: asyncio.Task[dict[str, Any]] | None = None
        try:
            while True:
                for frame in sink.drain_nowait():
                    yield frame
                if chat_task.done():
                    # 结束时可能还有一批事件没取（钩子在最后一步才 push）：先取完
                    # 再抛异常/收尾，否则最后一条 tool_result 会丢。
                    for frame in sink.drain_nowait():
                        yield frame
                    break
                if getter is None:
                    getter = asyncio.ensure_future(sink.queue.get())
                done, _pending = await asyncio.wait({getter}, timeout=TICK_TIMEOUT_SECONDS)
                if not done:
                    yield None
                    continue
                frame = getter.result()
                getter = None
                yield frame
        finally:
            if getter is not None:
                # 提前退出（取消 / 异常）时挂着的 ``queue.get()`` 必须收掉，
                # 否则任务泄漏并在事件循环关闭时刷 "Task was destroyed"。
                getter.cancel()

    @staticmethod
    async def _collect_usage(chat_task: asyncio.Task[Any]) -> dict[str, Any] | None:
        """从 chat 任务的返回值取 token 用量；异常照原样抛给上层分类。"""
        response = await chat_task
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return None
        return _usage_frame(usage)

    @staticmethod
    def _wrap_error(exc: BaseException) -> BackendError:
        """把 SDK / 网关异常转成 ``BackendError``（分类口径与 pi/dsh 一致）。

        先按**类型**：取消类原样（调用方已在 ``_stream`` 里挡掉，这里兜一层防御）、
        ``AntigravityConnectionError`` 与 ``OSError`` 系列 → ``UNAVAILABLE``（可重试）。
        SDK 把 HTTP 4xx/5xx 也包成 ``AntigravityConnectionError`` + 文本，所以再按
        关键词补 401/403、429、context 三类——这是**有损**的分类，但比一律「未知
        错误」好：至少限流不会被提示成「请稍后重试」以外的错。

        Raises:
            不会。所有异常都被包成 ``BackendError``。
        """
        if isinstance(exc, BackendError):
            return exc
        if isinstance(exc, (asyncio.CancelledError, GeneratorExit)):
            raise exc  # pragma: no cover - 契约要求原样上抛，不转错误

        kind = BACKEND_ERROR_TYPE_MAP.get(type(exc).__name__)
        if kind is not None:
            return BackendError.wrap(exc, kind, retryable=kind is BackendErrorKind.UNAVAILABLE)
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return BackendError.wrap(exc, BackendErrorKind.UNAVAILABLE, retryable=True)

        text = (str(exc) or exc.__class__.__name__).lower()
        if "api key" in text or "401" in text or "403" in text or "unauthorized" in text or "permission" in text:
            return BackendError.wrap(exc, BackendErrorKind.AUTH)
        if "429" in text or "rate limit" in text or "retry-after" in text:
            return BackendError.wrap(exc, BackendErrorKind.RATE_LIMITED, retryable=True)
        if "context" in text and ("window" in text or "length" in text or "overflow" in text):
            return BackendError.wrap(exc, BackendErrorKind.CONTEXT_OVERFLOW)
        return BackendError.wrap(exc, BackendErrorKind.UNKNOWN)


#: 需要在边界处翻译成 ``BackendError`` 的异常集合。
#:
#: 枚举而不是宽 except 基类（本仓库的宽异常棘轮按行正则扫源码，注释里写字面量也会被
#: 计入，所以这里只描述不照抄，见
#: ``devtools/security_guard.py --check broad-except``）：SDK 的异常是**平铺**的
#: （没有公共基类），所以逐个列出；再加传输层与 ``RuntimeError``/``ValueError``
#: ——harness 进程崩溃、subprocess 传参错误都落在后两类。**取消类不在这里**：
#: ``AntigravityCancelledError`` 继承 ``CancelledError``（``BaseException``），
#: 必须先被上面的 ``except`` 原样上抛。
ANTIGRAVITY_FAILURES: tuple[type[BaseException], ...] = (
    types.AntigravityConnectionError,
    types.AntigravityExecutionError,
    types.AntigravityValidationError,
    types.ToolExecutionError,
    OSError,
    RuntimeError,
    ValueError,
)

#: SDK 异常类名 → 错误分类。
#:
#: 用**类名字符串**而不是 import 类对象：0.1.x 是 alpha，模块路径与类名都在漂
#: （``AntigravityCancelledError`` 是从 ``types`` 导出的），绑类对象会让「SDK 升级
#: 改了导出位置」变成整个后端 import 失败。类名足够稳定，且取不到时只是退回关键词分类。
BACKEND_ERROR_TYPE_MAP: dict[str, BackendErrorKind] = {
    "AntigravityConnectionError": BackendErrorKind.UNAVAILABLE,
    "AntigravityValidationError": BackendErrorKind.UNAVAILABLE,
}


def _usage_frame(usage: Any) -> dict[str, Any]:
    """``UsageMetadata`` → ``usage`` 事件（``sse_types.UsageEvent``）。

    ## 口径（为什么这么拆）

    - ``cached_content_token_count`` 单列成 ``cache_read_tokens``：编排层把
      ``cache_read`` 与 ``input`` **分开累加**（``stream.py`` 的注释写明），把它们
      并进 input 会让「命中缓存的比例」永远看不出。
    - ``prompt_token_count`` 在 Gemini 语义里**含**缓存命中部分，所以
      ``input_tokens = prompt - cached``（下限 0，防御 SDK 给出不一致的值）；
    - ``thoughts_token_count`` 计入 ``output``：思考也是模型真的生成、真的计费的
      token，漏掉会让成本账偏低。
    """
    prompt = int(getattr(usage, "prompt_token_count", 0) or 0)
    cached = int(getattr(usage, "cached_content_token_count", 0) or 0)
    candidates = int(getattr(usage, "candidates_token_count", 0) or 0)
    thoughts = int(getattr(usage, "thoughts_token_count", 0) or 0)
    return {
        "type": "usage",
        "input_tokens": max(0, prompt - cached),
        "output_tokens": candidates + thoughts,
        "cache_read_tokens": cached,
        "cache_write_tokens": 0,
    }


def _instructions(ctx: RunContext) -> str:
    """本轮的系统提示（全量替换 Antigravity 自带身份，理由见 ``_build_config``）。

    刻意**不**注入仓库级 ``AGENTS.md`` / 技能目录：那是编码 agent 的默认行为，
    对法务场景是多余且不可控的注入面。业务上下文已由编排层渲染进 ``prompt``。
    """
    return (
        "你是「法穿」法律事务管理系统里的律师助理。"
        "统一使用简体中文回答，结论先行，引用法条时给出法律名称与条款号。"
        "涉及案件、合同、当事人、期限、金额等事实时，必须先用可用的工具查询后再回答，"
        "不要凭记忆编造；工具查不到就如实说明，并给出下一步建议。"
        "不要读写本机文件、不要执行命令——你的能力只有系统提供的业务工具。"
        f"本轮会话：{ctx.session.session_id}"
    )
