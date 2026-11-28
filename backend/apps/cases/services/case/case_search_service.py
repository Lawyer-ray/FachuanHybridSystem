"""Business logic services."""

from __future__ import annotations

from typing import Any

from django.db.models import Case as DjangoCase
from django.db.models import IntegerField, Q, QuerySet, Value, When

from apps.cases.models import Case, CaseNumber, CaseStatus
from apps.cases.utils import normalize_case_number as normalize_case_number_util
from apps.core.security.access_context import AccessContext

from .case_access_policy import CaseAccessPolicy
from .case_queryset import get_case_queryset

# 「待立案优先」的排序键白名单。sort 来自前端生成物的自由字符串，未知值一律按
# 「没传」处理（退回历史默认 -id），不认识的排序值不该让整页 400。
FILABLE_FIRST_SORT = "filable_first"


def normalize_case_number(number: str) -> str:
    return normalize_case_number_util(number, ensure_hao=True)


def _apply_search(qs: QuerySet[Case, Case], search: str | None) -> QuerySet[Case, Case]:
    """关键词过滤：name 或 cause_of_action 含关键词（icontains = 大小写不敏感）。

    只碰 Case 自身的两个字段、不跨表，因此不加 distinct——没有 JOIN 时 distinct
    只会白搭一次排序/子查询。空关键词等于没传（保持历史行为）。
    """
    keyword = (search or "").strip()
    if not keyword:
        return qs
    return qs.filter(Q(name__icontains=keyword) | Q(cause_of_action__icontains=keyword))


def _apply_sort(qs: QuerySet[Case, Case], sort: str | None) -> QuerySet[Case, Case]:
    """排序；sort 不在白名单内（含不传）时保持历史默认 ``-id``。

    sort=filable_first（待立案优先）：可立案 = 无案号且 status=active。用
    annotate + CASE/WHEN 算 0/1 排序键，而不是 ``order_by(F(...))``——这个谓词是
    「status 与案号」的合取，且案号要同时覆盖 NULL 与 ''（模型 save 只保证新数据
    存 NULL，历史数据可能有空串），两个 F() 键拼不出「同组内仍按 id DESC」的语义。
    生成的 SQL：
        CASE WHEN (status = 'active' AND (filing_number IS NULL OR filing_number = ''))
             THEN 0 ELSE 1 END ASC, id DESC
    """
    if sort != FILABLE_FIRST_SORT:
        return qs.order_by("-id")
    filable = Q(status=CaseStatus.ACTIVE) & (Q(filing_number__isnull=True) | Q(filing_number=""))
    return qs.annotate(
        _filable_rank=DjangoCase(When(filable, then=Value(0)), default=Value(1), output_field=IntegerField())
    ).order_by("_filable_rank", "-id")


class CaseSearchService:
    def __init__(self, access_policy: CaseAccessPolicy | None = None) -> None:
        self.access_policy = access_policy or CaseAccessPolicy()

    def search_by_case_number(
        self,
        case_number: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        exact_match: bool = False,
        slim: bool = False,
    ) -> QuerySet[Case, Case]:
        normalized = normalize_case_number(case_number)
        if not normalized:
            return Case.objects.none()

        if exact_match:
            case_ids = CaseNumber.objects.filter(number=normalized).values_list("case_id", flat=True)
        else:
            search_term = normalized.rstrip("号")
            case_ids = CaseNumber.objects.filter(number__icontains=search_term).values_list("case_id", flat=True)

        qs = get_case_queryset(slim=slim).filter(id__in=case_ids)
        return self.access_policy.filter_queryset(
            qs, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    def search_by_case_number_ctx(
        self, *, ctx: AccessContext, case_number: str, exact_match: bool = False
    ) -> QuerySet[Case, Case]:
        return self.search_by_case_number(
            case_number=case_number,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
            exact_match=exact_match,
        )

    def search_cases(
        self,
        query: str,
        limit: int = 10,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        offset: int = 0,
    ) -> list[Case]:
        if not query or not query.strip():
            return []

        query_value = query.strip()
        qs = get_case_queryset()

        search_conditions = Q()

        normalized_query = normalize_case_number(query_value)
        if normalized_query:
            search_term = normalized_query.rstrip("号")
            case_ids_by_number = CaseNumber.objects.filter(number__icontains=search_term).values_list(
                "case_id", flat=True
            )
            search_conditions |= Q(id__in=case_ids_by_number)

        search_conditions |= Q(name__icontains=query_value)
        search_conditions |= Q(parties__client__name__icontains=query_value)

        qs = qs.filter(search_conditions).distinct()

        qs = self.access_policy.filter_queryset(qs, user=user, org_access=org_access, perm_open_access=perm_open_access)
        bounded_offset = max(0, offset)
        return list(qs[bounded_offset : bounded_offset + limit])

    def search_cases_ctx(self, *, ctx: AccessContext, query: str, limit: int = 10) -> list[Case]:
        return self.search_cases(
            query=query,
            limit=limit,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def list_cases(
        self,
        case_type: str | None = None,
        status: str | None = None,
        contract_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        slim: bool = False,
        search: str | None = None,
        sort: str | None = None,
    ) -> QuerySet[Case, Case]:
        """获取案件列表（带权限过滤）。

        search / sort 是可选增量：不传时过滤结果与顺序与历史逐条一致（``-id``）。
        两个参数都在这里落地（而不是 API 层），因为 count_cases 复用的就是本条
        查询链——过滤/排序一旦分家，X-Total-Count 就会和分页对不上。
        """
        qs = get_case_queryset(slim=slim)

        # status/case_type 是 Case 自身字段（与 Contract 同名但语义独立），
        # 按 contract__ 过滤会丢掉无合同关联的案件，这里直接过滤 Case 字段
        if case_type:
            qs = qs.filter(case_type=case_type)
        if status:
            qs = qs.filter(status=status)
        if contract_id is not None:
            qs = qs.filter(contract_id=contract_id)

        qs = _apply_sort(_apply_search(qs, search), sort)

        return self.access_policy.filter_queryset(
            qs, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    def count_cases(
        self,
        case_type: str | None = None,
        status: str | None = None,
        contract_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        search: str | None = None,
        sort: str | None = None,
    ) -> int:
        """与 list_cases **同一套过滤 + 可见性口径**的总数（与 limit/offset 无关）。

        专供端点回 X-Total-Count：口径必须和列表本身逐条对齐（同一个 list_cases
        再 .count()），否则「列表 3 条、总数 4」这种对不上的数比没有总数更坏。
        这里用不到预取，故不传 slim（prefetch 不影响 count 的 SQL）。
        search 必须透传，否则翻页时总数恒为全集；sort 对 count 无影响，同样透传
        只为让「过滤 → 计数」只有一条路径（这里少传一个参数就多一种走偏的写法）。
        """
        return self.list_cases(
            case_type=case_type,
            status=status,
            contract_id=contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            search=search,
            sort=sort,
        ).count()

    def count_cases_by_case_number(
        self,
        case_number: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> int:
        """与 search_by_case_number 同口径的总数（端点走案号分支时用它）。"""
        return self.search_by_case_number(
            case_number=case_number,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        ).count()

    def list_cases_ctx(
        self,
        *,
        ctx: AccessContext,
        case_type: str | None = None,
        status: str | None = None,
        contract_id: int | None = None,
    ) -> QuerySet[Case, Case]:
        return self.list_cases(
            case_type=case_type,
            status=status,
            contract_id=contract_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
