"""审批记录查询 —— 审计列表、待办发现（含僵尸 pending 懒清理）与合规导出。"""

from __future__ import annotations

import csv
import io
import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.core.utils.csv_safety import csv_safe_cell

from ...models import AgentApproval
from .risk import OFFLINE_TIMEOUT

#: 审批导出表头（合规方按这个顺序对数；改名等于改对外契约）。
APPROVAL_EXPORT_HEADER: tuple[str, ...] = (
    "approval_id",
    "created_at",
    "decided_at",
    "session_id",
    "run_id",
    "tool_name",
    "risk_level",
    "status",
    "decided_by",
    "tool_args",
    "request_reason",
    "decision_reason",
)

#: 单次导出条数上限。审批导出要落到律师本地、用 Excel 打开；不设上限时
#: 一次「全部导出」就是一个几百万行的 CSV。
EXPORT_MAX_ROWS = 10_000

#: ``tool_args`` 单元格最大字符数。参数里可能塞整份文书，不截断会让单行几 MB。
EXPORT_TOOL_ARGS_MAX_CHARS = 400


@dataclass(slots=True)
class ApprovalExportPage:
    """一次导出的结果。

    ``truncated`` 必须随响应告知调用方：静默截断的合规导出比不给更糟——
    拿到的人会以为「就这么多条」。
    """

    records: list[AgentApproval]
    truncated: bool


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


async def list_approvals_for_export(
    *,
    user: Any,
    days: int = 0,
    status: str | None = None,
    limit: int = EXPORT_MAX_ROWS,
) -> ApprovalExportPage:
    """导出用的审批记录（合规留痕）—— 权限与 :func:`list_approvals` 同口径。

    - 超级用户：全部记录；
    - 普通用户：只有自己会话的记录（``session.user_id == user.pk``）——
      越权时返回空集合，**不报 403**：403 本身就是「确实存在别人的审批」的泄露；
    - 未认证（``user is None``）：一条都不给，导出比列表更敏感，fail-closed。

    Args:
        days: ``> 0`` 时只看最近这些天；``0``（默认）不限时间——导出是合规用途，
            默认不该把更早的记录悄悄藏掉。
        status: ``AgentApproval.Status`` 的值（HTTP 层由参数校验拦非法值）；
            ``None`` 表示不过滤。直接调用时传未知值也不报错，按无匹配处理。
        limit: 条数上限，超过 ``EXPORT_MAX_ROWS`` 按上限。
    """
    if user is None:
        return ApprovalExportPage(records=[], truncated=False)
    queryset = AgentApproval.objects.select_related("session", "decided_by")
    if not getattr(user, "is_superuser", False):
        queryset = queryset.filter(session__user_id=user.pk)
    if days > 0:
        queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=days))
    if status:
        queryset = queryset.filter(status=status)
    cap = max(1, min(int(limit), EXPORT_MAX_ROWS))
    # 多取一条用于判断「是否还有第 cap+1 条」：只 count() 一次也行，但那会在
    # 大表上多跑一个聚合，而这里本来就要取数据。
    rows = [record async for record in queryset.order_by("-created_at")[: cap + 1]]
    return ApprovalExportPage(records=rows[:cap], truncated=len(rows) > cap)


def approval_export_csv(records: list[AgentApproval]) -> str:
    """把审批记录渲染成 CSV 文本（表头 + 每行一格一值）。

    - 逐格过 :func:`csv_safe_cell`：审批理由与工具参数都是**不可信文本**
      （模型写的参数、用户写的驳回理由），以 ``= + @ -`` 开头到了 Excel 里
      就是公式（DDE 可借此拉起外链命令）。导出是唯一把这类文本交给本地表格
      软件解析的路径，所以转义放在这里而不是调用方。
    - ``tool_args`` 是 JSON 串，超长截断：参数里可能塞整份文书。
    - 时间用本地时区 ISO 8601：跨时区/跨天核对时不会差 8 小时。
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(APPROVAL_EXPORT_HEADER)
    for record in records:
        writer.writerow([csv_safe_cell(cell) for cell in _export_cells(record)])
    return buffer.getvalue()


def _export_cells(record: AgentApproval) -> list[str]:
    """一行导出数据，列序与 :data:`APPROVAL_EXPORT_HEADER` 一一对应。"""
    return [
        str(record.approval_id),
        timezone.localtime(record.created_at).isoformat() if record.created_at else "",
        timezone.localtime(record.decided_at).isoformat() if record.decided_at else "",
        str(record.session.session_id) if record.session is not None else "",
        record.run_id,
        record.tool_name,
        record.risk_level,
        record.status,
        getattr(record.decided_by, "username", ""),
        _truncate(json.dumps(record.tool_args or {}, ensure_ascii=False), EXPORT_TOOL_ARGS_MAX_CHARS),
        record.reason,
        record.decision_reason,
    ]


def _truncate(text: str, limit: int) -> str:
    """截断并**留下痕迹**：审计看行时要知道这格不是原文。"""
    return text if len(text) <= limit else text[:limit] + "…(截断)"


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
