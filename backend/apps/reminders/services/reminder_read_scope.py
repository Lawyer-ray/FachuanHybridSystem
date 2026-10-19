"""提醒**读**范围过滤（安全审计 2026-10-19 抽取）。

`/api/v1/reminders/list` 在不带 contract_id/case_id/case_log_id 时此前直接返回全表——
任何登录用户可拿到全所提醒（含本人无权案件的绑定提醒）。本模块把
`calendar_month_service._scope_for_context` 的口径抽为模块级函数供两处复用：

- 关联案件（含经案件日志间接关联）→ CaseAccessPolicy 可见案件
- 关联合同 → ContractAccessPolicy 可见合同
- 未绑定任何目标的个人提醒 → 创建者本人（created_by FK，metadata.created_by_user_id
  为迁移回填前的历史兜底）或管理员可见

ctx 为 None（admin 后台等内部调用）或 perm_open_access 时不过滤，保持全量口径。
写权限判定在 ``reminder_access``，与本模块无关。
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from apps.core.security.admin_access import is_admin_user  # 解耦（2026-10-19）：管理员判定收敛 core
from apps.reminders.models import Reminder


def scope_reminders_for_context(qs: QuerySet[Reminder, Reminder], ctx: Any) -> QuerySet[Reminder, Reminder]:
    """按查询用户的可视范围过滤提醒 QuerySet（口径见模块 docstring）。"""
    if ctx is None or ctx.perm_open_access:
        return qs
    user = ctx.user
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()

    from apps.cases.models import Case
    from apps.cases.services.case.case_access_policy import CaseAccessPolicy
    from apps.contracts.models import Contract
    from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy

    case_ids = CaseAccessPolicy().filter_queryset(Case.objects.all(), user, ctx.org_access).values("id")
    contract_ids = ContractAccessPolicy().filter_queryset(Contract.objects.all(), user, ctx.org_access).values("id")

    visible = Q(case_id__in=case_ids) | Q(case_log__case_id__in=case_ids) | Q(contract_id__in=contract_ids)
    unbound = Q(contract__isnull=True, case__isnull=True, case_log__isnull=True)
    is_admin = is_admin_user(user)
    if is_admin:
        visible |= unbound
    else:
        visible |= unbound & (Q(created_by_id=user.id) | Q(metadata__created_by_user_id=user.id))

    return qs.filter(visible).distinct()
