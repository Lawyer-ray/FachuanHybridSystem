"""Tests for reminder service and adapter behaviors."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.cases.models import Case, CaseLog
from apps.contracts.models import Contract
from apps.core.enums import CaseType
from apps.core.exceptions import NotFoundError, ValidationException
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


@pytest.fixture
def reminder(contract: Contract) -> Reminder:
    return ReminderService().create_reminder(
        contract_id=contract.id,
        reminder_type=ReminderType.HEARING,
        content="测试提醒",
        due_at=timezone.now() + timedelta(days=1),
    )


# ── create ──────────────────────────────────────────────────────────────────

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
def test_create_reminder_rejects_both_bindings(contract: Contract, case_log: CaseLog) -> None:
    with pytest.raises(ValidationException, match="只能绑定"):
        ReminderService().create_reminder(
            contract_id=contract.id,
            case_log_id=case_log.id,
            reminder_type=ReminderType.HEARING,
            content="x",
            due_at=timezone.now() + timedelta(days=1),
        )


@pytest.mark.django_db
def test_create_reminder_rejects_no_binding() -> None:
    with pytest.raises(ValidationException, match="只能绑定"):
        ReminderService().create_reminder(
            reminder_type=ReminderType.HEARING,
            content="x",
            due_at=timezone.now() + timedelta(days=1),
        )


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
def test_create_reminder_rejects_content_too_long(contract: Contract) -> None:
    with pytest.raises(ValidationException, match="255"):
        ReminderService().create_reminder(
            contract_id=contract.id,
            reminder_type=ReminderType.HEARING,
            content="x" * 256,
            due_at=timezone.now() + timedelta(days=1),
        )


# ── get ─────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_get_reminder_not_found_raises() -> None:
    with pytest.raises(NotFoundError):
        ReminderService().get_reminder(999999)


@pytest.mark.django_db
def test_get_reminder_returns_instance(reminder: Reminder) -> None:
    result = ReminderService().get_reminder(reminder.id)
    assert result.id == reminder.id


# ── list ─────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_list_reminders_rejects_dual_binding_filters() -> None:
    service = ReminderService()

    with pytest.raises(ValidationException, match="不能同时查询"):
        service.list_reminders(contract_id=1, case_log_id=1)


@pytest.mark.django_db
def test_list_reminders_filters_by_contract(contract: Contract, reminder: Reminder) -> None:
    results = list(ReminderService().list_reminders(contract_id=contract.id))
    assert len(results) == 1
    assert results[0].id == reminder.id


@pytest.mark.django_db
def test_list_reminders_filters_by_case_log(case_log: CaseLog) -> None:
    ReminderService().create_reminder(
        case_log_id=case_log.id,
        reminder_type=ReminderType.HEARING,
        content="案件提醒",
        due_at=timezone.now() + timedelta(days=1),
    )
    results = list(ReminderService().list_reminders(case_log_id=case_log.id))
    assert len(results) == 1
    assert results[0].case_log_id == case_log.id


# ── update ───────────────────────────────────────────────────────────────────

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
def test_update_reminder_updates_content(reminder: Reminder) -> None:
    updated = ReminderService().update_reminder(reminder.id, {"content": "新内容"})
    assert updated.content == "新内容"
    reminder.refresh_from_db()
    assert reminder.content == "新内容"


@pytest.mark.django_db
def test_update_reminder_empty_data_no_save(reminder: Reminder) -> None:
    """空 data 不触发 save，返回原实例。"""
    original_content = reminder.content
    updated = ReminderService().update_reminder(reminder.id, {})
    assert updated.content == original_content


@pytest.mark.django_db
def test_update_reminder_clears_metadata(reminder: Reminder) -> None:
    """metadata=None 应清空为 {}。"""
    ReminderService().update_reminder(reminder.id, {"metadata": {"key": "val"}})
    updated = ReminderService().update_reminder(reminder.id, {"metadata": None})
    assert updated.metadata == {}


# ── delete ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_delete_reminder_removes_record(reminder: Reminder) -> None:
    ReminderService().delete_reminder(reminder.id)
    assert not Reminder.objects.filter(id=reminder.id).exists()


@pytest.mark.django_db
def test_delete_reminder_not_found_raises() -> None:
    with pytest.raises(NotFoundError):
        ReminderService().delete_reminder(999999)


# ── get_existing_due_times ───────────────────────────────────────────────────

@pytest.mark.django_db
def test_get_existing_due_times_returns_set(case_log: CaseLog) -> None:
    due = timezone.now() + timedelta(days=3)
    ReminderService().create_reminder(
        case_log_id=case_log.id,
        reminder_type=ReminderType.HEARING,
        content="提醒",
        due_at=due,
    )
    times = ReminderService().get_existing_due_times(case_log.id, ReminderType.HEARING)
    assert len(times) == 1


# ── adapter ──────────────────────────────────────────────────────────────────

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
def test_adapter_returns_none_for_invalid_type_code() -> None:
    assert ReminderServiceAdapter().get_reminder_type_by_code_internal("invalid") is None


@pytest.mark.django_db
def test_adapter_get_reminder_type_for_document(  ) -> None:
    adapter = ReminderServiceAdapter()
    result = adapter.get_reminder_type_for_document_internal("court_summons")
    assert result is not None
    assert result.code == "hearing"


@pytest.mark.django_db
def test_adapter_get_reminder_type_for_unknown_document() -> None:
    assert ReminderServiceAdapter().get_reminder_type_for_document_internal("unknown_doc") is None


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
def test_adapter_create_reminder_internal_returns_none_for_invalid_type(case_log: CaseLog) -> None:
    result = ReminderServiceAdapter().create_reminder_internal(
        case_log_id=case_log.id,
        reminder_type="invalid_type",
        reminder_time=timezone.now() + timedelta(days=1),
    )
    assert result is None


@pytest.mark.django_db
def test_adapter_create_reminder_internal_returns_none_for_no_time(case_log: CaseLog) -> None:
    result = ReminderServiceAdapter().create_reminder_internal(
        case_log_id=case_log.id,
        reminder_type=ReminderType.HEARING,
        reminder_time=None,
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
def test_adapter_bulk_create_returns_zero_for_empty(contract: Contract) -> None:
    assert ReminderServiceAdapter().create_contract_reminders_internal(
        contract_id=contract.id, reminders=[]
    ) == 0


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


# ── validators ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_normalize_target_id_rejects_non_int() -> None:
    from apps.reminders.services.validators import normalize_target_id

    with pytest.raises(ValidationException, match="正整数"):
        normalize_target_id("abc", field_name="test_field")  # type: ignore[arg-type]


@pytest.mark.django_db
def test_validate_fk_exists_rejects_nonexistent_case_log() -> None:
    from apps.reminders.services.validators import validate_fk_exists

    with pytest.raises(ValidationException, match="案件日志"):
        validate_fk_exists(contract_id=None, case_log_id=999999)


@pytest.mark.django_db
def test_normalize_due_at_rejects_non_datetime() -> None:
    from apps.reminders.services.validators import normalize_due_at

    with pytest.raises(ValidationException, match="格式不正确"):
        normalize_due_at("2026-01-01")  # type: ignore[arg-type]


# ── _apply_update_fields FK switching ────────────────────────────────────────

@pytest.mark.django_db
def test_update_reminder_switch_from_case_log_to_contract(case_log: CaseLog, contract: Contract) -> None:
    """从 case_log 绑定切换到 contract 绑定。"""
    service = ReminderService()
    reminder = service.create_reminder(
        case_log_id=case_log.id,
        reminder_type=ReminderType.HEARING,
        content="原始提醒",
        due_at=timezone.now() + timedelta(days=1),
    )
    # 同时传两个 FK → 应报错
    with pytest.raises(ValidationException, match="只能绑定"):
        service.update_reminder(reminder.id, {"contract_id": contract.id, "case_log_id": case_log.id})
