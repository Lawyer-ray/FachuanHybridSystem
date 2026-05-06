"""工作台对话编排服务 - Pydantic AI Agent

使用 Pydantic AI 的 agent.iter() 驱动对话循环，替代手写 agent loop。
通过 asyncio.Queue 桥接 MCP 审批回调和 SSE 流式响应。

功能：
1. 对话历史管理（token 估算 + 滑动窗口）
2. 结构化输出（工具调用结果结构化）
3. 工具调用确认前置（审批机制）
4. 会话记忆（自动压缩长对话）
5. 多 MCP Server 支持（toolset 组合）
6. Token 用量追踪与限制
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from asgiref.sync import sync_to_async
from pydantic_ai import Agent, UsageLimits
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.result import AgentStream

from ..agents import (
    WorkbenchDeps,
    approval_manager,
    build_model,
    case_agent,
    contract_agent,
    general_agent,
    research_agent,
    set_event_queue,
    triage_agent,
)

logger = logging.getLogger(__name__)

# ─── 常量 ────────────────────────────────────────────────────────────────────

AGENT_MAP: dict[str, Agent[WorkbenchDeps, str]] = {
    "triage": triage_agent,
    "case": case_agent,
    "contract": contract_agent,
    "research": research_agent,
    "general": general_agent,
}

# 对话历史管理
MAX_HISTORY_TOKENS = 10000  # 历史消息最大 token 数
MAX_HISTORY_MESSAGES = 100  # 最多加载的消息条数
SUMMARY_THRESHOLD = 30  # 超过 N 条消息触发自动摘要

# Token 用量限制
USAGE_LIMITS = UsageLimits(
    request_limit=50,  # 单次运行最多 50 次 LLM 请求
    total_tokens_limit=100_000,  # 单次运行最多 10 万 token
    output_tokens_limit=30_000,  # 输出最多 3 万 token
)


# ─── Token 估算 ──────────────────────────────────────────────────────────────


def _estimate_tokens(text: str) -> int:
    """估算文本的 token 数量

    中文约 1-2 token/字，英文约 0.25 token/字符。
    使用保守估算：中文 1.5 token/字，英文 0.3 token/字符。
    """
    if not text:
        return 0

    chinese_chars = 0
    other_chars = 0
    for ch in text:
        if "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿":
            chinese_chars += 1
        else:
            other_chars += 1

    return max(1, int(chinese_chars * 1.5 + other_chars * 0.3))


# ─── 历史消息加载 ────────────────────────────────────────────────────────────


async def _load_message_history(
    session_id: int,
    max_tokens: int = MAX_HISTORY_TOKENS,
    max_messages: int = MAX_HISTORY_MESSAGES,
) -> list[ModelMessage]:
    """从数据库加载历史消息，转换为 Pydantic AI ModelMessage 格式

    使用滑动窗口策略：从最新消息向前加载，直到达到 token 上限。
    """
    from ..models import WorkbenchMessage

    # 从最新消息向前加载（含工具调用结果）
    messages_qs = WorkbenchMessage.objects.filter(
        session_id=session_id,
        role__in=[WorkbenchMessage.Role.USER, WorkbenchMessage.Role.ASSISTANT, WorkbenchMessage.Role.TOOL],
    ).order_by("-created_at")[:max_messages]

    raw_messages = list(reversed(await _async_list(messages_qs)))

    if not raw_messages:
        return []

    # 滑动窗口：从后向前累积 token
    result: list[WorkbenchMessage] = []
    total_tokens = 0

    for msg in reversed(raw_messages):
        msg_tokens = _estimate_tokens(msg.content)
        if total_tokens + msg_tokens > max_tokens and result:
            break
        result.insert(0, msg)
        total_tokens += msg_tokens

    # 转换为 ModelMessage
    return _convert_to_model_messages(result)


async def _async_list(queryset: Any) -> list[Any]:
    """异步遍历 QuerySet"""
    return [item async for item in queryset]


def _convert_to_model_messages(messages: list[Any]) -> list[ModelMessage]:
    """将数据库消息转换为 Pydantic AI ModelMessage"""
    result: list[ModelMessage] = []

    for msg in messages:
        if msg.role == "user":
            result.append(ModelRequest(parts=[UserPromptPart(content=msg.content)]))
        elif msg.role == "assistant":
            result.append(ModelResponse(parts=[TextPart(content=msg.content)]))
        elif msg.role == "tool":
            # 工具结果转为 ToolReturnPart，保持 tool_call_id 关联
            tool_output = msg.tool_output or {}
            result_text = tool_output.get("result", msg.content) if isinstance(tool_output, dict) else str(tool_output)
            result.append(
                ModelRequest(
                    parts=[
                        ToolReturnPart(
                            tool_call_id=msg.tool_call_id or "",
                            tool_name=msg.tool_name or "",
                            content=str(result_text),
                        )
                    ]
                )
            )

    return result


# ─── 自动摘要 ────────────────────────────────────────────────────────────────


async def _maybe_create_summary(
    session_id: int,
    current_count: int,
    model: Any,
) -> str | None:
    """如果消息数量超过阈值，自动生成对话摘要

    摘要存储在 session.metadata['conversation_summary'] 中。
    """
    if current_count < SUMMARY_THRESHOLD:
        return None

    from ..models import WorkbenchMessage, WorkbenchSession

    # 获取最近 20 条消息用于摘要
    recent = list(
        await _async_list(
            WorkbenchMessage.objects.filter(
                session_id=session_id,
                role__in=[WorkbenchMessage.Role.USER, WorkbenchMessage.Role.ASSISTANT],
            ).order_by("-created_at")[:20]
        )
    )
    recent.reverse()

    if not recent:
        return None

    # 构建摘要请求
    conversation_text = "\n".join(f"{'用户' if m.role == 'user' else '助手'}: {m.content[:200]}" for m in recent)

    summary_agent = Agent(
        model or "openai:gpt-4o-mini",
        instructions="请用 2-3 句话概括以下对话的要点，保留关键信息（案件编号、客户名称、具体需求等）。用中文回复。",
    )

    try:
        result = await summary_agent.run(
            f"请概括以下对话：\n\n{conversation_text}",
            usage_limits=UsageLimits(request_limit=1),
        )
        summary = result.output

        # 存储到 session metadata（merge 而非覆盖）
        session = await WorkbenchSession.objects.aget(id=session_id)
        meta = dict(session.metadata or {})
        meta["conversation_summary"] = summary
        await WorkbenchSession.objects.filter(id=session_id).aupdate(metadata=meta)

        return summary
    except Exception:
        logger.exception("生成对话摘要失败")
        return None


# ─── 主服务 ───────────────────────────────────────────────────────────────────


class WorkbenchChatService:
    """工作台对话编排服务"""

    def __init__(self) -> None:
        self.approval_manager = approval_manager

    def resolve_approval(self, approval_id: str, approved: bool, user_id: int | None = None) -> bool:
        """前端调用此方法来响应审批请求"""
        return self.approval_manager.resolve(approval_id, approved, user_id=user_id)

    # ── 主入口 ───────────────────────────────────────────────────────────

    async def stream_chat(
        self,
        session_id: int,
        user_message: str,
        llm_model: str = "",
        agent_type: str = "",
    ) -> AsyncIterator[dict[str, Any]]:
        """流式对话主入口

        Args:
            session_id: 会话 ID
            user_message: 用户消息
            llm_model: 指定模型（可选，覆盖会话默认）
            agent_type: Agent 类型（可选，默认 triage）

        Yields:
            SSE 事件字典
        """
        from ..models import WorkbenchMessage, WorkbenchSession

        start_time = time.perf_counter()

        # 获取会话
        try:
            session = await WorkbenchSession.objects.aget(id=session_id)
        except WorkbenchSession.DoesNotExist:
            yield {"type": "error", "message": "会话不存在"}
            return

        model_name = llm_model or session.llm_model or ""

        # 模型切换同步
        if llm_model and llm_model != session.llm_model:
            await WorkbenchSession.objects.filter(id=session_id).aupdate(llm_model=llm_model)
            session.llm_model = llm_model

        # 保存用户消息
        await WorkbenchMessage.objects.acreate(
            session_id=session_id,
            role=WorkbenchMessage.Role.USER,
            content=user_message,
        )

        # 选择 Agent
        agent = AGENT_MAP.get(agent_type, triage_agent)
        agent_display_name = agent.name or (agent_type or "triage")

        yield {"type": "meta", "session_id": str(session.session_id), "model": model_name, "agent": agent_display_name}
        yield {"type": "activity", "status": "thinking", "agent": agent_display_name}

        # 加载历史消息
        message_history = await _load_message_history(session_id)
        logger.info("加载 %d 条历史消息 (session=%d)", len(message_history), session_id)

        # 自动摘要（异步，不阻塞当前请求）
        summary_task = asyncio.create_task(_maybe_create_summary(session_id, len(message_history) + 1, model_name))

        # 获取已有的会话摘要
        conversation_summary = ""
        if session.metadata and "conversation_summary" in session.metadata:
            conversation_summary = session.metadata["conversation_summary"]

        # 构建依赖
        event_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        deps = WorkbenchDeps(
            session_id=session_id,
            user_id=session.user_id,
            llm_model=model_name,
            conversation_summary=conversation_summary,
        )

        # 设置审批事件队列（ContextVar，per-request 隔离）
        agent_name = agent_type or "triage"
        set_event_queue(event_queue, agent_name=agent_name, user_id=session.user_id)

        # 构建模型（LLMConfig 内部用同步 ORM，需 sync_to_async）
        model = await sync_to_async(build_model)(model_name) if model_name else None

        # 流式运行 Agent
        full_response: list[str] = []
        # tool_call_id -> WorkbenchMessage.id，用于关联 tool_result
        tool_msg_map: dict[str, int] = {}
        try:
            async for event in self._run_agent(
                agent=agent,
                user_message=user_message,
                model=model,
                deps=deps,
                event_queue=event_queue,
                message_history=message_history,
                agent_name=agent_name,
            ):
                if event["type"] == "delta":
                    full_response.append(event.get("content", ""))
                elif event["type"] == "tool_call":
                    # 持久化工具调用消息
                    tc_id = event.get("tool_call_id", "")
                    tool_msg = await WorkbenchMessage.objects.acreate(
                        session_id=session_id,
                        role=WorkbenchMessage.Role.TOOL,
                        content=f"调用工具: {event.get('name', '')}",
                        tool_call_id=tc_id,
                        tool_name=event.get("name", ""),
                        tool_input=event.get("arguments", {}),
                        tool_output={},
                    )
                    if tc_id:
                        tool_msg_map[tc_id] = tool_msg.id
                elif event["type"] == "tool_result":
                    # 更新工具结果
                    tc_id = event.get("tool_call_id", "")
                    msg_id = tool_msg_map.get(tc_id)
                    if msg_id:
                        result = event.get("result", "")
                        success = event.get("success", True)
                        await WorkbenchMessage.objects.filter(id=msg_id).aupdate(
                            content=f"工具 {event.get('name', '')}: {'成功' if success else '失败'}",
                            tool_output={"result": result, "success": success},
                            metadata={"success": success},
                        )
                yield event
        except Exception:
            logger.exception("Agent 运行失败")
            yield {"type": "error", "message": "Agent 运行失败，请稍后重试"}
        finally:
            set_event_queue(None)

        # 保存助手消息
        content = "".join(full_response)
        if content:
            duration_ms = (time.perf_counter() - start_time) * 1000
            await WorkbenchMessage.objects.acreate(
                session_id=session_id,
                role=WorkbenchMessage.Role.ASSISTANT,
                content=content,
                llm_model=model_name,
                metadata={
                    "duration_ms": round(duration_ms, 2),
                    "agent_type": agent_type or "triage",
                    "tokens": {
                        "prompt": deps.prompt_tokens,
                        "completion": deps.completion_tokens,
                        "total": deps.total_tokens,
                    },
                },
            )

        # 更新会话标题（如果是第一条消息）
        if not session.title:
            title = user_message[:50]
            await WorkbenchSession.objects.filter(id=session_id).aupdate(title=title)

        # 等待摘要任务完成（不阻塞响应）
        try:
            await asyncio.wait_for(summary_task, timeout=30)
        except (TimeoutError, Exception):
            summary_task.cancel()

        yield {"type": "done", "session_id": str(session.session_id)}

    # ── Agent 运行（并发事件流） ──────────────────────────────────────────

    async def _run_agent(
        self,
        agent: Agent[WorkbenchDeps, str],
        user_message: str,
        model: Any,
        deps: WorkbenchDeps,
        event_queue: asyncio.Queue[dict[str, Any] | None],
        message_history: list[ModelMessage] | None = None,
        agent_name: str = "triage",
    ) -> AsyncIterator[dict[str, Any]]:
        """运行 Agent 并流式输出 SSE 事件

        使用 asyncio.Queue 桥接：
        - Agent 任务：运行 agent.iter()，将工具事件推入队列
        - 主循环：从队列消费事件，yield 给 SSE 响应
        """

        # Agent 任务：推事件到队列
        async def agent_task() -> None:
            try:
                async with agent.iter(
                    user_message,
                    deps=deps,
                    model=model,
                    message_history=message_history,
                    usage_limits=USAGE_LIMITS,
                ) as run:
                    async for node in run:
                        if Agent.is_model_request_node(node):
                            # 流式收集文本和工具事件
                            stream: AgentStream[WorkbenchDeps, str]
                            async with node.stream(run.ctx) as stream:
                                async for event in stream:
                                    if isinstance(event, FunctionToolCallEvent):
                                        # 工具调用（执行前）
                                        args = event.part.args
                                        if isinstance(args, str):
                                            try:
                                                args = json.loads(args)
                                            except (json.JSONDecodeError, TypeError):
                                                pass
                                        tool_name = event.part.tool_name
                                        await event_queue.put(
                                            {
                                                "type": "tool_call",
                                                "tool_call_id": event.part.tool_call_id or "",
                                                "name": tool_name,
                                                "arguments": args,
                                            }
                                        )
                                        # 检测 handoff 工具调用
                                        if "handoff" in tool_name:
                                            target = tool_name.replace("_handoff_to_", "")
                                            await event_queue.put(
                                                {
                                                    "type": "handoff",
                                                    "from_agent": agent_name,
                                                    "to_agent": target,
                                                }
                                            )
                                    elif isinstance(event, FunctionToolResultEvent):
                                        # 工具结果
                                        result_content = event.content
                                        if hasattr(result_content, "content"):
                                            result_content = result_content.content
                                        result_str = str(result_content) if result_content else ""
                                        await event_queue.put(
                                            {
                                                "type": "tool_result",
                                                "tool_call_id": event.result.tool_call_id,
                                                "name": event.result.tool_name,
                                                "result": result_str[:2000],
                                            }
                                        )

                        elif Agent.is_call_tools_node(node):
                            # 工具执行节点：等待完成
                            async with node.stream(run.ctx) as _tool_stream:
                                async for _event in _tool_stream:
                                    pass

                        elif Agent.is_end_node(node):
                            # Agent 结束，发送最终文本
                            if run.result and run.result.output:
                                output = run.result.output
                                if isinstance(output, str) and output:
                                    await event_queue.put({"type": "delta", "content": output})

                            # 追踪 token 用量
                            if run.result and run.result.usage():
                                usage = run.result.usage()
                                deps.prompt_tokens = usage.input_tokens or 0
                                deps.completion_tokens = usage.output_tokens or 0
                                deps.total_tokens = usage.total_tokens or 0

            except Exception:
                logger.exception("Agent 任务异常")
                await event_queue.put({"type": "error", "message": "Agent 运行异常"})
            finally:
                # 发送结束哨兵
                await event_queue.put(None)

        # 启动 Agent 任务
        task = asyncio.create_task(agent_task())

        # 主循环：从队列消费事件
        try:
            while True:
                event = await event_queue.get()
                if event is None:
                    break
                yield event
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
