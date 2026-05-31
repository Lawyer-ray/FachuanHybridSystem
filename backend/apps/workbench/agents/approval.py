"""工作台工具审批管理器

通过 MCP process_tool_call 回调拦截高风险工具调用，
将审批请求推入 SSE 事件队列，等待前端通过 /approval API 响应。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)

# 需要用户审批的高风险工具
HIGH_RISK_TOOLS: frozenset[str] = frozenset(
    {
        "delete_case",
        "delete_client",
        "delete_contract",
        "send_document",
        "file_lawsuit",
        "submit_court_document",
    }
)

class ApprovalManager:
    """管理高风险工具的审批流程"""

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}
        self._results: dict[str, bool] = {}
        self._user_ids: dict[str, int] = {}

    def resolve(self, approval_id: str, approved: bool, user_id: int | None = None) -> bool:
        """API 层调用：响应审批请求

        Args:
            approval_id: 审批 ID
            approved: 是否批准
            user_id: 响应用户 ID（校验必须是发起审批的同一用户）
        """
        if approval_id not in self._events:
            return False
        # 校验用户身份
        if user_id is not None:
            expected_user = self._user_ids.get(approval_id)
            if expected_user is not None and expected_user != user_id:
                logger.warning("审批用户不匹配: expected=%s, got=%s", expected_user, user_id)
                return False
        self._results[approval_id] = approved
        self._events[approval_id].set()
        return True

    async def wait_for_approval(self, approval_id: str, user_id: int | None = None, timeout: float = 300) -> bool:
        """等待审批响应"""
        event = asyncio.Event()
        self._events[approval_id] = event
        self._results[approval_id] = False
        if user_id is not None:
            self._user_ids[approval_id] = user_id

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._results.get(approval_id, False)
        except TimeoutError:
            logger.warning("审批超时: %s", approval_id)
            return False
        finally:
            self._events.pop(approval_id, None)
            self._results.pop(approval_id, None)
            self._user_ids.pop(approval_id, None)

# 模块级单例
approval_manager = ApprovalManager()

async def process_tool_call_with_approval(
    ctx: Any,
    call_tool: Any,
    name: str,
    tool_args: dict[str, Any],
    event_queue: asyncio.Queue[dict[str, Any] | None],
    user_id: int | None = None,
) -> Any:
    """MCP process_tool_call 回调：拦截高风险工具，推入审批事件

    Args:
        ctx: MCP 上下文（未使用）
        call_tool: 实际执行工具的回调
        name: 工具名
        tool_args: 工具参数
        event_queue: SSE 事件队列
        user_id: 发起请求的用户 ID
    """
    if name not in HIGH_RISK_TOOLS:
        return await call_tool(name, tool_args)

    # 推送审批请求事件到队列
    approval_id = uuid.uuid4().hex[:12]
    await event_queue.put(
        {
            "type": "approval_request",
            "approval_id": approval_id,
            "tool_name": name,
            "tool_args": tool_args,
            "message": f"即将执行高风险操作：{name}，请确认是否继续",
        }
    )

    # 等待审批响应（绑定用户）
    approved = await approval_manager.wait_for_approval(approval_id, user_id=user_id, timeout=300)
    if not approved:
        return {"error": "用户拒绝执行此操作", "user_denied": True}

    # 审批通过，执行工具
    return await call_tool(name, tool_args)
