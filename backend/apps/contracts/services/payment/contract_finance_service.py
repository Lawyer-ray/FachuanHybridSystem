"""
合同财务统计服务层
处理合同财务统计相关的业务逻辑,符合三层架构规范
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Sum

from apps.contracts.models import Contract, ContractPayment


class ContractFinanceService:
    """
    合同财务统计服务

    职责:
    - 财务数据汇总统计
    - 收款/开票数据聚合
    """

    def get_finance_stats(
        self,
        contract_id: int | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        user: Any | None = None,
        perm_open_access: bool = False,
        org_access: dict[str, Any] | None = None,
    ) -> dict[str, Any]:  # pragma: no cover
        """
        获取财务统计数据

        Args:
            contract_id: 合同 ID(可选)
            start_date: 开始日期筛选(可选)
            end_date: 结束日期筛选(可选)
            user: 当前用户
            perm_open_access: 是否开放访问权限
            org_access: 组织访问上下文（用于合同访问范围过滤）

        Returns:
            财务统计数据,包含:
            - items: 各合同的统计明细
            - total_received_all: 总收款金额
            - total_invoiced_all: 总开票金额
        """
        qs = ContractPayment.objects.all()

        # 合同访问范围过滤（管理员见全量，普通律师仅统计自己可访问的合同）
        if not perm_open_access:
            from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy

            if not user or not getattr(user, "is_authenticated", False):
                qs = qs.none()
            else:
                policy = ContractAccessPolicy()
                accessible_ids = policy.filter_queryset(Contract.objects.all(), user, org_access).values_list(
                    "id", flat=True
                )
                qs = qs.filter(contract_id__in=accessible_ids)

        # 应用筛选条件
        if contract_id:
            qs = qs.filter(contract_id=contract_id)
        if start_date:
            qs = qs.filter(received_at__gte=start_date)
        if end_date:
            qs = qs.filter(received_at__lte=end_date)

        # 按合同汇总（金额全程 Decimal，出口统一转 float，避免浮点累加漂移）
        totals: dict[int, dict[str, Decimal]] = {}
        for p in qs.values("contract_id").annotate(total_received=Sum("amount"), total_invoiced=Sum("invoiced_amount")):
            totals[p["contract_id"]] = {
                "total_received": p["total_received"] or Decimal("0"),
                "total_invoiced": p["total_invoiced"] or Decimal("0"),
            }

        # 获取合同固定金额
        contract_ids = list(totals.keys())
        contracts = Contract.objects.filter(id__in=contract_ids) if contract_ids else Contract.objects.none()
        fixed_map = {c.id: c.fixed_amount for c in contracts}

        # 构建统计明细
        items: list[Any] = []
        for cid, t in totals.items():
            fixed = fixed_map.get(cid)
            unpaid = None
            if fixed is not None:
                val = fixed - t["total_received"]
                unpaid = float(val) if val >= 0 else 0.0

            items.append(
                {
                    "contract_id": cid,
                    "total_received": float(t["total_received"]),
                    "total_invoiced": float(t["total_invoiced"]),
                    "unpaid_amount": unpaid,
                }
            )

        # 计算总计（Decimal 求和后单次转换）
        all_received = float(sum((t["total_received"] for t in totals.values()), Decimal("0")))
        all_invoiced = float(sum((t["total_invoiced"] for t in totals.values()), Decimal("0")))

        return {
            "items": items,
            "total_received_all": all_received,
            "total_invoiced_all": all_invoiced,
        }
