"""Business workflow orchestration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dateutil.relativedelta import relativedelta

from apps.contracts.models import (
    Contract,
    ContractAssignment,
    ContractParty,
    SupplementaryAgreement,
    SupplementaryAgreementParty,
)


class ContractCloneWorkflow:
    def __init__(self, *, reminder_service: Any) -> None:
        self.reminder_service = reminder_service

    def clone_related_data(
        self,
        *,
        source_contract: Contract,
        target_contract: Contract,
        due_at_transform: Callable[[Any], Any] | None = None,
    ) -> None:
        ContractParty.objects.bulk_create(
            [
                ContractParty(
                    contract=target_contract,
                    client=party.client,
                    role=party.role,
                )
                for party in source_contract.contract_parties.all()
            ]
        )

        ContractAssignment.objects.bulk_create(
            [
                ContractAssignment(
                    contract=target_contract,
                    lawyer=assignment.lawyer,
                    is_primary=assignment.is_primary,
                    order=assignment.order,
                )
                for assignment in source_contract.assignments.all()
            ]
        )

        reminders = self.reminder_service.export_contract_reminders_internal(contract_id=source_contract.id)
        if due_at_transform is not None and reminders:
            reminders = [{**item, "due_at": due_at_transform(item.get("due_at"))} for item in reminders]

        if reminders:
            self.reminder_service.create_contract_reminders_internal(
                contract_id=target_contract.id,
                reminders=reminders,
            )

        agreements_data = [
            {"agreement": agreement, "parties": list(agreement.parties.all())}
            for agreement in source_contract.supplementary_agreements.all()
        ]
        if not agreements_data:
            return

        created_agreements = SupplementaryAgreement.objects.bulk_create(
            [
                SupplementaryAgreement(
                    contract=target_contract,
                    name=data["agreement"].name,  # type: ignore[attr-defined]
                )
                for data in agreements_data
            ]
        )

        SupplementaryAgreementParty.objects.bulk_create(
            [
                SupplementaryAgreementParty(
                    supplementary_agreement=new_agreement,
                    client=party.client,
                    role=party.role,
                )
                for new_agreement, data in zip(created_agreements, agreements_data, strict=False)
                for party in data["parties"]  # type: ignore[attr-defined]
            ]
        )



def plus_one_year_due_at(due_at: Any) -> Any:
    if not due_at:
        return None
    return due_at + relativedelta(years=1)
