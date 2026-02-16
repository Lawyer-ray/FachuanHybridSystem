"""
合同进度计算服务层
处理合同履行进度和开票汇总的计算逻辑
"""

from decimal import Decimal
from typing import Any

from django.db.models import Sum

from apps.contracts.models import Contract, ContractPayment, FeeMode
from apps.core.exceptions import NotFoundError


class ContractProgressService:
    """
    合同进度计算服务

    职责:
    - 计算收款进度(已收/应收)
    - 计算开票汇总(已开票/未开票)
    """

    def __init__(self) -> None:
        """构造函数,预留依赖注入扩展"""

    def _get_contract(self, contract_id: int) -> Contract:
        """
        获取合同

        Args:
            contract_id: 合同 ID

        Returns:
            合同对象

        Raises:
            NotFoundError: 合同不存在
        """
        try:
            return Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(f"合同 {contract_id} 不存在") from None

    def _get_payment_totals(self, contract_id: int) -> dict[str, Decimal]:
        """
        获取收款汇总数据

        Args:
            contract_id: 合同 ID

        Returns:
            包含 total_amount 和 invoiced_amount 的字典
        """
        result = ContractPayment.objects.filter(contract_id=contract_id).aggregate(
            total_amount=Sum("amount"),
            invoiced_amount=Sum("invoiced_amount"),
        )
        return {
            "total_amount": Decimal(str(result["total_amount"] or 0)),
            "invoiced_amount": Decimal(str(result["invoiced_amount"] or 0)),
        }

    def get_payment_progress(self, contract: Contract) -> dict[str, Any]:
        """
        计算收款进度

        对于固定收费模式:进度 = 已收金额 / 固定金额 * 100
        对于半风险模式:进度 = 已收金额 / 前期律师费 * 100
        对于全风险/自定义模式:无固定应收金额,进度显示为 None

        Args:
            contract: 合同对象

        Returns:
            {
                'total_amount': Decimal,      # 应收总额(固定金额或前期律师费)
                'received_amount': Decimal,   # 已收金额
                'progress_percent': int,      # 进度百分比 (0-100),无法计算时为 None
                'is_completed': bool          # 是否已收齐
            }
        """
        # 获取已收款金额
        totals = self._get_payment_totals(contract.id)
        received_amount = totals["total_amount"]

        # 确定应收总额
        total_amount = None
        if contract.fee_mode in (FeeMode.FIXED, FeeMode.SEMI_RISK):
            total_amount = contract.fixed_amount

        # 计算进度百分比
        progress_percent = None
        is_completed = False

        if total_amount is not None and total_amount > 0:
            # 计算百分比,限制在 0-100 范围内
            percent = (received_amount / total_amount) * 100
            progress_percent = min(100, max(0, int(percent)))
            is_completed = received_amount >= total_amount

        return {
            "total_amount": total_amount,
            "received_amount": received_amount,
            "progress_percent": progress_percent,
            "is_completed": is_completed,
        }

    def get_invoice_summary(self, contract: Contract) -> dict[str, Any]:
        """
        计算开票汇总

        已开票金额 = sum(payments.invoiced_amount)
        未开票金额 = sum(payments.amount) - sum(payments.invoiced_amount)
        开票进度 = 已开票金额 / sum(payments.amount) * 100

        Args:
            contract: 合同对象

        Returns:
            {
                'total_received': Decimal,    # 累计收款
                'invoiced_amount': Decimal,   # 已开票金额
                'uninvoiced_amount': Decimal, # 未开票金额
                'invoice_percent': int,       # 开票进度百分比 (0-100)
                'has_pending': bool           # 是否有待开票
            }
        """
        # 获取汇总数据
        totals = self._get_payment_totals(contract.id)
        total_received = totals["total_amount"]
        invoiced_amount = totals["invoiced_amount"]

        # 计算未开票金额
        uninvoiced_amount = total_received - invoiced_amount

        # 计算开票进度百分比
        invoice_percent = 0
        if total_received > 0:
            percent = (invoiced_amount / total_received) * 100
            invoice_percent = min(100, max(0, int(percent)))

        # 判断是否有待开票
        has_pending = uninvoiced_amount > 0

        return {
            "total_received": total_received,
            "invoiced_amount": invoiced_amount,
            "uninvoiced_amount": uninvoiced_amount,
            "invoice_percent": invoice_percent,
            "has_pending": has_pending,
        }
