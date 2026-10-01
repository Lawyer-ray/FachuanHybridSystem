"""Business logic services."""

from __future__ import annotations

from typing import Any, cast

from django.db.models import Count, F, IntegerField, OuterRef, QuerySet, Subquery, Sum
from django.db.models.expressions import RawSQL

from apps.cases.models import Case
from apps.contracts.models import Contract
from apps.core.exceptions import NotFoundError
from apps.core.security.access_context import AccessContext

from ..domain import ContractAccessPolicy


class ContractQueryService:
    def __init__(self, access_policy: ContractAccessPolicy | None = None) -> None:
        self._access_policy = access_policy

    @property
    def access_policy(self) -> ContractAccessPolicy:
        if self._access_policy is None:
            self._access_policy = ContractAccessPolicy()
        return self._access_policy

    def get_contract_queryset(self) -> QuerySet[Contract, Contract]:
        return (
            Contract.objects.prefetch_related(
                "contract_parties__client",
                "payments__invoices",
                "reminders",
                "assignments__lawyer",
                "assignments__lawyer__law_firm",
                "supplementary_agreements__parties__client",
                "finalized_materials",
                "client_payment_records",
            )
            # 用 DB 层聚合替代 ContractOut.resolve_total_received/invoiced 中的 Python 循环求和。
            # case_count 用相关子查询而非 Count("cases")：同一 annotate 链上再 join cases 会与
            # payments 的 Sum 互相放大（笛卡尔积），子查询各算各的互不干扰。
            .annotate(
                _total_received=Sum("payments__amount"),
                _total_invoiced=Sum("payments__invoiced_amount"),
                _case_count=Subquery(
                    Case.objects.filter(contract_id=OuterRef("pk"))
                    .values("contract_id")
                    .annotate(c=Count("pk"))
                    .values("c")[:1],
                    output_field=IntegerField(),
                ),
            )
        )

    def _apply_list_filters(
        self,
        qs: QuerySet[Contract, Contract],
        *,
        case_type: str | None,
        status: str | None,
        search: str | None,
        fee_mode: str | None,
        is_filed: bool | None,
    ) -> QuerySet[Contract, Contract]:
        if case_type:
            qs = qs.filter(case_type=case_type)
        if status:
            qs = qs.filter(status=status)
        if fee_mode:
            qs = qs.filter(fee_mode=fee_mode)
        if is_filed is not None:
            qs = qs.filter(is_filed=is_filed)
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    def list_contracts(
        self,
        case_type: str | None = None,
        status: str | None = None,
        search: str | None = None,
        fee_mode: str | None = None,
        is_filed: bool | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[Contract, Contract]:
        qs = self.get_contract_queryset().order_by("-id")
        qs = self._apply_list_filters(
            qs, case_type=case_type, status=status, search=search, fee_mode=fee_mode, is_filed=is_filed
        )

        qs = self.access_policy.filter_queryset(
            qs=qs,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        return qs

    def list_contracts_page(
        self,
        *,
        page: int,
        page_size: int,
        case_type: str | None = None,
        status: str | None = None,
        search: str | None = None,
        fee_mode: str | None = None,
        is_filed: bool | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        """分页列表（服务端分页，前端不再全量拉）。

        排序沿用办案主页口径「离今天最近」：|end_date - 今天| 升序、无到期沉底。
        facets 计数固定全库口径（与旧客户端筛选行为一致），三条 group by 很便宜。
        """
        qs = (
            self.get_contract_queryset()
            .annotate(_abs_days=RawSQL("ABS(end_date - CURRENT_DATE)", []))
            .order_by(F("_abs_days").asc(nulls_last=True), "-id")
        )
        qs = self._apply_list_filters(
            qs, case_type=case_type, status=status, search=search, fee_mode=fee_mode, is_filed=is_filed
        )
        qs = self.access_policy.filter_queryset(
            qs=qs,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        total = qs.count()
        offset = max(0, (page - 1)) * page_size
        items = list(qs[offset : offset + page_size])
        facets = self.contract_facets(user=user, org_access=org_access, perm_open_access=perm_open_access)
        return {"total": total, "items": items, **facets}

    def contract_facets(
        self,
        *,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        """筛选 chips 计数：状态（代码→数）/ 类目 / 收费（value+label+数，label 供展示、value 供过滤参数），全库口径。"""
        base = self.access_policy.filter_queryset(
            qs=Contract.objects.all(),
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

        def facet_list(field: str, label_of: Any) -> list[dict[str, Any]]:
            agg = dict(base.values_list(field).annotate(n=Count("id")))
            return [{"value": k, "label": label_of(k), "n": v} for k, v in sorted(agg.items()) if k]

        status_counts = {s or "": n for s, n in base.values_list("status").annotate(n=Count("id"))}
        cat_counts = facet_list("case_type", lambda c: Contract(case_type=c).get_case_type_display())
        fee_counts = facet_list("fee_mode", lambda f: Contract(fee_mode=f).get_fee_mode_display())
        return {"status_counts": status_counts, "cat_counts": cat_counts, "fee_counts": fee_counts}

    def list_contracts_ctx(
        self,
        *,
        ctx: AccessContext,
        case_type: str | None = None,
        status: str | None = None,
        search: str | None = None,
        fee_mode: str | None = None,
        is_filed: bool | None = None,
    ) -> QuerySet[Contract, Contract]:
        qs = self.get_contract_queryset().order_by("-id")
        qs = self._apply_list_filters(
            qs, case_type=case_type, status=status, search=search, fee_mode=fee_mode, is_filed=is_filed
        )

        qs = self.access_policy.filter_queryset_ctx(qs=qs, ctx=ctx)
        return qs

    def get_contract_internal(self, contract_id: int) -> Any:
        try:
            contract = self.get_contract_queryset().get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError("合同 %(id)s 不存在" % {"id": contract_id}) from None
        return contract

    def get_contract_with_details_model_internal(self, contract_id: int) -> Any:
        try:
            return (
                Contract.objects.prefetch_related(
                    "contract_parties__client",
                    "assignments__lawyer",
                    "assignments__lawyer__law_firm",
                    "cases__parties__client",
                    "cases__supervising_authorities",
                    "payments__invoices",
                    "reminders",
                    "supplementary_agreements__parties__client",
                    "finalized_materials",
                    "client_payment_records",
                )
                .annotate(
                    _total_received=Sum("payments__amount"),
                    _total_invoiced=Sum("payments__invoiced_amount"),
                )
                .get(pk=contract_id)
            )
        except Contract.DoesNotExist:
            return None
