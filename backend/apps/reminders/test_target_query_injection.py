"""Regression tests for reminder target query dependency injection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apps.core.exceptions import ValidationException
from apps.reminders.models import Reminder, ReminderType
from apps.reminders.services.reminder_service import ReminderService
from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter


class _ContractQueryStub:
    def __init__(self, result: bool) -> None:
        self._result = result
        self.calls: list[int] = []

    def exists(self, contract_id: int) -> bool:
        self.calls.append(contract_id)
        return self._result


class _CaseLogQueryStub:
    def __init__(self, result: bool) -> None:
        self._result = result
        self.calls: list[int] = []

    def exists(self, case_log_id: int) -> bool:
        self.calls.append(case_log_id)
        return self._result


def _ensure_contract_id() -> int:
    from apps.contracts.models import Contract

    contract = Contract.objects.create(name="inj-contract", case_type="civil")
    return int(contract.pk)


def _ensure_case_log_id() -> int:
    from apps.cases.models import Case, CaseLog
    from apps.organization.models import Lawyer

    lawyer = Lawyer.objects.create_user(username=f"inj-lawyer-{uuid4().hex[:12]}", password="test1234")
    case = Case.objects.create(name="inj-case")
    log = CaseLog.objects.create(case=case, content="inj-log", actor=lawyer)
    return int(log.pk)


@pytest.mark.django_db
def test_service_create_reminder_uses_injected_contract_query() -> None:
    contract_query = _ContractQueryStub(result=False)
    case_log_query = _CaseLogQueryStub(result=True)
    service = ReminderService(contract_target_query=contract_query, case_log_target_query=case_log_query)

    with pytest.raises(ValidationException, match="合同"):
        service.create_reminder(
            contract_id=999999,
            reminder_type=ReminderType.OTHER,
            content="test",
            due_at=datetime.now(tz=UTC) + timedelta(days=1),
        )

    assert contract_query.calls == [999999]
    assert case_log_query.calls == []


@pytest.mark.django_db
def test_service_create_reminder_uses_injected_case_log_query() -> None:
    contract_query = _ContractQueryStub(result=True)
    case_log_query = _CaseLogQueryStub(result=False)
    service = ReminderService(contract_target_query=contract_query, case_log_target_query=case_log_query)

    with pytest.raises(ValidationException, match="案件日志"):
        service.create_reminder(
            case_log_id=999999,
            reminder_type=ReminderType.HEARING,
            content="test",
            due_at=datetime.now(tz=UTC) + timedelta(days=1),
        )

    assert contract_query.calls == []
    assert case_log_query.calls == [999999]


@pytest.mark.django_db
def test_adapter_bulk_create_keeps_behavior_with_injected_queries() -> None:
    contract_id = _ensure_contract_id()
    case_log_id = _ensure_case_log_id()
    contract_query = _ContractQueryStub(result=True)
    case_log_query = _CaseLogQueryStub(result=True)
    adapter = ReminderServiceAdapter(contract_target_query=contract_query, case_log_target_query=case_log_query)
    due_at = datetime.now(tz=UTC) + timedelta(days=7)

    created_contract = adapter.create_contract_reminders_internal(
        contract_id=contract_id,
        reminders=[{
            "reminder_type": ReminderType.OTHER,
            "content": "contract reminder",
            "due_at": due_at,
            "metadata": {"source": "test"},
        }],
    )
    created_case_log = adapter.create_case_log_reminders_internal(
        case_log_id=case_log_id,
        reminders=[{
            "reminder_type": ReminderType.HEARING,
            "content": "case log reminder",
            "due_at": due_at,
            "metadata": {"source": "test"},
        }],
    )

    assert created_contract == 1
    assert created_case_log == 1
    assert contract_query.calls == [contract_id]
    assert case_log_query.calls == [case_log_id]
    assert Reminder.objects.filter(contract_id=contract_id).count() == 1
    assert Reminder.objects.filter(case_log_id=case_log_id).count() == 1


@pytest.mark.django_db
def test_core_dependency_build_reminder_service_keeps_internal_create_behavior() -> None:
    from apps.core.dependencies.business_organization import build_reminder_service

    case_log_id = _ensure_case_log_id()
    service = build_reminder_service()
    due_at = datetime.now(tz=UTC) + timedelta(days=3)

    result = service.create_reminder_internal(
        case_log_id=case_log_id,
        reminder_type=ReminderType.HEARING.value,
        reminder_time=due_at,
    )

    assert result is not None
    assert result.case_log_id == case_log_id
    assert Reminder.objects.filter(case_log_id=case_log_id, reminder_type=ReminderType.HEARING.value).exists()


@pytest.mark.django_db
def test_create_case_log_reminder_internal_keeps_caller_content() -> None:
    case_log_id = _ensure_case_log_id()
    service = ReminderServiceAdapter()
    due_at = datetime.now(tz=UTC) + timedelta(days=2)

    result = service.create_case_log_reminder_internal(
        case_log_id=case_log_id,
        reminder_type=ReminderType.OTHER.value,
        content="caller-content",
        reminder_time=due_at,
    )

    created = Reminder.objects.get(id=result.id)
    assert created.case_log_id == case_log_id
    assert created.content == "caller-content"


@pytest.mark.django_db
def test_export_case_log_reminders_batch_internal_groups_by_case_log() -> None:
    first_case_log_id = _ensure_case_log_id()
    second_case_log_id = _ensure_case_log_id()
    empty_case_log_id = _ensure_case_log_id()
    due_at = datetime.now(tz=UTC) + timedelta(days=5)
    service = ReminderServiceAdapter()

    Reminder.objects.create(
        case_log_id=first_case_log_id,
        reminder_type=ReminderType.HEARING,
        content="first",
        due_at=due_at,
        metadata={"k": "v1"},
    )
    Reminder.objects.create(
        case_log_id=second_case_log_id,
        reminder_type=ReminderType.OTHER,
        content="second",
        due_at=due_at + timedelta(hours=1),
        metadata={"k": "v2"},
    )

    exported = service.export_case_log_reminders_batch_internal(
        case_log_ids=[first_case_log_id, second_case_log_id, empty_case_log_id, first_case_log_id]
    )

    assert set(exported.keys()) == {first_case_log_id, second_case_log_id, empty_case_log_id}
    assert len(exported[first_case_log_id]) == 1
    assert exported[first_case_log_id][0]["content"] == "first"
    assert exported[first_case_log_id][0]["due_at"] == due_at
    assert len(exported[second_case_log_id]) == 1
    assert exported[second_case_log_id][0]["content"] == "second"
    assert exported[empty_case_log_id] == []
