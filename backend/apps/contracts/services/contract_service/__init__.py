"""
合同服务层
处理合同相关的业务逻辑
"""

from __future__ import annotations

from ._crud import ContractCrudMixin
from ._finance import ContractFinanceMixin
from ._parties import ContractPartiesMixin

__all__ = ["ContractService", "ContractServiceAdapter"]


class ContractService(ContractCrudMixin, ContractFinanceMixin, ContractPartiesMixin):
    """
    合同服务

    职责：
    1. 封装合同相关的所有业务逻辑
    2. 管理数据库事务
    3. 执行权限检查
    4. 协调多个 Model 操作
    5. 优化数据库查询
    """


# 向后兼容导出
from apps.contracts.services._contract_service_adapter import ContractServiceAdapter
