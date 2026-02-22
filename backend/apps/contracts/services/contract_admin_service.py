"""合同 Admin 服务 - 处理 Admin 层的复杂业务逻辑（委托层）"""

from datetime import date
from typing import Any

from apps.contracts.models import Contract


class ContractAdminService:
    """合同 Admin 服务"""

    def renew_advisor_contract(self, contract_id: int) -> Contract:
        """续签常法顾问合同（委托给 ContractAdminMutationService）"""
        from apps.contracts.services.contract.contract_admin_mutation_service import ContractAdminMutationService
        return ContractAdminMutationService().renew_advisor_contract(contract_id)

    def generate_advisor_contract_name(self, principal_names: list[str], start_date: date, end_date: date) -> str:
        """生成常法顾问合同名称（委托给 ContractAdminMutationService）"""
        from apps.contracts.services.contract.contract_admin_mutation_service import ContractAdminMutationService
        return ContractAdminMutationService().generate_advisor_contract_name(principal_names, start_date, end_date)

    def duplicate_contract(self, contract_id: int) -> Contract:
        """复制合同及其所有关联数据（委托给 ContractAdminMutationService）"""
        from apps.contracts.services.contract.contract_admin_mutation_service import ContractAdminMutationService
        return ContractAdminMutationService().duplicate_contract(contract_id)

    def can_create_case(self, contract_id: int) -> bool:
        """检查合同是否可以创建案件（委托给 ContractAdminQueryService）"""
        from apps.contracts.services.contract.contract_admin_query_service import ContractAdminQueryService
        return ContractAdminQueryService().can_create_case(contract_id)

    def create_case_from_contract(self, contract_id: int) -> Any:
        """从合同创建案件（委托给 ContractAdminMutationService）"""
        from apps.contracts.services.contract.contract_admin_mutation_service import ContractAdminMutationService
        return ContractAdminMutationService().create_case_from_contract(contract_id=contract_id)
