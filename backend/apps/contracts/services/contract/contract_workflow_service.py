"""Business workflow orchestration."""

from typing import TYPE_CHECKING, Any, cast

from django.db import transaction

from apps.contracts.models import Contract
from apps.core.exceptions import ValidationException

if TYPE_CHECKING:
    from apps.contracts.services.assignment.lawyer_assignment_service import LawyerAssignmentService
    from apps.contracts.services.payment.contract_finance_mutation_service import ContractFinanceMutationService
    from apps.contracts.services.supplementary.supplementary_agreement_service import SupplementaryAgreementService
    from apps.core.protocols import ICaseService

    from .mutation import ContractMutationService


class ContractWorkflowService:
    def __init__(
        self,
        *,
        mutation_service: "ContractMutationService",
        supplementary_agreement_service: "SupplementaryAgreementService",
        finance_mutation_service: "ContractFinanceMutationService",
        lawyer_assignment_service: "LawyerAssignmentService",
        case_service: "ICaseService",
    ) -> None:
        self.mutation_service = mutation_service
        self.supplementary_agreement_service = supplementary_agreement_service
        self.finance_mutation_service = finance_mutation_service
        self.lawyer_assignment_service = lawyer_assignment_service
        self.case_service = case_service

    @transaction.atomic
    def create_contract_with_cases(
        self,
        contract_data: dict[str, Any],
        cases_data: list[dict[str, Any]] | None = None,
        assigned_lawyer_ids: list[int] | None = None,
        payments_data: list[dict[str, Any]] | None = None,
        confirm_finance: bool = False,
        user: Any | None = None,
    ) -> Contract:
        if payments_data and not confirm_finance:
            raise ValidationException("关键财务操作需二次确认")

        supplementary_agreements_data = contract_data.pop("supplementary_agreements", None)

        lawyer_ids = contract_data.get("lawyer_ids") or assigned_lawyer_ids
        if lawyer_ids:
            contract_data["lawyer_ids"] = lawyer_ids

        contract = self.mutation_service.create_contract(contract_data)

        if supplementary_agreements_data:
            for sa_data in supplementary_agreements_data:
                self.supplementary_agreement_service.create_supplementary_agreement(
                    contract_id=cast(Any, contract).id, name=sa_data.get("name"), party_ids=sa_data.get("party_ids")
                )

        if payments_data:
            self.finance_mutation_service.add_payments(
                contract_id=cast(Any, contract).id,
                payments_data=payments_data,
                user=user,
                confirm=True,
            )

        if cases_data:
            all_lawyers = self.lawyer_assignment_service.get_all_lawyers(contract.id)
            all_lawyer_ids = [cast(Any, lawyer).id for lawyer in all_lawyers]

            for case_data in cases_data:
                case_create_data = {
                    "name": case_data.get("name"),
                    "contract_id": cast(Any, contract).id,
                    "is_archived": case_data.get("is_archived", False),
                    "case_type": case_data.get("case_type"),
                    "target_amount": case_data.get("target_amount"),
                }
                case_dto = self.case_service.create_case(case_create_data, user=user)

                for lawyer_id in all_lawyer_ids:
                    self.case_service.create_case_assignment(case_dto.id, lawyer_id)

                parties = case_data.get("parties", [])
                for party_data in parties:
                    self.case_service.create_case_party(
                        case_id=case_dto.id,
                        client_id=party_data.get("client_id"),
                        legal_status=party_data.get("legal_status"),
                    )

        return contract
