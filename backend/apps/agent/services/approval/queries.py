"""审批记录查询 —— 审计列表与待办发现（含僵尸 pending 懒清理）。"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from django.utils import timezone

from ...models import AgentApproval
from .risk import OFFLINE_TIMEOUT


async def get_approval_for_decision(approval_id: str) -> AgentApproval | None:
    """取审批记录（含会话预取）供归属判定；无效 id 返回 None。"""
    try:
        normalized = approval_id.replace("-", "")
        return await AgentApproval.objects.select_related("session").filter(approval_id=uuid.UUID(normalized)).afirst()
    except (ValueError, AttributeError):
        return None


async def list_approvals(*, user: Any, limit: int) -> list[AgentApproval]:
    """审批记录列表（审计用；非超级用户仅见自己会话的记录）。"""
    queryset = AgentApproval.objects.all()
    if user is not None and not getattr(user, "is_superuser", False):
        queryset = queryset.filter(session__user_id=user.pk)
    return [record async for record in queryset[: max(1, min(limit, 200))]]


async def list_pending_for_user(*, user_id: int | None) -> list[AgentApproval]:
    """某人所有**仍待处理**的审批（离线审批用：用户回来看到待审批卡片）。

    只查 pending：已决/超时的不需要再打扰用户。按创建时间正序，
    先来的先处理（避免用户在处理一堆旧请求时又漏掉更急的）。

    **懒清理僵尸 pending**：等待审批的进程内 waiter 死亡时（worker 重启 /
    崩溃），记录会永远停在 pending——没人把它转成 timeout（差距分析 B2-4）。
    这里在列表时把超过最长可能等待窗口（OFFLINE_TIMEOUT，挂起等离线
    审批的上限）的 pending 批量转成 timeout：

    - 不会误杀活等待：任何在等的 waiter（在线 300/900s 或离线 7200s）
      最长也就等到 OFFLINE_TIMEOUT，超过它必是僵尸；
    - fail-closed 语义不变：被转 timeout 的记录等同拒绝，工具未执行。
    """
    if user_id is None:
        return []
    zombie_deadline = timezone.now() - timedelta(seconds=OFFLINE_TIMEOUT)
    await AgentApproval.objects.filter(
        status=AgentApproval.Status.PENDING,
        session__user_id=user_id,
        created_at__lt=zombie_deadline,
    ).aupdate(status=AgentApproval.Status.TIMEOUT, decided_at=timezone.now())
    queryset = AgentApproval.objects.filter(
        status=AgentApproval.Status.PENDING,
        session__user_id=user_id,
    ).select_related("session")
    results = []
    async for record in queryset.order_by("created_at")[:100]:
        results.append(record)
    return results
