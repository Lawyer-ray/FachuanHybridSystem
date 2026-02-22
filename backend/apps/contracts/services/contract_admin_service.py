"""合同 Admin 服务 - 处理 Admin 层的复杂业务逻辑"""

from datetime import date
from typing import Any, ClassVar

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core.enums import CaseType

from apps.contracts.models import (
    Contract,
    ContractAssignment,
    ContractParty,
    ContractReminder,
    SupplementaryAgreement,
    SupplementaryAgreementParty,
)


class ContractAdminService:
    """合同 Admin 服务"""

    def renew_advisor_contract(self, contract_id: int) -> Contract:
        """续签常法顾问合同（委托给 ContractAdminMutationService）"""
        from apps.contracts.services.contract.contract_admin_mutation_service import ContractAdminMutationService
        return ContractAdminMutationService().renew_advisor_contract(contract_id)

    @staticmethod
    def generate_advisor_contract_name(principal_names: list[str], start_date: date, end_date: date) -> str:
        """生成常法顾问合同名称"""
        principals_str = "、".join(principal_names)
        start_str = start_date.strftime("%Y年%m月%d日")
        end_str = end_date.strftime("%Y年%m月%d日")
        return f"{principals_str}常法顾问-{start_str}至{end_str}"

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
    CASE_ALLOWED_TYPES: ClassVar[set[CaseType]] = {
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
    def create_case_from_contract(self, contract_id: int) -> Any:
        """
        从合同创建案件

        Args:
            contract_id: 合同ID

        Returns:
            新创建的案件 DTO
        """
        from apps.core.enums import SimpleCaseType
        from apps.core.exceptions import ValidationException
        from apps.core.interfaces import ServiceLocator

        contract = Contract.objects.get(pk=contract_id)

        # 检查合同类型是否允许创建案件
        if contract.case_type not in self.CASE_ALLOWED_TYPES:
            raise ValidationException(
                message=_("该合同类型不支持创建案件"),
                code="INVALID_CONTRACT_TYPE",
                errors={"case_type": f"合同类型 {contract.get_case_type_display()} 不支持创建案件"},
            )

        # 映射合同类型到案件类型
        case_type_mapping: dict[CaseType, SimpleCaseType] = {
            CaseType.CIVIL: SimpleCaseType.CIVIL,
            CaseType.CRIMINAL: SimpleCaseType.CRIMINAL,
            CaseType.ADMINISTRATIVE: SimpleCaseType.ADMINISTRATIVE,
            CaseType.LABOR: SimpleCaseType.CIVIL,
            CaseType.INTL: SimpleCaseType.CIVIL,
        }
        case_type_key = CaseType(contract.case_type) if contract.case_type else CaseType.CIVIL
        case_type_value = case_type_mapping.get(case_type_key, SimpleCaseType.CIVIL)

        case_service = ServiceLocator.get_case_service()
        case_dto = case_service.create_case(
            data={
                "contract_id": contract_id,
                "name": f"{contract.name} - 案件",
                "case_type": case_type_value,
                "is_archived": False,
            }
        )

        # 复制合同当事人到案件当事人
        for party in contract.contract_parties.all():
            if party.client_id:
                case_service.create_case_party(
                    case_id=case_dto.id,
                    client_id=party.client_id,
                    legal_status=None,
                )

        # 复制合同律师指派到案件律师指派
        for assignment in contract.assignments.all():
            if assignment.lawyer_id:
                case_service.create_case_assignment(
                    case_id=case_dto.id,
                    lawyer_id=assignment.lawyer_id,
                )

        return case_dto
