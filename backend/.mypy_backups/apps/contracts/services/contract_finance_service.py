"""
合同财务统计服务层
处理合同财务统计相关的业务逻辑，符合三层架构规范
"""
from typing import Optional, List, Dict, Any
from datetime import date
from decimal import Decimal
from django.db.models import Sum

from ..models import Contract, ContractPayment


class ContractFinanceService:
    """
    合同财务统计服务
    
    职责：
    - 财务数据汇总统计
    - 收款/开票数据聚合
    """

    def __init__(self):
        """构造函数，预留依赖注入扩展"""
        pass

    def get_finance_stats(
        self,
        contract_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        获取财务统计数据
        
        Args:
            contract_id: 合同 ID（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            
        Returns:
            财务统计数据，包含：
            - items: 各合同的统计明细
            - total_received_all: 总收款金额
            - total_invoiced_all: 总开票金额
        """
        qs = ContractPayment.objects.all()
        
        # 应用筛选条件
        if contract_id:
            qs = qs.filter(contract_id=contract_id)
        if start_date:
            qs = qs.filter(received_at__gte=start_date)
        if end_date:
            qs = qs.filter(received_at__lte=end_date)
        
        # 按合同汇总
        totals = {}
        for p in qs.values("contract_id").annotate(
            total_received=Sum("amount"),
            total_invoiced=Sum("invoiced_amount")
        ):
            c_id = p["contract_id"]
            totals[c_id] = {
                "total_received": float(p["total_received"] or 0),
                "total_invoiced": float(p["total_invoiced"] or 0),
            }
        
        # 获取合同固定金额
        contract_ids = list(totals.keys())
        contracts = Contract.objects.filter(id__in=contract_ids) if contract_ids else Contract.objects.none()
        fixed_map = {
            c.id: float(c.fixed_amount) if c.fixed_amount is not None else None
            for c in contracts
        }
        
        # 构建统计明细
        items = []
        for cid, t in totals.items():
            fixed = fixed_map.get(cid)
            unpaid = None
            if fixed is not None:
                val = fixed - t["total_received"]
                unpaid = float(val) if val >= 0 else 0.0
            
            items.append({
                "contract_id": cid,
                "total_received": t["total_received"],
                "total_invoiced": t["total_invoiced"],
                "unpaid_amount": unpaid,
            })
        
        # 计算总计
        all_received = sum(i["total_received"] for i in items)
        all_invoiced = sum(i["total_invoiced"] for i in items)
        
        return {
            "items": items,
            "total_received_all": all_received,
            "total_invoiced_all": all_invoiced,
        }
