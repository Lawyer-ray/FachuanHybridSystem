"""合同 Admin 服务 - 处理 Admin 层的复杂业务逻辑"""
from typing import Optional
from django.db import transaction

from ..models import (
    Contract, ContractParty, ContractAssignment,
    ContractReminder, SupplementaryAgreement, SupplementaryAgreementParty
)
from apps.core.enums import CaseType


class ContractAdminService:
    """合同 Admin 服务"""

    @transaction.atomic
    def duplicate_contract(self, contract_id: int) -> Contract:
        """
        复制合同及其所有关联数据
        
        Args:
            contract_id: 原合同ID
            
        Returns:
            新创建的合同对象
        """
        # 获取原合同
        original = Contract.objects.get(pk=contract_id)
        
        # 复制主对象
        new_contract = Contract.objects.create(
            name=f"{original.name} (副本)",
            case_type=original.case_type,
            status=original.status,
            specified_date=original.specified_date,
            start_date=original.start_date,
            end_date=original.end_date,
            is_archived=False,  # 副本默认未建档
            fee_mode=original.fee_mode,
            fixed_amount=original.fixed_amount,
            risk_rate=original.risk_rate,
            custom_terms=original.custom_terms,
            representation_stages=original.representation_stages,
        )
        
        # 复制当事人
        for party in original.contract_parties.all():
            ContractParty.objects.create(
                contract=new_contract,
                client=party.client,
                role=party.role,
            )
        
        # 复制律师指派
        for assignment in original.assignments.all():
            ContractAssignment.objects.create(
                contract=new_contract,
                lawyer=assignment.lawyer,
                is_primary=assignment.is_primary,
                order=assignment.order,
            )
        
        # 复制提醒
        for reminder in original.reminders.all():
            ContractReminder.objects.create(
                contract=new_contract,
                kind=reminder.kind,
                content=reminder.content,
                due_date=reminder.due_date,
            )
        
        # 复制补充协议及其当事人
        for agreement in original.supplementary_agreements.all():
            new_agreement = SupplementaryAgreement.objects.create(
                contract=new_contract,
                name=agreement.name,
            )
            for party in agreement.parties.all():
                SupplementaryAgreementParty.objects.create(
                    supplementary_agreement=new_agreement,
                    client=party.client,
                    role=party.role,
                )
        
        return new_contract

    # 允许创建案件的合同类型
    CASE_ALLOWED_TYPES = {
        CaseType.CIVIL,
        CaseType.CRIMINAL,
        CaseType.ADMINISTRATIVE,
        CaseType.LABOR,
        CaseType.INTL,
    }

    def can_create_case(self, contract_id: int) -> bool:
        """检查合同是否可以创建案件"""
        contract = Contract.objects.filter(pk=contract_id).first()
        if not contract:
            return False
        return contract.case_type in self.CASE_ALLOWED_TYPES

    @transaction.atomic
    def create_case_from_contract(self, contract_id: int) -> "Case":
        """
        从合同创建案件
        
        Args:
            contract_id: 合同ID
            
        Returns:
            新创建的案件对象
        """
        from apps.cases.models import Case, CaseParty, CaseAssignment, SimpleCaseType
        
        contract = Contract.objects.get(pk=contract_id)
        
        # 检查合同类型是否允许创建案件
        if contract.case_type not in self.CASE_ALLOWED_TYPES:
            from apps.core.exceptions import ValidationException
            raise ValidationException(
                message="该合同类型不支持创建案件",
                code="INVALID_CONTRACT_TYPE",
                errors={"case_type": f"合同类型 {contract.get_case_type_display()} 不支持创建案件"}
            )
        
        # 映射合同类型到案件类型
        case_type_mapping = {
            CaseType.CIVIL: SimpleCaseType.CIVIL,
            CaseType.CRIMINAL: SimpleCaseType.CRIMINAL,
            CaseType.ADMINISTRATIVE: SimpleCaseType.ADMINISTRATIVE,
            CaseType.LABOR: SimpleCaseType.CIVIL,  # 劳动仲裁映射到民事
            CaseType.INTL: SimpleCaseType.CIVIL,   # 商事仲裁映射到民事
        }
        
        # 创建案件
        case = Case.objects.create(
            contract=contract,
            name=f"{contract.name} - 案件",
            case_type=case_type_mapping.get(contract.case_type, SimpleCaseType.CIVIL),
            is_archived=False,
        )
        
        # 复制合同当事人到案件当事人
        for party in contract.contract_parties.all():
            CaseParty.objects.create(
                case=case,
                client=party.client,
                legal_status=None,  # 诉讼地位需要用户后续设置
            )
        
        # 复制合同律师指派到案件律师指派
        for assignment in contract.assignments.all():
            CaseAssignment.objects.create(
                case=case,
                lawyer=assignment.lawyer,
            )
        
        return case
