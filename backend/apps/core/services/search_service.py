"""全局搜索服务 — 跨实体关键词搜索。

安全（第4轮审计修复）：所有 search_* 均接受 user / org_access 并做行级过滤——
此前全库 icontains 查询，任意登录用户可用关键词 / 手机号 / 案号探询全库数据。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Q, QuerySet


@dataclass
class SearchResultItem:
    id: int
    title: str
    subtitle: str = ""
    # 仅当事人（clients）有值：ours=我方 / opposing=对方（取 Client.is_our_client）；其他类别为空串
    side: str = ""
    # 合同类型代码（contracts / cases 两类填充，对应 core.models.enums.CaseType）：
    # 前端按诉讼/非诉分流 /projects/:id 或 /projects/:id/nonlit
    case_type: str = ""
    # 仅 cases 填充：所属委托合同（= 项目）的 id 与名称——项目语义下案件挂在合同分组下
    contract_id: int | None = None
    contract_name: str = ""


def search_clients(
    q: str, limit: int, *, user: Any = None, org_access: dict[str, Any] | None = None
) -> list[SearchResultItem]:
    from apps.client.models import Client
    from apps.client.services.client_access_policy import ClientAccessPolicy

    # client 模块功能级权限：无 client.view_client 的用户不返回任何客户
    if not ClientAccessPolicy().has_perm(user, "client.view_client"):
        return []

    qs: QuerySet = (
        Client.objects.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(id_number__icontains=q))
        .order_by("-created_at", "-id")
        .distinct()[:limit]
    )
    # 电话原样出参（2026-10 产品决策，与证件号同口径：本机部署、办案要能直接看到联系方式；
    # 此前审计加的打码连座机都整串变星号，已撤除）
    return [
        SearchResultItem(
            id=c.id,
            title=c.name,
            subtitle=c.phone or "",
            side="ours" if c.is_our_client else "opposing",
        )
        for c in qs
    ]


def search_cases(
    q: str, limit: int, *, user: Any = None, org_access: dict[str, Any] | None = None
) -> list[SearchResultItem]:
    from apps.cases.models import Case
    from apps.cases.services.case.case_access_policy import CaseAccessPolicy

    qs: QuerySet = Case.objects.filter(
        Q(name__icontains=q) | Q(case_numbers__number__icontains=q) | Q(parties__client__name__icontains=q)
    )
    # 行级归属过滤：律师只能搜到本人/团队被分配或显式授权的案件
    qs = CaseAccessPolicy().filter_queryset(qs, user, org_access)
    qs = (
        qs.prefetch_related("case_numbers").select_related("contract").order_by("-created_at", "-id").distinct()[:limit]
    )
    results: list[SearchResultItem] = []
    for c in qs:
        case_number = ""
        numbers = list(c.case_numbers.all())
        if numbers:
            case_number = numbers[0].number
        results.append(
            SearchResultItem(
                id=c.id,
                title=c.name or "",
                subtitle=case_number,
                # 案件挂在委托合同（项目）下：带上合同 id/名称/类型，前端按项目分组并跳合同详情页
                contract_id=c.contract_id,
                contract_name=(c.contract.name or "") if c.contract else "",
                case_type=c.contract.case_type if c.contract else "",
            )
        )
    return results


def search_contracts(
    q: str, limit: int, *, user: Any = None, org_access: dict[str, Any] | None = None
) -> list[SearchResultItem]:
    from apps.contracts.models import Contract
    from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy

    qs: QuerySet = Contract.objects.filter(Q(name__icontains=q) | Q(contract_parties__client__name__icontains=q))
    # 行级归属过滤：与合同列表同口径
    qs = ContractAccessPolicy().filter_queryset(qs, user, org_access)
    qs = qs.order_by("-created_at", "-id").distinct()[:limit]
    # case_type 供前端判诉讼/非诉并分流 /projects/:id 或 /projects/:id/nonlit
    return [SearchResultItem(id=c.id, title=c.name or "", subtitle="", case_type=c.case_type) for c in qs]


def search_inbox(q: str, limit: int) -> list[SearchResultItem]:
    from apps.message_hub.models import InboxMessage

    qs: QuerySet = InboxMessage.objects.filter(Q(subject__icontains=q) | Q(sender__icontains=q)).order_by(
        "-received_at"
    )[:limit]
    return [
        SearchResultItem(
            id=m.id,
            title=m.subject or "(无主题)",
            subtitle=m.sender or "",
        )
        for m in qs
    ]


def search_court_sms(
    q: str, limit: int, *, user: Any = None, org_access: dict[str, Any] | None = None
) -> list[SearchResultItem]:
    from apps.automation.models import CourtSMS
    from apps.cases.models import Case
    from apps.cases.services.case.case_access_policy import CaseAccessPolicy

    qs: QuerySet = CourtSMS.objects.filter(Q(content__icontains=q) | Q(case__name__icontains=q)).select_related("case")
    # 归属过滤：绑定了案件的短信按案件 ACL 过滤；未绑案件的公共短信保持全员可见。
    # 管理员短路（避免 case_id IN 全表子查询）。
    policy = CaseAccessPolicy()
    if not policy.is_superuser(user):
        accessible_case_ids = policy.filter_queryset(Case.objects.all(), user, org_access).values("id")
        qs = qs.filter(Q(case__isnull=True) | Q(case_id__in=accessible_case_ids))
    qs = qs.order_by("-received_at")[:limit]
    results: list[SearchResultItem] = []
    for sms in qs:
        preview = sms.content[:50] + ("..." if len(sms.content) > 50 else "")
        case_name = sms.case.name if sms.case else ""
        results.append(SearchResultItem(id=sms.id, title=preview, subtitle=case_name))
    return results


def search_contacts(
    q: str, limit: int, *, user: Any = None, org_access: dict[str, Any] | None = None
) -> list[SearchResultItem]:
    from apps.contacts.models import CaseContact
    from apps.core.security.admin_access import is_admin_user

    # contacts 模块为 admin-only 语义（参照 CaseContactService.ensure_admin）：
    # 非管理员不返回任何联系人
    if not is_admin_user(user):
        return []

    qs: QuerySet = (
        CaseContact.objects.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(authority__name__icontains=q))
        .select_related("authority")
        .distinct()[:limit]
    )
    results: list[SearchResultItem] = []
    for contact in qs:
        role_display = contact.get_role_display()
        authority_name = contact.authority.name if contact.authority else ""
        subtitle = f"{role_display} | {authority_name}" if authority_name else role_display
        results.append(SearchResultItem(id=contact.id, title=contact.name, subtitle=subtitle))
    return results
