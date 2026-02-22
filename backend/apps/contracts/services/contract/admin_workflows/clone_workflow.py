"""Business workflow orchestration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

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
                for party in cast(Any, source_contract.contract_parties).all()
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
                for assignment in cast(Any, source_contract.assignments).all()
            ]
        )

        reminders: list[dict[str, Any]] = []
        for reminder in cast(Any, source_contract.reminders).all():
            due_at = reminder.due_at
            if due_at_transform is not None:
                due_at = due_at_transform(due_at)
            reminders.append(
                {
                    "reminder_type": reminder.reminder_type,
                    "content": reminder.content,
                    "due_at": due_at,
                    "metadata": reminder.metadata,
                }
            )

        if reminders:
            self.reminder_service.create_contract_reminders_internal(
                contract_id=target_contract.id,
                reminders=reminders,
            )

        agreements_data = [
            {"agreement": agreement, "parties": list(agreement.parties.all())}
            for agreement in cast(Any, source_contract.supplementary_agreements).all()
        ]
        if not agreements_data:
            return

        created_agreements = SupplementaryAgreement.objects.bulk_create(
            [
                SupplementaryAgreement(
                    contract=target_contract,
                    name=data["agreement"].name,
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
                for party in data["parties"]
            ]
        )

    @staticmethod
    def plus_one_year_due_at(due_at: Any) -> Any:
        if not due_at:
            return None
        return due_at + relativedelta(years=1)
