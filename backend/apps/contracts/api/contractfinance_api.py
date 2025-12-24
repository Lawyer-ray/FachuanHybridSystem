"""
合同财务统计 API 层
符合三层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""
from typing import Optional
from ninja import Router
from django.utils.dateparse import parse_date

from ..schemas import FinanceStatsOut, FinanceStatsItem
from ..services.contract_finance_service import ContractFinanceService

router = Router()


def _get_finance_service() -> ContractFinanceService:
    """工厂函数：创建 ContractFinanceService 实例"""
    return ContractFinanceService()


@router.get("/finance/stats", response=FinanceStatsOut)
def finance_stats(
    request,
    contract_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """
    获取财务统计数据
    
    API 层职责：
    1. 接收请求参数
    2. 解析日期参数
    3. 调用 Service 层方法
    4. 返回响应
    """
    service = _get_finance_service()
    
    # 解析日期参数
    d1 = parse_date(start_date) if start_date else None
    d2 = parse_date(end_date) if end_date else None
    
    # 调用 Service 层
    result = service.get_finance_stats(
        contract_id=contract_id,
        start_date=d1,
        end_date=d2,
    )
    
    # 转换为 Schema
    items = [
        FinanceStatsItem(
            contract_id=item["contract_id"],
            total_received=item["total_received"],
            total_invoiced=item["total_invoiced"],
            unpaid_amount=item["unpaid_amount"],
        )
        for item in result["items"]
    ]
    
    return FinanceStatsOut(
        items=items,
        total_received_all=result["total_received_all"],
        total_invoiced_all=result["total_invoiced_all"],
    )
