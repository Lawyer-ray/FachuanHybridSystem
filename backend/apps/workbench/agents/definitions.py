"""工作台 Agent 定义

使用 Pydantic AI 构建多 Agent 系统：
- triage_agent: 分诊路由，根据用户意图委托给专业 Agent
- case_agent: 案件管理
- contract_agent: 合同管理
- research_agent: 法律检索

所有 Agent 共享同一个 MCPToolset 实例（进程复用）。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Any, cast

from fastmcp.client import Client
from pydantic_ai import Agent, ConcurrencyLimiter, RunContext, Tool, limit_model_concurrency
from pydantic_ai.capabilities.instrumentation import Instrumentation
from pydantic_ai.mcp import MCPToolset, StdioTransport
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from apps.core.llm.config import LLMConfig

from .approval import HIGH_RISK_TOOLS, approval_manager, process_tool_call_with_approval
from .deps import WorkbenchDeps
from .http_client import shared_http_client
from .multi_key_model import DEFAULT_AGENT_CONCURRENCY, MultiKeyOpenAIModel, agent_concurrency_capacity, shared_key_pool

logger = logging.getLogger(__name__)

# ─── 常量 ────────────────────────────────────────────────────────────────────

BACKEND_DIR = str(Path(__file__).resolve().parents[3])

BASE_SYSTEM_PROMPT = """你是法穿AI Copilot，一个法律事务助手。你拥有丰富的工具，必须通过调用工具来完成用户的请求，绝不要凭自己的知识猜测回答。

可用工具类别：
- 案件管理（创建、查询、修改案件）
- 客户管理（创建、查询客户信息）
- 合同管理（查询、下载、生成合同）
- 提醒管理（创建、查询提醒）
- 财务统计、LPR 利率查询
- 法律检索、类案检索
- 企业信息查询（工商信息、股东、风险等）
- 联网搜索（web_search 工具）

核心原则：
1. 必须使用工具：用户问任何需要数据的问题时，你必须调用相应工具获取数据，不要凭记忆回答
2. 联网搜索优先：当用户询问实时信息（时间、天气、新闻、最新法规、当前事件等）时，必须调用 web_search 工具搜索，不要说"我无法获取实时信息"
3. 不要拒绝：如果你有相关工具可以完成任务，就直接调用工具，不要告诉用户你做不到
4. 错误重试：如果工具调用返回错误，分析原因并尝试修正参数重新调用
5. 高风险确认：对于删除、发送等高风险操作，系统会要求用户确认后再执行

请用中文回复。"""

CONTEXT_SUFFIX = """当前会话信息：
- 当前日期：{current_date}
- 会话 ID：{session_id}
- 使用模型：{llm_model}
{summary_section}"""


def _build_instructions(base: str, deps: WorkbenchDeps) -> str:
    """构建带上下文的 system prompt"""
    from datetime import datetime

    summary_section = ""
    if deps.conversation_summary:
        summary_section = f"- 之前对话摘要：\n{deps.conversation_summary}"

    now = datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    current_date = f"{now.year}年{now.month}月{now.day}日 {weekdays[now.weekday()]}"

    context = CONTEXT_SUFFIX.format(
        current_date=current_date,
        session_id=deps.session_id,
        llm_model=deps.llm_model or "未指定",
        summary_section=summary_section,
    )
    return f"{base}\n\n{context}"


# ─── 审批事件队列（per-request，ContextVar 隔离并发请求） ─────────────────────

_current_event_queue: ContextVar[asyncio.Queue[dict[str, Any] | None] | None] = ContextVar(
    "_current_event_queue",
    default=None,
)
_current_agent_name: ContextVar[str] = ContextVar("_current_agent_name", default="triage")
_current_user_id: ContextVar[int | None] = ContextVar("_current_user_id", default=None)


def set_event_queue(
    queue: asyncio.Queue[dict[str, Any] | None] | None,
    agent_name: str = "triage",
    user_id: int | None = None,
) -> None:
    """设置当前请求的事件队列、agent 名称和用户 ID（stream_chat 调用前设置）"""
    _current_event_queue.set(queue)
    _current_agent_name.set(agent_name)
    _current_user_id.set(user_id)


async def _process_tool_call(ctx: Any, call_tool: Any, name: str, tool_args: dict[str, Any]) -> Any:
    """MCP process_tool_call 回调：拦截高风险工具，推入审批事件"""
    queue = _current_event_queue.get()
    if queue is None:
        return await call_tool(name, tool_args)

    # 检测 handoff 工具调用，发送 handoff 事件
    if "handoff" in name:
        target = name.replace("_handoff_to_", "")
        source = _current_agent_name.get()
        await queue.put(
            {
                "type": "handoff",
                "from_agent": source,
                "to_agent": target,
            }
        )

    user_id = _current_user_id.get()
    return await process_tool_call_with_approval(ctx, call_tool, name, tool_args, queue, user_id=user_id)


# ─── Model 构建 ──────────────────────────────────────────────────────────────

# HTTP 重试交给 openai SDK 自带机制：默认 max_retries=2，覆盖 408/409/429/5xx，
# 且解析 Retry-After / Retry-After-Ms（openai/_base_client.py::_calculate_retry_timeout），
# 最终仍失败时按状态码抛 RateLimitError / AuthenticationError 等**类型化**异常。
#
# 原先这里还挂了一层 AsyncHTTPX2TenacityTransport，但它没传 validate_response，而重试条件
# 是 retry_if_exception_type(httpx2.HTTPStatusError) —— transport 层根本拿不到该异常
# （响应不会 raise_for_status），所以那一层从未重试过，属死代码。若直接补 validate_response，
# 异常会在 SDK 之前抛出、被其 except Exception 归类成 APIConnectionError，反而丢掉状态码语义，
# 并与 SDK 自身重试叠加成最多 9 次。故移除该层，显式委托给 SDK。

# 全局并发限制器（所有模型共享，防止压爆 LLM provider rate limit）。
# 容量随平台配置（Key 数 × 每 Key 上限）变化时重建，见 _get_model_limiter。
_model_limiter: ConcurrencyLimiter | None = None
_model_limiter_capacity: int | None = None


def _get_model_limiter(capacity: int) -> ConcurrencyLimiter:
    """返回全局并发限制器，容量变化时重建。

    容量取「Key 数 × 每 Key 上限」，与 Key 池的实际吞吐对齐；再往上加并发只会
    触发 Key 池的超限兜底（用延迟换成功率），卡在容量点排队更划算。

    重建只影响后续 ``build_model`` 调用拿到的限制器，已经在跑的请求仍持有旧实例，
    因此不会打断进行中的会话。
    """
    global _model_limiter, _model_limiter_capacity
    if _model_limiter is None or _model_limiter_capacity != capacity:
        _model_limiter = ConcurrencyLimiter(max_running=capacity, max_queued=20)
        _model_limiter_capacity = capacity
        logger.info("Agent 模型并发上限设为 %s", capacity)
    return _model_limiter


def _build_openai_model(model_name: str, base_url: str, api_key: str) -> OpenAIChatModel:
    """构建单 Key 的 OpenAI-compatible 模型；HTTP 客户端全进程共用。"""
    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(
            base_url=base_url,
            api_key=api_key,
            http_client=shared_http_client(),
        ),
        profile=OpenAIModelProfile(
            openai_supports_strict_tool_definition=False,
        ),
    )


def build_model(model_name: str) -> Model:
    """根据模型名动态构建 Pydantic AI Model

    复用已有的 LLMConfig 后端路由逻辑：
    - 包含 ":" → Ollama
    - 其他 → OpenAI Compatible

    自动附加：
    - HTTP 重试（由 openai SDK 负责：429/5xx，最多 2 次，尊重 Retry-After）
    - 并发限制（容量 = Key 数 × 每 Key 并发上限）

    OpenAI-compatible 平台下按模型名解析平台配置，并为每个 Key 各建一个模型，
    由 ``MultiKeyOpenAIModel`` 轮询——这样网关的「每 Key 并发上限」才能真正用上。
    """
    backend = LLMConfig.resolve_backend_for_model(model_name)

    if backend == "ollama":
        model = _build_openai_model(
            model_name,
            LLMConfig.get_ollama_base_url(),
            "ollama",  # pragma: allowlist secret
        )
        return limit_model_concurrency(model, _get_model_limiter(DEFAULT_AGENT_CONCURRENCY))

    provider = LLMConfig.get_openai_compatible_provider(model_name)
    if provider is None or not provider.api_keys:
        # 未配置平台（或平台无 Key）：沿用单 Key 配置，兼容本地免鉴权 vLLM
        api_key = LLMConfig.get_openai_compatible_api_key()
        if not api_key:
            logger.warning("LLM API Key 未配置，backend=%s", backend)
        model = _build_openai_model(
            model_name,
            LLMConfig.get_openai_compatible_base_url(),
            api_key or "ollama",  # pragma: allowlist secret
        )
        return limit_model_concurrency(model, _get_model_limiter(DEFAULT_AGENT_CONCURRENCY))

    pool = shared_key_pool(provider)
    if not pool.has_key_for(model_name):
        logger.warning(
            "平台「%s」没有 API Key 被授权访问模型 %s，Agent 调用将直接失败",
            provider.name,
            model_name,
        )

    keyed_models: list[Model] = [_build_openai_model(model_name, provider.base_url, key) for key in provider.api_keys]
    rotating: Model = MultiKeyOpenAIModel(keyed_models, pool, model_name)
    return limit_model_concurrency(rotating, _get_model_limiter(agent_concurrency_capacity(provider)))


# ─── MCP Server（共享实例，带审批回调） ───────────────────────────────────────

# pydantic-ai 2.0：MCPServerStdio 被 MCPToolset + StdioTransport + fastmcp.Client 替代。
# MCPToolset 第一个参数是 fastmcp.Client（pre-built），process_tool_call 通过关键字传入。
# timeout 传给 Client（read_timeout），init_timeout 用默认值 5s。
_mcp_transport = StdioTransport(
    command=sys.executable,
    args=["-m", "mcp_server"],
    cwd=BACKEND_DIR,
)
_mcp_client = Client(_mcp_transport, timeout=30)
mcp_server = MCPToolset(
    _mcp_client,
    process_tool_call=_process_tool_call,
)

# ─── 工具过滤函数 ────────────────────────────────────────────────────────────


def _case_filter(ctx: Any, tool_def: Any) -> bool:
    name = tool_def.name.lower()
    return any(kw in name for kw in ["case", "litigation", "court", "hearing", "party", "log", "assign"])


def _contract_filter(ctx: Any, tool_def: Any) -> bool:
    name = tool_def.name.lower()
    return any(kw in name for kw in ["contract", "agreement"])


def _research_filter(ctx: Any, tool_def: Any) -> bool:
    name = tool_def.name.lower()
    return any(
        kw in name for kw in ["search", "research", "enterprise", "company", "bidding", "person", "profile", "web"]
    )


# ─── 动态指令函数（每次 run 时实时生成上下文） ────────────────────────────────

_CASE_PROMPT = BASE_SYSTEM_PROMPT + "\n\n你专门负责案件管理相关操作，包括创建、查询、修改案件信息。"
_CONTRACT_PROMPT = BASE_SYSTEM_PROMPT + "\n\n你专门负责合同管理相关操作，包括查询、下载、生成合同。"
_RESEARCH_PROMPT = BASE_SYSTEM_PROMPT + "\n\n你专门负责法律检索和企业信息查询。"

TRIAGE_PROMPT = (
    BASE_SYSTEM_PROMPT
    + """\n\n你是分诊助手。根据用户意图，使用 handoff 工具将请求路由到专业助手：
- 案件相关（创建、查询、修改案件）→ handoff_to_case
- 合同相关（查询、下载、生成合同）→ handoff_to_contract
- 法律检索、企业查询 → handoff_to_research
- 联网搜索、实时信息查询 → 直接调用 web_search 工具
- 其他或不确定 → 直接回复或使用通用工具

重要：
- 你也可以直接使用 MCP 工具完成简单操作，不必总是委托
- 搜索互联网信息时，直接使用 web_search 工具，不要委托给其他助手"""
)


def _case_instructions(ctx: RunContext[WorkbenchDeps]) -> str:
    return _build_instructions(_CASE_PROMPT, ctx.deps)


def _contract_instructions(ctx: RunContext[WorkbenchDeps]) -> str:
    return _build_instructions(_CONTRACT_PROMPT, ctx.deps)


def _research_instructions(ctx: RunContext[WorkbenchDeps]) -> str:
    return _build_instructions(_RESEARCH_PROMPT, ctx.deps)


def _triage_instructions(ctx: RunContext[WorkbenchDeps]) -> str:
    return _build_instructions(TRIAGE_PROMPT, ctx.deps)


# ─── 专业 Agent ──────────────────────────────────────────────────────────────

case_agent = Agent(
    None,  # model 由 triage 委托时动态传入
    instructions=_case_instructions,
    deps_type=WorkbenchDeps,
    toolsets=[mcp_server.filtered(_case_filter)],
    name="案件管理助手",
    capabilities=[Instrumentation()],
)

contract_agent = Agent(
    None,
    instructions=_contract_instructions,
    deps_type=WorkbenchDeps,
    toolsets=[mcp_server.filtered(_contract_filter)],
    name="合同管理助手",
    capabilities=[Instrumentation()],
)

research_agent = Agent(
    None,
    instructions=_research_instructions,
    deps_type=WorkbenchDeps,
    toolsets=[mcp_server.filtered(_research_filter)],
    name="法律检索助手",
    capabilities=[Instrumentation()],
)

# ─── Triage Agent（带 Handoff 工具） ─────────────────────────────────────────


async def _handoff_to_case(ctx: RunContext[WorkbenchDeps], query: str) -> str:
    """当用户请求与案件管理相关时，将请求委托给案件管理助手。

    Args:
        query: 用户的原始请求或需要案件管理助手处理的具体问题
    """
    result = await case_agent.run(
        query,
        deps=ctx.deps,
        message_history=ctx.messages,
        model=cast("Model[Any] | None", ctx.model),
    )
    return result.output


async def _handoff_to_contract(ctx: RunContext[WorkbenchDeps], query: str) -> str:
    """当用户请求与合同管理相关时，将请求委托给合同管理助手。

    Args:
        query: 用户的原始请求或需要合同管理助手处理的具体问题
    """
    result = await contract_agent.run(
        query,
        deps=ctx.deps,
        message_history=ctx.messages,
        model=cast("Model[Any] | None", ctx.model),
    )
    return result.output


async def _handoff_to_research(ctx: RunContext[WorkbenchDeps], query: str) -> str:
    """当用户请求与法律检索或企业信息查询相关时，将请求委托给法律检索助手。

    Args:
        query: 用户的原始请求或需要法律检索助手处理的具体问题
    """
    result = await research_agent.run(
        query,
        deps=ctx.deps,
        message_history=ctx.messages,
        model=cast("Model[Any] | None", ctx.model),
    )
    return result.output


triage_agent = Agent(
    None,
    instructions=_triage_instructions,
    deps_type=WorkbenchDeps,
    toolsets=[mcp_server],
    tools=[
        Tool(_handoff_to_case, takes_ctx=True),
        Tool(_handoff_to_contract, takes_ctx=True),
        Tool(_handoff_to_research, takes_ctx=True),
    ],
    name="分诊助手",
    capabilities=[Instrumentation()],
)
