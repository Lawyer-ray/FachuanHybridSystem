from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from dateutil.relativedelta import relativedelta
from django.utils import timezone

from apps.contracts.models import (
    ContractAssignment,
    ContractParty,
    PartyRole,
    SupplementaryAgreement,
    SupplementaryAgreementParty,
)
from apps.contracts.services.contract.admin_workflows import (
    ContractCaseCreationWorkflow,
    ContractCloneWorkflow,
    ContractFilingNumberWorkflow,
)
from apps.reminders.models import Reminder, ReminderType
from tests.factories import ClientFactory, ContractFactory, LawyerFactory


@pytest.mark.django_db
def test_contract_clone_workflow_clones_related_data():
    original_contract = ContractFactory(name="源合同")
    client = ClientFactory()
    ContractParty.objects.create(contract=original_contract, client=client, role=PartyRole.PRINCIPAL)  # type: ignore[misc]

    lawyer = LawyerFactory()
    ContractAssignment.objects.create(contract=original_contract, lawyer=lawyer, is_primary=True, order=0)  # type: ignore[misc]

    due_at = timezone.make_aware(datetime(2025, 5, 1, 0, 0, 0))
    Reminder.objects.create(  # type: ignore[misc]
        contract=original_contract,
        reminder_type=ReminderType.HEARING,
        content="测试提醒",
        due_at=due_at,
    )

    agreement = SupplementaryAgreement.objects.create(contract=original_contract, name="补充协议")  # type: ignore[misc]
    SupplementaryAgreementParty.objects.create(  # type: ignore[misc]
        supplementary_agreement=agreement, client=client, role=PartyRole.PRINCIPAL
    )

    target_contract = ContractFactory(name="目标合同")

    class FakeReminderService:
        def create_contract_reminders_internal(self, *, contract_id, reminders):
            for r in reminders:
                Reminder.objects.create(
                    contract_id=contract_id,
                    reminder_type=r["reminder_type"],
                    content=r["content"],
                    due_at=r["due_at"],
                    metadata=r["metadata"],
                )

    workflow = ContractCloneWorkflow(reminder_service=FakeReminderService())
    workflow.clone_related_data(source_contract=original_contract, target_contract=target_contract)

    assert target_contract.contract_parties.count() == 1  # type: ignore[attr-defined]
    assert target_contract.assignments.count() == 1  # type: ignore[attr-defined]
    assert target_contract.reminders.count() == 1  # type: ignore[attr-defined]
    assert target_contract.reminders.first().due_at == due_at  # type: ignore[attr-defined]
    assert target_contract.supplementary_agreements.count() == 1  # type: ignore[attr-defined]
    assert target_contract.supplementary_agreements.first().parties.count() == 1  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_contract_clone_workflow_due_at_transform():
    original_contract = ContractFactory(name="源合同")
    due_at = timezone.make_aware(datetime(2025, 5, 1, 0, 0, 0))
    Reminder.objects.create(  # type: ignore[misc]
        contract=original_contract,
        reminder_type=ReminderType.HEARING,
        content="测试提醒",
        due_at=due_at,
    )
    target_contract = ContractFactory(name="目标合同")

    class FakeReminderService:
        def create_contract_reminders_internal(self, *, contract_id, reminders):
            for r in reminders:
                Reminder.objects.create(
                    contract_id=contract_id,
                    reminder_type=r["reminder_type"],
                    content=r["content"],
                    due_at=r["due_at"],
                    metadata=r["metadata"],
                )

    workflow = ContractCloneWorkflow(reminder_service=FakeReminderService())
    workflow.clone_related_data(
        source_contract=original_contract,
        target_contract=target_contract,
        due_at_transform=ContractCloneWorkflow.plus_one_year_due_at,
    )

    assert target_contract.reminders.count() == 1  # type: ignore[attr-defined]
    assert target_contract.reminders.first().due_at == due_at + relativedelta(years=1)  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_contract_filing_number_workflow_generates_and_saves():
    contract = ContractFactory(filing_number=None)
    filing_number_service = MagicMock()
    filing_number_service.generate_contract_filing_number.return_value = "X-TEST"

    workflow = ContractFilingNumberWorkflow(filing_number_service=filing_number_service)
    filing_number = workflow.ensure_filing_number(contract=contract)

    assert filing_number == "X-TEST"
    contract.refresh_from_db()  # type: ignore[attr-defined]
    assert contract.filing_number == "X-TEST"  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_contract_case_creation_workflow_calls_case_service():
    contract = ContractFactory(name="合同")
    client1 = ClientFactory()
    client2 = ClientFactory()
    ContractParty.objects.create(contract=contract, client=client1, role=PartyRole.PRINCIPAL)  # type: ignore[misc]
    ContractParty.objects.create(contract=contract, client=client2, role=PartyRole.PRINCIPAL)  # type: ignore[misc]

    lawyer1 = LawyerFactory()
    lawyer2 = LawyerFactory()
    ContractAssignment.objects.create(contract=contract, lawyer=lawyer1, is_primary=True, order=0)  # type: ignore[misc]
    ContractAssignment.objects.create(contract=contract, lawyer=lawyer2, is_primary=False, order=1)  # type: ignore[misc]

    case_service = MagicMock()
    case_service.create_case.return_value = SimpleNamespace(id=123)

    workflow = ContractCaseCreationWorkflow(case_service=case_service)
    case_dto = workflow.create_case_from_contract(
        contract=contract,
        case_data={"name": "案件", "contract_id": contract.id, "case_type": "civil", "is_archived": False},  # type: ignore[attr-defined]
        user="u",
        org_access={"x": 1},
        perm_open_access=True,
    )

    assert case_dto.id == 123
    case_service.create_case.assert_called_once()
    assert case_service.create_case_party.call_count == 2
    assert case_service.create_case_assignment.call_count == 2
