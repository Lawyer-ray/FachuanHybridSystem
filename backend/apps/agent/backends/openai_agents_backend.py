"""openai-agents 后端：把「一次 ``Runner.run_streamed`` → 翻译成 SSE 事件」接成 ``AgentBackend``。

第三个后端（pi / DeepSeek Harness 之后）。走官方 ``openai-agents`` SDK：模型经
律所网关（LiteLLM，OpenAI 兼容）走 ``OpenAIChatCompletionsModel``，业务工具经
``MCPServerStreamableHttp`` 连法穿共享 MCP（:8011，与 pi / dsh 同一个常驻进程）。

## 本模块管什么

从建立 MCP 连接开始，到本轮最后一个事件。三件事都自己造：

1. **网关配置**：base_url / api_key / 模型名**全部来自数据库 ``LLMProvider``**
   （复用 pi 的 ``model_config`` 函数，见 :func:`gateway_from_provider`）。硬编码
   模型名会让 Admin 里换模型在这一栏静默失效。
2. **事件翻译**：SDK 的 ``raw_response_event`` / ``run_item_stream_event`` →
   ``sse_types.py`` 的契约事件（见 :meth:`OpenAiAgentsBackend._translate_stream_event`），
   收尾再从 ``RunResultStreaming.raw_responses`` 累加出**一帧** ``usage``（见
   :func:`_usage_frame`）。
3. **代理剔除**：律所网关是内网地址，开发机的 ``HTTPS_PROXY`` 指向本地 Clash，
   不拿掉就会「502 no body」。复用 ``dsh_config.without_proxy_env``（同一个坑、
   同一份实现）。

**不接管**（留在编排层 ``services/chat/stream.py``）：铸造用户凭证、写
``AgentMessage`` / ``AgentRun``、事件总线订阅、错误文案翻译。边界与
``pi_backend`` / ``dsh_backend`` 完全一致，理由见 ``base.py`` 的「分工边界」。

## 能力声明是事实，不是愿望

- ``streaming=True``：真的产出 ``delta`` / ``thinking``（逐 token 的
  ``ResponseTextDeltaEvent`` 等直接翻成增量，**不是**整段补发）。
- ``tool_calls=True``：真的产出 ``tool_call`` / ``tool_result``（``tool_called`` /
  ``tool_output`` 两种 run item）。
- ``approval``：由 :data:`APPROVAL_ENV`（``FACHUAN_OPENAI_APPROVAL``）决定，默认
  ``True``。闸门接在 MCP server 的 ``tool_input_guardrails`` 上（见下节）；关掉开关
  时**既不挂 guardrail、``approval`` 也同时声明 False**——前端「有闸门」徽标据此
  显示，两处写死一份必然说谎。
- ``compaction=False``：SDK 不做上下文裁剪，由编排层负责。
- ``steer=False``：``RunResultStreaming`` 只有 ``cancel``，没有插话接口。声明
  ``True`` 会让前端渲染出一个敲进去就被丢弃的输入框，比禁用更糟。
- ``concurrent_in_session=True``：每次 ``stream()`` 自建 client / agent / MCP 连接，
  没有跨请求共享的可变状态，同会话并行两轮互不干扰。

## 多轮上下文

本轮不做服务端会话续接（不传 ``session`` / ``previous_response_id``）：
``RunContext.prompt`` 已由编排层渲染好历史（见 ``RunContext.prompt`` 的注释），
agent 本身无状态。收益是上下文只有一个来源——两套来源必然漂移。

## 人工审批闸门

高危 / 紧急工具调用在**执行前**停下来等律师确认（分级判定与审批单复用
``services/approval`` 的 ``classify_risk`` / ``request_approval``，不在本模块另写
一套阈值）。三点接线事实：

1. **用 ``tool_input_guardrails``，不用 ``require_approval``**：后者的 callable 策略
   只拿到 ``(run_context, agent, tool)``——SDK 在 ``agents/mcp/server.py`` 的
   ``_get_needs_approval_for_tool`` 里把 ``_args`` / ``_call_id`` 丢弃了。那会把
   「改金额的写」与「改备注的写」拉平，参数级判定（``SENSITIVE_ARG_MARKERS``）
   直接失效。guardrail 拿到的 ``ToolContext`` 带 ``tool_name`` 与
   ``tool_arguments``（模型发出的原始 JSON 串），才是分级要的两样东西。
2. **拒绝走 ``reject_content``，不抛异常**：抛异常会被 SDK 包成
   ``Error executing tool ...``（前端标红、看板上算工具故障），而这里要的是
   「工具不执行、本轮继续，模型换个只读方案」。
3. **``Runner.run_streamed(..., context=ctx)`` 是必要条件**：guardrail 只能经
   ``data.context.context`` 取回本轮 ``RunContext``（用户 / 会话 / run_id 三个归因
   字段都在里面），不传 context 时闸门拿不到归因信息。

## 工具面

「越多越好」是明确要求：``tool_filter`` **只排除** :data:`BLOCKED_TOOL_NAMES`
里的不可逆删除类工具，不做任何收窄。工具名取不到（未连 MCP）就整条过滤器都不传。
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
from collections.abc import AsyncGenerator, Iterable
from dataclasses import dataclass

dataclasses_replace = dataclasses.replace
from typing import Any, cast

from agents import (
    Agent,
    ModelSettings,
    OpenAIChatCompletionsModel,
    Runner,
    ToolGuardrailFunctionOutput,
    ToolInputGuardrail,
    ToolInputGuardrailData,
    set_tracing_disabled,
)
from agents.mcp import MCPServerStreamableHttp
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent, StreamEvent
from asgiref.sync import sync_to_async
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseReasoningTextDeltaEvent,
    ResponseTextDeltaEvent,
)

from .base import BackendCapabilities, BackendError, BackendErrorKind, RunContext, StreamFrame
from .dsh_config import without_proxy_env
from .gateway_cache import GatewaySettings, get_gateway_settings, resolve_gateway_target, settings_from_provider
from .mcp_session_pool import PooledMCPServer, get_mcp_session_pool
from .toolface import SERVER_NAME, endpoint_from_env, port_open, shared_enabled

logger = logging.getLogger(__name__)

#: 一轮内最多允许的模型循环次数（一次模型调用 + 其工具调用算一轮）。
#:
#: ## 为什么从 8 上调到 24（实测，2026-11-21 四栏验收）
#:
#: 原值 8 的依据是「法务工具链通常 3~5 轮收尾，超过 8 轮是空转」。同一句正常业务问题
#: （「先完整推理再回答：民法典 585 条违约金调整规则」+ 61 个直连工具）实测：
#:
#: - 通过：12 次工具调用 / 559 delta（刚好压在 8 轮边缘）
#: - 失败：15 次工具调用 → ``MaxTurnsExceeded: Max turns (8) exceeded``，
#:   **``delta=0``、``done=0``**，用户看到的是「Agent 运行失败，请稍后重试」
#:
#: 也就是说 8 轮不是「空转线」而是「正常工作线」：模型一次只调一个工具时，
#: 「列案件 → 读一个 → 再读一个 → 查法条 → 再核一遍」很容易超过 8 次模型调用，
#: 而**超限的代价是这一栏一个字都不产出**（不是降级，是整轮报废）。
#: 取 24：给 15~20 次工具调用留余量，同时仍是有限值（防真·死循环烧 token）。
MAX_TURNS = 24

#: MCP 工具调用的单次超时（秒）。与服务端 ``TOOL_TIMEOUT_SECONDS``（200s）同口径：
#: 双端超时必须「调用方 > 服务端」，否则文书生成 / 批量类工具会被调用方先掐断。
MCP_CLIENT_TIMEOUT_SECONDS = 200.0

#: 等 SDK 下一个事件的单次上限（秒）。超时就 ``yield None`` 让出一个 tick——
#: 编排层只在后端 yield 时排空事件总线（``services/chat/stream.py``），而审批卡
#: 正是从那条总线来的；不让出就表现为「工具在等审批、前端的卡永远不出现」。
#: 与 ``pi_backend`` 取同一值：两个后端同一套编排层，让出粒度不该各写一份。
TICK_TIMEOUT_SECONDS = 0.2

#: 明确危险、不交给模型的工具名（MCP 原始名，不带 ``mcp__fachuan__`` 前缀——
#: ``tool_filter`` 匹配的是 ``Tool.name``）。
#:
#: **只排除删除类**：用户要求「工具面越多越好」，这里不是收窄，而是摘掉「不可逆
#: 且不该由模型自主发起」的动作。审批闸门（:data:`APPROVAL_GUARDRAIL`）拦的是模型
#: **已经决定**要调的写操作，``delete_case`` 连审批卡都不该弹——直接不给这个工具。
BLOCKED_TOOL_NAMES: tuple[str, ...] = ("delete_case",)

#: 让网关在**流式**响应里也回 ``usage`` 的请求字段。
#:
#: ## 为什么必须显式要（实测，2026-11-21）
#:
#: 律所网关是 LiteLLM → vLLM：``stream=true`` 时**默认不回 usage**，同一句问题
#: 直接 curl 网关的对照结果：
#:
#: - 不带 ``stream_options`` → 全程没有 usage 块（``usage=None``）
#: - 带 ``{"include_usage": true}`` → 末块带
#:   ``{"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10, ...}``
#:
#: 而 ``openai-agents`` 默认不传它（它面向官方端点，那边流式本来就带 usage）。
#: 结果就是这一栏 ``ModelResponse.usage`` 恒 None → 成本账恒记 0
#: （真机实测 ``usage=0in/0out``，同题 pi/antigravity 是 42.9K/38.2K）。
#: 这是**网关侧默认值**的差异，不是 SDK 的 bug，所以补在请求参数上。
STREAM_USAGE_EXTRA_BODY: dict[str, Any] = {"stream_options": {"include_usage": True}}

#: 收尾水位不编造（``done`` 的水位取自本模块 ``result_for``）：SDK 的 ``Usage``
#: 只有 token 计数，没有模型窗口大小。与 ``dsh_backend`` 同口径——编造 0 会让
#: 前端显示「上下文已满」。
_CONTEXT_UNKNOWN: int | None = None


@dataclass(frozen=True)
class OpenAiAgentsRunResult:
    """一轮跑完后交回编排层的事实（与 ``PiRunResult`` / ``DshRunResult`` 同构）。

    ``model`` 来自 ``LLMProvider``（编排层回写 ``AgentSession.llm_model`` 与
    ``AgentRun.model``）；``context_used`` / ``context_total`` 恒为 ``None``，
    原因见 :data:`_CONTEXT_UNKNOWN`。
    """

    model: str | None
    context_used: int | None = None
    context_total: int | None = None


@dataclass(frozen=True)
class McpTarget:
    """本轮要连的 MCP endpoint 与身份。

    ``user_token`` 是律师本人的 access token，**不得写进日志**；它是
    ``mcp_session_pool`` 的分桶依据（取 sha256 指纹后的那一半）。
    """

    url: str
    user_token: str


@dataclass(frozen=True)
class ResolvedGateway:
    """本轮真正要用的网关配置（解析结果，供构造客户端与思考参数使用）。

    ``settings`` 同时交给 :func:`_thinking_settings`：思考开关与模型能力都在
    这份快照里，不再第二次查库。``api_key`` 是**这一轮**的取值（编排层经
    ``RunContext.api_key`` 指定则照用，为空才走 ``_next_key`` 轮转），
    不属于缓存内容（见 ``gateway_cache`` 的红线二）。
    """

    settings: GatewaySettings
    base_url: str
    api_key: str
    model: str


def gateway_from_settings(
    settings: GatewaySettings, model_hint: str | None, *, api_key: str | None = None
) -> tuple[str, str, str] | None:
    """把 :class:`GatewaySettings` 映射成 ``(base_url, api_key, model)``；不可用时 ``None``。

    与 :func:`gateway_from_provider` 的区别只有输入形状：本函数吃的是**缓存里的
    不可变快照**（``gateway_cache.get_gateway_settings`` 的返回值），所以可以在
    事件循环里直接调用、不碰数据库。

    **Key 轮转仍在这里现算**（``_next_key``）：缓存只存 provider 的静态配置
    （全部 key 的列表），不存「这一轮选中的是哪把」——否则轮转序列会被冻结在
    缓存有效期内，所有会话压在同一把 key 上（见 ``gateway_cache`` 模块 docstring
    的红线二）。

    **三条判定口径（key 轮转 / 模型分辨率 / 不可用条件）已收敛到
    :func:`gateway_cache.resolve_gateway_target`**：接第 3、4 个后端时它们只能靠
    「照抄上一份」，而两份实现分叉的症状是「Admin 里换了模型，这一栏还用旧的」。
    本函数只把结果摊成元组（对外签名与历史调用点保持不变）。
    """
    target = resolve_gateway_target(settings, model_hint, api_key=api_key)
    if target is None:
        return None
    return (target.base_url, target.api_key, target.model)


def gateway_from_provider(provider: Any, model_hint: str | None) -> tuple[str, str, str] | None:
    """把 ``LLMProvider`` 映射成 ``(base_url, api_key, model)``；不可用时返回 ``None``。

    本函数**不读库**（``provider`` 由调用方查好传进来），所以可以在事件循环里
    直接调用，也便于用 provider 桩做测试。字段解析复用
    :func:`gateway_cache.settings_from_provider`，与缓存路径走同一份实现。
    """
    return gateway_from_settings(settings_from_provider(provider), model_hint)


def resolve_gateway(model_hint: str | None) -> tuple[str, str, str] | None:
    """查库（命中缓存则免查）+ 映射网关（**同步**，调用方负责 ``sync_to_async``）。

    读库那一步走 ``gateway_cache.get_gateway_settings``：它带 30s TTL 且被
    ``LLMProvider`` 的 save/delete 信号清空，所以既省掉每轮的同步 ORM（实测
    首字延迟里约 1.3s 的量级），又不会让「Admin 里换了模型/换 key」在这栏失效。

    字段解析复用 ``pi.model_config`` 的 ``_load_provider`` /
    ``_provider_keys_and_models`` / ``_provider_models`` / ``_next_key``，不另写
    一套：``api_keys`` 的 ``key|model1,model2`` 格式、``extra_models`` 的混写
    分隔符、key 轮转这些细节各写一份必然分叉，而「Admin 里改了 provider，这一栏
    还用旧配置」是最难查的一类故障（``dsh_config`` 的模块 docstring 记的是同一个
    教训）。
    """
    settings = get_gateway_settings(model_hint)
    if settings is None:
        return None
    return gateway_from_settings(settings, model_hint)


def _is_transport_failure(exc: BaseException) -> bool:
    """异常是否说明「这条 MCP 连接已经不可用」。

    连接失效要能从池里摘掉，否则下一轮会再撞一次同样的超时。判据宽松一点：
    凡是网络/传输层（``OSError`` 全家、``httpx`` / ``anyio`` 的传输异常、
    MCP 自己的 ``UserError`` 包装）都算；**业务错误与取消不算**——``CancelledError``
    是用户按停止，不该当作「连接坏了」（那条连接下次还能正常用）。

    刻意**不**去 import ``httpx`` / ``mcp`` 判具体类型：SDK 与 mcp 的版本
    会漂（本仓库已在 mcp v1/v2 之间切过一次），按「是不是传输类异常」的粗粒度
    判断比绑死类型稳；判错的代价只是「多建一条连接」，比「留一条坏连接」轻。
    """
    if isinstance(exc, asyncio.CancelledError):
        return False
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    text = (type(exc).__name__ + " " + str(exc)).lower()
    return any(
        marker in text for marker in ("connect", "transport", "closed", "disconnect", "broken pipe", "eof", "stream")
    )


def _instructions(ctx: RunContext) -> str:
    """本轮的 system prompt。

    刻意**不**注入仓库级 ``AGENTS.md`` / 技能目录：那是编码 agent 的默认行为，
    对法务场景是多余且不可控的注入面（``dsh_config`` 的收紧层为同一理由关掉了
    skill / agent-instructions 插件）。业务上下文已经由编排层渲染进 ``prompt``。
    """
    return (
        "你是法穿法律事务系统的律师助理。"
        "统一使用简体中文回答，结论先行，引用法条时给出法律名称与条款号。"
        "涉及案件、合同、当事人、期限等事实时，必须用可用的工具查询后再回答，"
        "不要凭记忆编造；工具查不到就如实说明，并给出下一步建议。"
        f"本轮会话：{ctx.session.session_id}"
    )


# ── 人工审批闸门 ──────────────────────────────────────────────────────────

#: 审批闸门开关（环境变量）。默认 on；``off`` / ``0`` / ``false`` / ``no`` 时
#: **既不挂 guardrail、:attr:`OpenAiAgentsBackend.capabilities` 的 ``approval``
#: 也同时变 False**。两处读同一个函数是本模块的硬约束：能力声明是给前端看的
#: 事实（「这一栏有没有人工闸门」），与实现默默分叉就是合规级别的错误信息。
APPROVAL_ENV = "FACHUAN_OPENAI_APPROVAL"

#: 拒绝后喂回模型的文案。刻意不谈「权限 / 系统限制」：律师拒绝是可以谈的，
#: 写明「改用只读方案或提出替代方案」模型才会接着干活，而不是直接终止本轮。
APPROVAL_REJECTED_MESSAGE = "用户拒绝了该操作，请改用只读方案或提出替代方案。"


def approval_enabled() -> bool:
    """审批闸门是否启用（默认启用，解析口径与 ``toolface.shared_enabled`` 一致）。"""
    raw = os.environ.get(APPROVAL_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def backend_capabilities() -> BackendCapabilities:
    """本轮实例的能力声明（``approval`` 与开关同源，其余是静态事实）。

    返回新对象而不是类属性常量：``approval`` 随 ``FACHUAN_OPENAI_APPROVAL`` 变，
    写成类属性就只能在进程启动时取一次值，测试与热切换都会看到陈旧值。
    """
    return BackendCapabilities(
        streaming=True,
        tool_calls=True,
        approval=approval_enabled(),
        compaction=False,
        steer=False,
        concurrent_in_session=True,
    )


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    """把 guardrail 拿到的原始参数串解析成 dict。

    ``ToolContext.tool_arguments`` 是模型发出的**原始 JSON 串**（字符串，不是已解析
    的 dict），与 ``run_item`` 里透传给前端的 ``arguments`` 同一份。解析失败时退回空
    dict 而不是拒绝整个调用：``classify_risk`` 的第一层判据是工具名（删除 / 外发 /
    递交类照样命中），参数级敏感字段判定只是补漏层——「读不出参数就退回纯名字
    口径」与 ``approval.risk`` 里注解表加载失败时的降级同义。
    """
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        logger.warning("工具参数不是合法 JSON，风险判定退回纯名字口径")
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _approval_guardrail(data: ToolInputGuardrailData) -> ToolGuardrailFunctionOutput:
    """高危 / 紧急工具执行前等律师确认；拒绝则以 ``reject_content`` 回给模型。

    分级与审批单全部交给 ``services/approval``（与其它入口同一张审批卡、同一份阈值），
    本函数只负责三件事：把参数交给分级器、拿到决定、翻译成 guardrail 输出。

    **不抛异常**：抛异常会被 SDK 包成 ``Error executing tool ...``，前端标红且看板上
    算成工具故障；真正的语义是「律师拒了，本轮继续」——``reject_content`` 让工具
    不执行、把文案当工具结果交给模型。

    审批服务在函数内 import：``backends`` 在 AppConfig 阶段被导入，而
    ``services.approval`` 要初始化 Django 模型层与事件总线，模块级 import 会把
    ``backends`` ← ``services`` 串成一个启动期的环。
    """
    from ..services.approval import RiskLevel, classify_risk, request_approval

    tool_name = str(data.context.tool_name or "")
    tool_args = _parse_tool_arguments(data.context.tool_arguments)
    if classify_risk(tool_name, tool_args) not in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return ToolGuardrailFunctionOutput.allow()

    ctx = cast(RunContext, data.context.context)
    approved, _approval_id, _reason = await request_approval(
        tool_name=tool_name,
        tool_args=tool_args,
        user_id=ctx.user_id,
        session_id=str(ctx.session.session_id),
        run_id=ctx.run_id,
    )
    if approved:
        return ToolGuardrailFunctionOutput.allow()
    return ToolGuardrailFunctionOutput.reject_content(APPROVAL_REJECTED_MESSAGE)


#: 挂在每个 MCP 工具上的审批 guardrail（开关 ``off`` 时不传给 MCP server，见
#: :func:`build_mcp_server`）。名字进日志与 trace，改名前先搜有没有按名字断言的地方。
APPROVAL_GUARDRAIL: ToolInputGuardrail[Any] = ToolInputGuardrail(
    guardrail_function=_approval_guardrail, name="fachuan_approval"
)


def build_mcp_server(*, url: str, user_token: str, session_id: str = "") -> MCPServerStreamableHttp:
    """建一个（尚未连接的）法穿 MCP 客户端。

    ``tool_filter`` 用**静态 dict** 而不是 callable：callable 过滤器内部抛异常会被
    SDK 静默吞掉（表现是「工具凭空消失」，连日志都没有）。dict 走同一路径但不会抛。

    ``tool_input_guardrails`` 是本栏的人工审批闸门（开关见 :data:`APPROVAL_ENV`）；
    关掉时传 ``None``——不挂闸门与「挂了但放行」在 trace 与行为上都不同，别混。
    """
    return MCPServerStreamableHttp(
        params={
            "url": url,
            "headers": {
                # 会话标识：MCP 服务端审批闸门（mcp_server/tool_approval_gate.py）
                # 靠它把审批卡投到正确会话；不带时会建「无会话单」，只有超管能批，
                # 等于高危工具全拒。头名与 pi / dsh 同源（HTTP 头大小写不敏感）。
                **({"x-fachuan-session": session_id} if session_id else {}),
                "Authorization": f"Bearer {user_token}",
            },
        },
        # tools/list 约 244KB，而每次模型调用都要工具声明；不开缓存每轮多几次全量传输。
        cache_tools_list=True,
        name=SERVER_NAME,
        tool_filter={"blocked_tool_names": list(BLOCKED_TOOL_NAMES)},
        client_session_timeout_seconds=MCP_CLIENT_TIMEOUT_SECONDS,
        tool_input_guardrails=[APPROVAL_GUARDRAIL] if approval_enabled() else None,
    )


def build_openai_client(*, base_url: str, api_key: str) -> AsyncOpenAI:
    """建本轮的网关客户端；**代理剔除窗口只覆盖这一次构造**。

    ## 为什么窗口必须够

    律所网关是内网地址，开发机的 ``HTTPS_PROXY`` 指向本地 Clash；带着代理去访问
    会得到「502 no body」（见 :func:`dsh_config.without_proxy_env` 的 docstring）。
    代理是 httpx 在**客户端构造期**从环境解析并写进 mounts 的，所以构造必须在
    无代理窗口内。

    ## 为什么窗口不能更大

    ``without_proxy_env`` 改的是 ``os.environ``（进程全局）。一轮从建连到最后一个
    token 是秒级，三 agent 并发时这段窗口近乎连续——期间同进程内**其他**出网调用
    若新建 httpx 客户端（GitHub OAuth 换 token、企微、法院系统……）会一起丢掉代理，
    而那几个目标恰恰必须走代理。``without_proxy_env`` 自己的 docstring 也写明
    「删除窗口越短越好」。

    实测（本机，内网网关 + Clash）：构造在窗口内、``Runner.run_streamed`` 与其流式
    迭代都在窗口外，连续 3 轮全部 200。
    """
    with without_proxy_env():
        return AsyncOpenAI(base_url=base_url, api_key=api_key)


def _thinking_settings(model: str, settings: GatewaySettings) -> ModelSettings | None:
    """本轮的思考参数（与 pi 的 compat / dsh 的 compat 同口径）。

    为什么需要手动下发：律所网关是 LiteLLM → vLLM，它把开关拆成两件事——

    - ``chat_template_kwargs.thinking``（布尔）：要不要想；
    - ``reasoning_effort``（字符串）：想多深。

    openai-agents 的 ``OpenAIChatCompletionsModel`` 默认两个都不发，于是同一个
    模型在这里「不开思考、也没有档位」，而 pi/dsh 那边是开的——用户只看到
    「换个 agent 回答变浅了」，不会有任何报错。

    ``reasoning_effort`` 的取值受**服务端白名单**约束（实测 DeepSeek V4.1：
    ``low`` / ``high`` / ``xhigh`` / ``max``），因此不直接写死字面量，而是经
    :func:`apps.core.llm.gateway_profile.gateway_effort` 归一化——原样发 ``medium``
    会 400。字段形状也只有那一处（``wire_fields``）：四个后端各拼一份必然分叉，
    ``kimi-k2`` 就曾在两条通道上判出相反的思考结论（见 ``gateway_profile`` 的
    docstring）。

    Args:
        model: 本轮最终模型名（已按 model_hint / default_model 解析过）。
        settings: 本轮的网关配置快照。**刻意收它而不是自己去查库**：解析思考
            开关原本要再走一次 ``resolve_thinking_level`` → ``_load_provider``，
            那是一轮里的**第二次**同步 ORM 查询（网关解析已经查过一次）。实测
            省下的就是首字延迟里的固定开销。

    Returns:
        ``None`` 表示该模型不开启思考（平台未开或非推理模型），此时不插手请求。
    """
    # 延迟 import：``apps.core.llm`` 是重包（``__init__`` 会拉起 service/config），
    # 而本模块在 ``AgentConfig.ready()`` 注册后端时就被 import（同 ``gateway_cache``）。
    from apps.core.llm.gateway_profile import resolve_thinking, wire_fields

    directives = resolve_thinking(model, enable_thinking=settings.enable_thinking)
    if not directives.enabled:
        # 平台没开思考，或该模型不是推理模型：**一个字段都不插手**（与 pi / dsh 同
        # 口径）。``wire_fields`` 的「显式发 ``thinking=false``」分支是服务通道语义
        # （``openai_compatible`` 要保持历史行为），Agent 通道是不开就不发。
        return None
    return ModelSettings(extra_body=wire_fields(directives))


def _usage_frame(raw_responses: Iterable[Any]) -> dict[str, Any] | None:
    """一轮的 SDK 原始响应 → **一帧** ``usage``（``sse_types.UsageEvent``）；无数据 ``None``。

    ## 源与字段（实测 agents 0.25，不是猜的）

    ``RunResultStreaming.raw_responses`` 是**每次模型调用一条** ``ModelResponse``
    （工具循环一轮会有多条），每条带 ``usage: agents.usage.Usage``：
    ``input_tokens`` / ``output_tokens`` / ``input_tokens_details.cached_tokens`` /
    ``input_tokens_details.cache_write_tokens``。``RawResponsesStreamEvent`` 里拿
    不到它——只有收尾时的 ``result`` 有全量，所以本帧只能在**一轮跑完之后**发。

    ## 口径（为什么这么累加、这么拆）

    - 一轮**最多一帧**：工具循环的每一次模型调用都是一笔真实开销，逐条发会让
      ``stream.py`` 的累加（它按帧求和）依赖帧数；收尾一次总和与服务端计费口径
      一致（``usage.add`` 也是同一个加法）。
    - ``input_tokens`` 在 Responses 语义里**含**缓存命中与缓存写入部分（
      ``InputTokensDetails.cached_tokens`` / ``cache_write_tokens`` 的字段说明都是
      「输入 token 的一部分」），而 ``sse_types.UsageEvent`` 约定 ``input_tokens``
      只装未命中部分、缓存单列。所以这里减掉两者（下限 0，防御 provider 给出
      不一致的值），否则前端算出的命中率恒偏低、成本账虚高。
    - 拿不到就返回 ``None``（不发 0/0 假帧）：provider 不报 usage 时记 0 会让
      「这一栏花了多少钱」看起来是免费，而编造的 0 无法与真实 0 区分。
    """
    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_write_tokens = 0
    reported = False
    for response in raw_responses:
        usage = getattr(response, "usage", None)
        if usage is None:
            continue
        reported = True
        input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        details = getattr(usage, "input_tokens_details", None)
        cache_read_tokens += int(getattr(details, "cached_tokens", 0) or 0)
        cache_write_tokens += int(getattr(details, "cache_write_tokens", 0) or 0)
    if not reported or input_tokens + output_tokens <= 0:
        return None
    return {
        "type": "usage",
        "input_tokens": max(0, input_tokens - cache_read_tokens - cache_write_tokens),
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
    }


class OpenAiAgentsBackend:
    """openai-agents 运行时（每次 ``stream()`` 自建 agent + MCP 连接，跑完即关）。

    能力声明依据见模块 docstring。收尾事实由 ``result_for(run_id)`` 取——编排层
    铸的 ``done`` 与 ``AgentRun`` 都要它，而异步生成器的 ``return`` 值调用方取不到。
    """

    kind = "openai-agents"

    #: 能力声明（:func:`backend_capabilities`）。**实例属性而不是类属性**：
    #: ``approval`` 与 ``FACHUAN_OPENAI_APPROVAL`` 同源，类属性只能在 import 时
    #: 取一次值。
    capabilities: BackendCapabilities

    #: 按 ``run_id`` 归集的收尾事实。键控而不是单值——注册表里存的是单例，而
    #: ``stream()`` 并发（见 ``capabilities.concurrent_in_session``）：实例属性会让
    #: 两个会话互相覆盖对方的结果（pi 的 ``PiBackend`` 同因同解）。
    _results: dict[str, OpenAiAgentsRunResult]

    #: 本轮 ``call_id`` → 工具名。``ToolCallOutputItem`` 不带工具名（见
    #: :meth:`_translate_run_item`），靠这张表把 ``tool_result`` 与前面的
    #: ``tool_call`` 对上。每次 ``stream()`` 重建，并发两轮互不覆盖。
    _tool_names: dict[str, str]

    def __init__(self) -> None:
        self.capabilities = backend_capabilities()
        self._results = {}
        self._tool_names = {}

    def result_for(self, run_id: str) -> OpenAiAgentsRunResult | None:
        """取某一轮的收尾事实；未跑过 / 本轮异常时为 ``None``。"""
        return self._results.get(run_id)

    def stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        """跑一轮，产出一轮全部 SSE 事件。

        事件体已带 ``agent="openai-agents"`` 与 ``run_id=ctx.run_id``（``base.py``
        契约要求）；``meta`` / ``done`` 都由编排层发。本模块**不发** ``done``：
        ``services/chat/stream.py`` 每条流自己铸一条，后端再发一条会让单栏出现两条
        ``done``（实测 ``done=2``），与 ``pi_backend`` / ``antigravity_backend`` 同口径。
        token 用量在最后发且只发一帧（见 :func:`_usage_frame`）。

        Raises:
            BackendError: 网关配置不可用 / SDK 异常，均在边界处转换。
                ``asyncio.CancelledError`` 原样上抛（用户按停止不是错误）。
        """
        return self._stream(ctx)

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        session_id = str(ctx.session.session_id)
        resolved = await self._resolve_gateway(ctx)

        # SDK 默认把 trace 上报到 OpenAI 平台。这里用的是内网网关，key 与 endpoint
        # 都对不上——上报只会产生一批失败请求，还会把会话内容发往境外。关掉。
        set_tracing_disabled(True)

        self._results.pop(ctx.run_id, None)
        self._tool_names = {}
        try:
            async for frame in self._run(ctx, resolved=resolved):
                yield frame
        except BackendError:
            raise
        except Exception as exc:
            logger.warning("openai-agents 本轮失败 session=%s run=%s", session_id, ctx.run_id, exc_info=True)
            raise self._wrap_error(exc) from exc

    async def _resolve_gateway(self, ctx: RunContext) -> ResolvedGateway:
        """解析本轮的网关配置；不可用时报可读错误（``UNAVAILABLE``）。

        读库走 ``sync_to_async``：``_load_provider`` 是同步 ORM 查询，直接在事件
        循环里调会抛 ``SynchronousOnlyOperation``，而那会被兜底 except 吞成「未知
        错误」，排查方向完全被带偏。命中 ``gateway_cache`` 时那一步只是读内存，
        但**仍留在同一个 ``sync_to_async`` 里**：拆成「先探缓存再决定要不要切线程」
        会让未命中的路径多一次往返，而命中的路径本来就只差一次函数调用调度。
        """
        try:
            settings = await sync_to_async(get_gateway_settings, thread_sensitive=True)(ctx.model)
        except Exception as exc:
            raise BackendError.wrap(exc, BackendErrorKind.UNAVAILABLE) from exc
        gateway = gateway_from_settings(settings, ctx.model, api_key=ctx.api_key) if settings is not None else None
        if settings is None or gateway is None:
            # 明确报「没有可用平台配置」，而不是让 SDK 回退到 ``OPENAI_API_KEY`` /
            # 官方端点——那会用错的 key、记错的账，用户完全看不出发生了什么。
            raise BackendError(
                BackendErrorKind.UNAVAILABLE,
                "未配置可用的 AI 平台（base_url / api_key / 模型），openai-agents 无法启动；请联系管理员",
            )
        return ResolvedGateway(settings=settings, base_url=gateway[0], api_key=gateway[1], model=gateway[2])

    async def _run(
        self,
        ctx: RunContext,
        *,
        resolved: ResolvedGateway,
    ) -> AsyncGenerator[StreamFrame, None]:
        """取池里的 MCP 连接 → 跑一轮 → 逐事件翻译 → 收尾发一帧 ``usage``。"""
        base_url, api_key, model = resolved.base_url, resolved.api_key, resolved.model
        target = self._mcp_target(ctx)
        pooled: PooledMCPServer | None = None
        if target is not None:
            pooled = await get_mcp_session_pool().acquire(
                url=target.url,
                user_token=target.user_token,
                factory=lambda: build_mcp_server(
                    url=target.url,
                    user_token=target.user_token,
                    session_id=str(ctx.session.session_id),
                ),
            )

        try:
            # 代理剔除只覆盖客户端构造（窗口为何不能更大：见 ``build_openai_client``）。
            client = build_openai_client(base_url=base_url, api_key=api_key)
            # 思考参数 + 流式 usage 开关合并进同一份 ``extra_body``：
            # 两者都是「网关要的、SDK 默认不发」的字段，分两处构造会让后一处覆盖前一处。
            base_settings = _thinking_settings(model, resolved.settings) or ModelSettings()
            # ``ModelSettings.extra_body`` 的静态类型是 ``object``（SDK 允许任意结构），
            # 直接解包 mypy 会报 [dict-item]；这里先收窄成 dict 再合并——非 dict 时按
            # "没有 base 字段"处理（比抛 TypeError 好：那会让整栏直接失败）。
            base_extra_body = base_settings.extra_body
            model_settings = dataclasses_replace(
                base_settings,
                extra_body={
                    **(base_extra_body if isinstance(base_extra_body, dict) else {}),
                    **STREAM_USAGE_EXTRA_BODY,
                },
            )
            agent = Agent(
                name="法穿法律助手",
                model=OpenAIChatCompletionsModel(model=model, openai_client=client),
                # ``ctx.system_prompt`` 给了就全量替换默认人格（综合结论等一次性任务）。
                instructions=ctx.system_prompt if ctx.system_prompt is not None else _instructions(ctx),
                mcp_servers=[pooled.server] if pooled is not None else [],
                # 思考强度：与 pi / dsh 同口径、同模型、同档位。
                # 三个 agent 跑的是同一个网关同一份模型，若只给其中两个配，
                # 用户换 agent 就会发现「同一个模型差一截」而这种差异不报错。
                #
                # 不思考时传空 ``ModelSettings()`` 而不是 ``None``：SDK 的
                # ``Agent.model_settings`` 不接受 None，传 None 会被当成
                # “沿用默认”，与“显式不要思考参数”是两回事。
                model_settings=model_settings,
            )
            # ``context=ctx`` 不只是「顺手传个上下文」：审批 guardrail 只能经
            # ``data.context.context`` 取回本轮 RunContext（用户 / 会话 / run_id
            # 三个归因字段）。不传时闸门就变成无主审批单，审计断链。
            # 不传 SDK ``session``：每轮无状态，历史只在 ``ctx.prompt`` 里，``ctx.isolated``
            # 天然成立（不读也不写任何持久对话历史）。
            max_turns = ctx.max_turns if ctx.max_turns is not None else MAX_TURNS
            result = Runner.run_streamed(agent, ctx.prompt, context=ctx, max_turns=max_turns)
            stream_events = result.stream_events()
            pending_next: asyncio.Task[Any] | None = None
            try:
                while True:
                    if pending_next is None:
                        pending_next = asyncio.ensure_future(stream_events.__anext__())
                    await asyncio.wait({pending_next}, timeout=TICK_TIMEOUT_SECONDS)
                    if not pending_next.done():
                        # 本 tick 没有新事件：让出一帧，编排层借它把外部总线里的
                        # 审批事件推进来（工具正在等 approval_guardrail，那段时间
                        # SDK 不会产出任何事件）。``pending_next`` 不丢：它还挂着
                        # 一次 ``__anext__``，下一轮循环继续等它（不重复取、不泄漏）。
                        yield None
                        continue
                    task, pending_next = pending_next, None
                    try:
                        event = task.result()
                    except StopAsyncIteration:
                        break
                    for frame in self._translate_stream_event(event):
                        yield {**frame, "agent": self.kind, "run_id": ctx.run_id}
            finally:
                if pending_next is not None:
                    # 提前退出（done / 取消）时可能还挂着一次 __anext__，必须收掉，
                    # 否则任务泄漏并在事件循环关闭时刷 "Task was destroyed" 警告。
                    pending_next.cancel()
                if not result.is_complete:
                    # 客户端断开 / 提前 break：让 SDK 的后台任务停下来，否则它会
                    # 继续跑模型循环（烧 token），并在事件循环关闭时刷
                    # "Task was destroyed" 警告。
                    result.cancel()
        except BaseException as exc:
            # 连接层面的失败（传输断了 / 服务端重启）说明这条连接已经不可用：
            # 从池里摘掉，别让下一轮再撞一次超时。``BaseException`` 是为了把
            # ``CancelledError`` 也覆盖到——用户按停止后那条连接上的半截响应
            # 同样不可信。异常一律原样上抛（取消不得转成 BackendError）。
            if pooled is not None and target is not None and _is_transport_failure(exc):
                await get_mcp_session_pool().discard(url=target.url, user_token=target.user_token, pooled=pooled)
                pooled = None
            raise
        finally:
            if pooled is not None and target is not None:
                # **不关闭**：留给池复用（关闭=没有复用）。真正回收由空闲 TTL /
                # 桶淘汰 / 连接失效三处执行，见 ``mcp_session_pool`` 的模块 docstring。
                get_mcp_session_pool().release(url=target.url, user_token=target.user_token, pooled=pooled)

        # 收尾事实要在最后那一帧**之前**写好：编排层拿到 usage 后就可能结束迭代
        # （客户端断开），之后本生成器不会再往下跑。
        self._results[ctx.run_id] = OpenAiAgentsRunResult(model=model)
        usage = _usage_frame(result.raw_responses)
        if usage is not None:
            yield {**usage, "agent": self.kind, "run_id": ctx.run_id}

    def _mcp_target(self, ctx: RunContext) -> McpTarget | None:
        """本轮该连哪个 MCP、用谁的 token；不该连/连不上返回 ``None``。

        **没有律师 token 就不接工具**：:8011 强制每请求 Bearer 且**刻意不回退服务
        账号**（越权修复）。硬连只会 401 把「本来能对话」变成「整轮失败」。与
        ``dsh_mcp.ensure_mcp_patch`` 同口径：降级为「无工具但能对话」并留 warning
        ——工具面缺失是用户可感知的能力变化，不能静默。

        ``token`` 只放在返回值里，**绝不进日志**（日志只写长度或干脆不写）：
        它是律师本人的业务读权限凭据。
        """
        token = (ctx.user_token or "").strip()
        if not token:
            logger.warning("openai-agents 本轮没有律师 token，无法接入法穿 MCP 工具（无工具但可对话）")
            return None
        if not shared_enabled():
            logger.warning("共享 MCP 已禁用（FACHUAN_MCP_SHARED=0），openai-agents 本轮无业务工具")
            return None
        endpoint = endpoint_from_env()
        if not port_open(endpoint.host, endpoint.port):
            # 不在这里拉起共享 MCP：冷启动实测 ~6s，会卡住整个事件循环。pi / dsh 的
            # acquire 路径会自愈拉起，下一轮自然就有工具了。
            logger.warning("共享 MCP %s 不可连，openai-agents 本轮无业务工具", endpoint.url)
            return None
        return McpTarget(url=endpoint.url, user_token=token)

    # ── 事件翻译 ─────────────────────────────────────────────────────────

    def _translate_stream_event(self, event: StreamEvent) -> list[dict[str, Any]]:
        """把一个 SDK 流事件翻成 0..n 个 SSE 事件。

        两类源事件（``agents.stream_events``）：

        - ``raw_response_event``：LLM 原始增量，``data.type`` 决定是正文还是思考；
        - ``run_item_stream_event``：语义 run item（工具调用 / 工具输出）。

        ``agent_updated_stream_event`` 只在 handoff 时出现，本后端不配 handoff。
        **刻意不「凡不认识就透传 unknown」**：原始事件流里还有几十种生命周期事件
        （``response.created`` / ``output_item.added`` / ``completed`` …），每轮
        全刷一遍只会让前端与日志全是噪音。
        """
        if isinstance(event, RawResponsesStreamEvent):
            return self._translate_raw_event(event.data)
        if isinstance(event, RunItemStreamEvent):
            return self._translate_run_item(event.name, event.item)
        return []

    @staticmethod
    def _translate_raw_event(data: Any) -> list[dict[str, Any]]:
        """原始 LLM 增量 → ``delta`` / ``thinking``。

        ``delta`` 已是字符串（SDK 保证），直接下发、不做拼接：前端逐条追加，与其它
        后端的 ``delta`` 语义一致。思考有两种事件：``reasoning_summary_text.delta``
        （网关摘要）与 ``reasoning_text.delta``（原文），都翻成 ``thinking``——两者的
        区别是 provider 侧实现细节，前端一视同仁地展示为「思考中」。
        """
        if isinstance(data, ResponseTextDeltaEvent):
            delta = str(getattr(data, "delta", "") or "")
            return [{"type": "delta", "content": delta}] if delta else []
        if isinstance(data, (ResponseReasoningTextDeltaEvent, ResponseReasoningSummaryTextDeltaEvent)):
            delta = str(getattr(data, "delta", "") or "")
            return [{"type": "thinking", "content": delta}] if delta else []
        return []

    def _translate_run_item(self, name: str, item: Any) -> list[dict[str, Any]]:
        """语义 run item → ``tool_call`` / ``tool_result``。

        只翻译两种有用户可见价值的 item：

        - ``tool_called`` / ``tool_search_called`` → ``tool_call``：律师要看「查了
          哪些法条 / 案件」，这是可展示的证据链；
        - ``tool_output`` → ``tool_result``。

        ``message_output_created`` 不进这里：正文已经由 ``delta`` 逐字发过，再发一遍
        会让前端出现**双份回答**。``reasoning_item_created`` 同理（``thinking`` 已发）。
        """
        if name in ("tool_called", "tool_search_called"):
            raw = getattr(item, "raw_item", None)
            call_id = str(getattr(item, "call_id", "") or "")
            tool_name = str(getattr(item, "tool_name", "") or "")
            if not call_id or not tool_name:
                return []
            # 记下 call_id → 工具名，供后续 ``tool_output`` 补名：SDK 的
            # ``ToolCallOutputItem.raw_item`` 里**没有** name（实测是
            # ``{"type": "function_call_output", "call_id": ...}``），不配对就只剩空串。
            self._tool_names[call_id] = tool_name
            arguments = raw.arguments if isinstance(raw, ResponseFunctionToolCall) else None
            return [
                {
                    "type": "tool_call",
                    "tool_call_id": call_id,
                    "name": tool_name,
                    "arguments": arguments if isinstance(arguments, str) else None,
                }
            ]
        if name == "tool_output":
            call_id = str(getattr(item, "call_id", "") or "")
            if not call_id:
                return []
            # 工具名不在 ``ToolCallOutputItem`` 上（``raw_item`` 是
            # ``function_call_output``，只有 call_id）：用前面 ``tool_called`` 记下的
            # 配对表补名。仍取不到就给空串——``tool_result.name`` 是必填字符串，前端
            # 靠 ``tool_call_id`` 与 ``tool_call`` 配对，不依赖这个名字。
            raw = getattr(item, "raw_item", None)
            tool_name = self._tool_names.get(call_id) or str(getattr(raw, "name", "") or "")
            output = getattr(item, "output", None)
            text = output if isinstance(output, str) else (None if output is None else str(output))
            # SDK 把工具失败包成一段 ``Error executing tool ...`` 文本而不是抛异常，
            # 按前缀识别，让前端能把失败的工具标红（否则失败与成功长得一样）。
            is_error = bool(text and text.lstrip().startswith("Error executing tool"))
            return [
                {
                    "type": "tool_result",
                    "tool_call_id": call_id,
                    "name": tool_name,
                    "result": text,
                    "is_error": is_error,
                }
            ]
        return []

    # ── 错误分类 ─────────────────────────────────────────────────────────

    @staticmethod
    def _wrap_error(exc: BaseException) -> BackendError:
        """把 SDK / 网关异常转成 ``BackendError``（分类口径见 ``base.py`` 的映射表）。

        优先按 ``openai`` 的异常**类型**判（``AuthenticationError`` /
        ``RateLimitError`` / ``APIConnectionError`` …）：网关的 4xx/5xx 会被包成
        ``APIStatusError`` 的具体子类，类型是结构化事实，比消息匹配可靠。类型认不出
        时才退回关键词（SDK 自己的 ``MaxTurnsExceeded`` / ``ModelBehaviorError`` 只带
        文本）。

        网关 5xx（``InternalServerError`` 等）归 ``UNAVAILABLE`` 且可重试：
        实测网关没起来时 ``AsyncOpenAI`` 会把它包成 ``InternalServerError``，归
        ``UNKNOWN`` 会让用户看到「未知错误」而不是「稍后重试」。
        """
        if isinstance(exc, BackendError):
            return exc
        if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
            return BackendError.wrap(exc, BackendErrorKind.AUTH)
        if isinstance(exc, RateLimitError):
            return BackendError.wrap(exc, BackendErrorKind.RATE_LIMITED, retryable=True)
        if isinstance(exc, APIStatusError) and exc.status_code >= 500:
            return BackendError.wrap(exc, BackendErrorKind.UNAVAILABLE, retryable=True)
        if isinstance(exc, (APIConnectionError, APITimeoutError, ConnectionError, TimeoutError, OSError)):
            return BackendError.wrap(exc, BackendErrorKind.UNAVAILABLE, retryable=True)

        text = str(exc) or exc.__class__.__name__
        lowered = text.lower()
        if "api key" in lowered or "401" in lowered or "403" in lowered or "unauthorized" in lowered:
            return BackendError.wrap(exc, BackendErrorKind.AUTH)
        if "429" in lowered or "rate limit" in lowered:
            return BackendError.wrap(exc, BackendErrorKind.RATE_LIMITED, retryable=True)
        if "context" in lowered and ("window" in lowered or "length" in lowered or "overflow" in lowered):
            return BackendError.wrap(exc, BackendErrorKind.CONTEXT_OVERFLOW)
        return BackendError.wrap(exc, BackendErrorKind.UNKNOWN)
