"""工作台 Agent 定义

使用 Pydantic AI 构建多 Agent 系统：
- triage_agent: 分诊路由，根据用户意图委托给专业 Agent
- case_agent: 案件管理
- contract_agent: 合同管理
- research_agent: 法律检索
- general_agent: 通用助手

所有 Agent 共享同一个 MCPServerStdio 实例（进程复用）。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.profiles.openai import OpenAIModelProfile

from apps.core.llm.config import LLMConfig

from .approval import HIGH_RISK_TOOLS, approval_manager, process_tool_call_with_approval
from .deps import WorkbenchDeps

logger = logging.getLogger(__name__)

# ─── 常量 ────────────────────────────────────────────────────────────────────

BACKEND_DIR = str(Path(__file__).resolve().parents[3])

BASE_SYSTEM_PROMPT = """你是法穿AI Copilot，一个法律事务助手。你可以通过调用工具来完成各种法律事务操作，包括：
- 案件管理（创建、查询、修改案件）
- 客户管理（创建、查询客户信息）
- 合同管理（查询、下载、生成合同）
- 提醒管理（创建、查询提醒）
- 财务统计
- 法律检索
- 企业信息查询
- 联网搜索（搜索互联网获取最新信息、新闻、法规等）
- 等等

当你需要执行操作或查询信息时，请使用工具调用。请用中文回复。

重要提示：
- 如果用户询问最新信息、实时新闻、最近法规变化等，请使用联网搜索工具
- 如果工具调用返回错误，请分析错误原因并尝试修正参数重新调用
- 如果多次失败，请告知用户具体原因和建议
- 对于高风险操作（如删除、发送），系统会要求用户确认后再执行"""

CONTEXT_SUFFIX = """当前会话信息：
- 会话 ID：{session_id}
- 使用模型：{llm_model}
{summary_section}"""


def _build_instructions(base: str, deps: WorkbenchDeps) -> str:
    """构建带上下文的 system prompt"""
    summary_section = ""
    if deps.conversation_summary:
        summary_section = f"- 之前对话摘要：\n{deps.conversation_summary}"

    context = CONTEXT_SUFFIX.format(
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


def build_model(model_name: str) -> OpenAIChatModel:
    """根据模型名动态构建 Pydantic AI Model

    复用已有的 LLMConfig 后端路由逻辑：
    - 包含 "/" → SiliconFlow
    - 包含 ":" → Ollama
    - 其他 → OpenAI Compatible
    """
    backend = LLMConfig.resolve_backend_for_model(model_name)

    if backend == "ollama":
        base_url = LLMConfig.get_ollama_base_url()
        api_key = "ollama"
    elif backend == "openai_compatible":
        api_key = LLMConfig.get_openai_compatible_api_key()
        base_url = LLMConfig.get_openai_compatible_base_url()
    else:
        # 默认 siliconflow
        api_key = LLMConfig.get_api_key()
        base_url = LLMConfig.get_base_url()

    if backend != "ollama" and not api_key:
        logger.warning("LLM API Key 未配置，backend=%s", backend)

    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(
            base_url=base_url,
            api_key=api_key or "ollama",
        ),
        profile=OpenAIModelProfile(
            openai_supports_strict_tool_definition=False,
        ),
    )


# ─── MCP Server（共享实例，带审批回调） ───────────────────────────────────────

mcp_server = MCPServerStdio(
    sys.executable,
    args=["-m", "mcp_server"],
    cwd=BACKEND_DIR,
    tool_prefix="",
    timeout=30,
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
    return any(kw in name for kw in ["search", "research", "enterprise", "company", "bidding", "person", "profile", "web"])


# ─── 专业 Agent ──────────────────────────────────────────────────────────────

case_agent = Agent(
    None,  # model 由 triage 委托时动态传入
    instructions=_build_instructions(
        BASE_SYSTEM_PROMPT + "\n\n你专门负责案件管理相关操作，包括创建、查询、修改案件信息。",
        WorkbenchDeps(session_id=0),
    ),
    deps_type=WorkbenchDeps,
    toolsets=[mcp_server.filtered(_case_filter)],
    name="案件管理助手",
)

contract_agent = Agent(
    None,
    instructions=_build_instructions(
        BASE_SYSTEM_PROMPT + "\n\n你专门负责合同管理相关操作，包括查询、下载、生成合同。",
        WorkbenchDeps(session_id=0),
    ),
    deps_type=WorkbenchDeps,
    toolsets=[mcp_server.filtered(_contract_filter)],
    name="合同管理助手",
)

research_agent = Agent(
    None,
    instructions=_build_instructions(
        BASE_SYSTEM_PROMPT + "\n\n你专门负责法律检索和企业信息查询。",
        WorkbenchDeps(session_id=0),
    ),
    deps_type=WorkbenchDeps,
    toolsets=[mcp_server.filtered(_research_filter)],
    name="法律检索助手",
)

general_agent = Agent(
    None,
    instructions=_build_instructions(BASE_SYSTEM_PROMPT, WorkbenchDeps(session_id=0)),
    deps_type=WorkbenchDeps,
    toolsets=[mcp_server],
    name="通用助手",
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
        model=ctx.model,
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
        model=ctx.model,
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
        model=ctx.model,
    )
    return result.output


TRIAGE_PROMPT = (
    BASE_SYSTEM_PROMPT
    + """\n\n你是分诊助手。根据用户意图，使用 handoff 工具将请求路由到专业助手：
- 案件相关（创建、查询、修改案件）→ handoff_to_case
- 合同相关（查询、下载、生成合同）→ handoff_to_contract
- 法律检索、企业查询 → handoff_to_research
- 其他或不确定 → 直接回复或使用通用工具

重要：你也可以直接使用 MCP 工具完成简单操作，不必总是委托。"""
)

triage_agent = Agent(
    None,
    instructions=_build_instructions(TRIAGE_PROMPT, WorkbenchDeps(session_id=0)),
    deps_type=WorkbenchDeps,
    toolsets=[mcp_server],
    tools=[
        Tool(_handoff_to_case, takes_ctx=True),
        Tool(_handoff_to_contract, takes_ctx=True),
        Tool(_handoff_to_research, takes_ctx=True),
    ],
    name="分诊助手",
)
