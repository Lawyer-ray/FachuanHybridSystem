"""客户关联案件/合同查询适配器。

跨模块（cases / contracts）的 Model 与访问策略依赖收敛在此适配器内，
client Service 层只依赖 RelatedItemsPort。
"""

from __future__ import annotations

from typing import Any


class RelatedItemsAdapter:
    """关联案件/合同查询适配器。"""

    def get_related_items(self, *, client_id: int, user: Any | None) -> dict[str, list[dict[str, Any]]]:
        from apps.cases.models import Case, CaseParty
        from apps.cases.services.case.case_access_policy import CaseAccessPolicy
        from apps.contracts.models import Contract, ContractParty
        from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy

        case_parties = (
            CaseParty.objects.filter(client_id=client_id).select_related("case").order_by("-case__start_date")
        )
        contract_parties = (
            ContractParty.objects.filter(client_id=client_id)
            .select_related("contract")
            .order_by("-contract__specified_date")
        )

        # 只回查询用户有权访问的案件/合同（与 cases/contracts 列表口径一致）。
        # 用 values("id") 子查询而非物化 Python set：后者会把该用户全部可见 ID
        # 拉进内存再生成大 IN 列表，千级案件时每详情请求多拉千级 int；
        # 子查询交给 PG 一次执行（同款写法见 search_service 的 court_sms 路径）。
        if user is not None:
            visible_cases = CaseAccessPolicy().filter_queryset(Case.objects.all(), user, None).values("id")
            visible_contracts = ContractAccessPolicy().filter_queryset(Contract.objects.all(), user, None).values("id")
            case_parties = case_parties.filter(case_id__in=visible_cases)
            contract_parties = contract_parties.filter(contract_id__in=visible_contracts)

        cases = [
            {
                "id": cp.case.id,
                "name": cp.case.name,
                "case_type": cp.case.case_type,
                "status": cp.case.get_status_display() if cp.case.status else None,
                "current_stage": cp.case.get_current_stage_display() if cp.case.current_stage else None,
                "legal_status": cp.legal_status,
            }
            for cp in case_parties
        ]
        contracts = [
            {
                "id": cp.contract.id,
                "name": cp.contract.name,
                "case_type": cp.contract.case_type,
                "status": cp.contract.get_status_display() if cp.contract.status else None,
                "role": cp.role,
            }
            for cp in contract_parties
        ]

        return {"cases": cases, "contracts": contracts}
