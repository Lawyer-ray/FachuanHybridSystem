"""Tests for reminder service and adapter behaviors."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.cases.models import Case, CaseLog
from apps.contracts.models import Contract
from apps.core.enums import CaseType
from apps.core.exceptions import ValidationException
from apps.organization.models import LawFirm, Lawyer
from apps.reminders.models import Reminder, ReminderType
from apps.reminders.services import ReminderService, ReminderServiceAdapter


@pytest.fixture
def lawyer(db: Any) -> Lawyer:
    firm = LawFirm.objects.create(name="提醒测试律所")
    return Lawyer.objects.create_user(
        username="reminder_tester",
        password="test-pass-123",
        law_firm=firm,
    )


@pytest.fixture
def contract(db: Any) -> Contract:
    return Contract.objects.create(name="提醒测试合同", case_type=CaseType.CIVIL)


@pytest.fixture
def case_log(db: Any, contract: Contract, lawyer: Lawyer) -> CaseLog:
    case = Case.objects.create(name="提醒测试案件", contract=contract)
    return CaseLog.objects.create(case=case, content="提醒日志", actor=lawyer)


@pytest.mark.django_db
def test_create_reminder_rejects_nonexistent_contract() -> None:
    service = ReminderService()

    with pytest.raises(ValidationException, match="合同"):
        service.create_reminder(
            contract_id=999999,
            reminder_type=ReminderType.HEARING,
            content="开庭提醒",
            due_at=timezone.now() + timedelta(days=1),
        )


@pytest.mark.django_db
def test_update_reminder_rejects_whitespace_content(contract: Contract) -> None:
    service = ReminderService()
    reminder = service.create_reminder(
        contract_id=contract.id,
        reminder_type=ReminderType.HEARING,
        content="有效内容",
        due_at=timezone.now() + timedelta(days=1),
    )

    with pytest.raises(ValidationException, match="提醒事项不能为空"):
        service.update_reminder(reminder.id, {"content": "   "})


@pytest.mark.django_db
def test_update_reminder_rejects_non_positive_target_id(case_log: CaseLog) -> None:
    service = ReminderService()
    reminder = service.create_reminder(
        case_log_id=case_log.id,
        reminder_type=ReminderType.HEARING,
        content="开庭提醒",
        due_at=timezone.now() + timedelta(days=1),
    )

    with pytest.raises(ValidationException, match="正整数"):
        service.update_reminder(reminder.id, {"contract_id": 0})


@pytest.mark.django_db
def test_create_reminder_normalizes_content_and_due_at(contract: Contract) -> None:
    service = ReminderService()
    due_at = timezone.now().replace(tzinfo=None)

    reminder = service.create_reminder(
        contract_id=contract.id,
        reminder_type=ReminderType.HEARING,
        content="  需处理开庭  ",
        due_at=due_at,
        metadata=None,
    )

    assert reminder.content == "需处理开庭"
    assert reminder.metadata == {}
    assert timezone.is_aware(reminder.due_at)


@pytest.mark.django_db
def test_list_reminders_rejects_dual_binding_filters() -> None:
    service = ReminderService()

    with pytest.raises(ValidationException, match="不能同时查询"):
        service.list_reminders(contract_id=1, case_log_id=1)


@pytest.mark.django_db
def test_adapter_returns_stable_reminder_type_id() -> None:
    adapter = ReminderServiceAdapter()

    type_item = adapter.get_reminder_type_by_code_internal(ReminderType.HEARING)
    type_item_again = adapter.get_reminder_type_by_code_internal(ReminderType.HEARING)

    assert type_item is not None
    assert type_item_again is not None
    assert type_item.id == type_item_again.id
    assert type_item.id == list(ReminderType.values).index(ReminderType.HEARING) + 1


@pytest.mark.django_db
def test_adapter_create_reminder_internal_returns_none_on_validation_error() -> None:
    adapter = ReminderServiceAdapter()

    result = adapter.create_reminder_internal(
        case_log_id=999999,
        reminder_type=ReminderType.HEARING,
        reminder_time=timezone.now() + timedelta(days=1),
    )

    assert result is None


@pytest.mark.django_db
def test_adapter_bulk_create_contract_reminders_skips_invalid_rows(contract: Contract) -> None:
    adapter = ReminderServiceAdapter()
    due_at = timezone.now() + timedelta(days=2)

    created = adapter.create_contract_reminders_internal(
        contract_id=contract.id,
        reminders=[
            {
                "reminder_type": ReminderType.HEARING,
                "content": "  有效提醒  ",
                "due_at": due_at,
                "metadata": {"source": "clone"},
            },
            {"reminder_type": "invalid-type", "content": "无效类型", "due_at": due_at, "metadata": {}},
            {"reminder_type": ReminderType.HEARING, "content": "无效时间", "due_at": "2026-01-01", "metadata": {}},
            {"reminder_type": ReminderType.HEARING, "content": "无效元数据", "due_at": due_at, "metadata": []},
        ],
    )

    assert created == 1
    reminder = Reminder.objects.get(contract_id=contract.id)
    assert reminder.content == "有效提醒"
    assert reminder.metadata == {"source": "clone"}


@pytest.mark.django_db
def test_adapter_reminder_dto_uses_iso_datetime(case_log: CaseLog) -> None:
    adapter = ReminderServiceAdapter()
    dto = adapter.create_reminder_internal(
        case_log_id=case_log.id,
        reminder_type=ReminderType.HEARING,
        reminder_time=timezone.now() + timedelta(days=1),
    )

    assert dto is not None
    assert "T" in dto.reminder_time
    assert dto.created_at is not None
    assert "T" in dto.created_at
