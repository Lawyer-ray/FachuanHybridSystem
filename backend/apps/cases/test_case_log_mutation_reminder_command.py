"""Regression tests for case log reminder command wiring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apps.cases.models import Case, CaseLog
from apps.cases.services.log.case_log_mutation_service import CaseLogMutationService
from apps.organization.models import Lawyer


class _ReminderServiceSpy:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_case_log_reminder_internal(
        self,
        *,
        case_log_id: int,
        reminder_type: str,
        content: str,
        reminder_time: datetime,
        user_id: int | None = None,
    ) -> object:
        self.calls.append({
            "case_log_id": case_log_id,
            "reminder_type": reminder_type,
            "content": content,
            "reminder_time": reminder_time,
            "user_id": user_id,
        })
        return object()


def _ensure_actor() -> Lawyer:
    return Lawyer.objects.create_user(username=f"caselog-user-{uuid4().hex[:12]}", password="test1234")


@pytest.mark.django_db
def test_create_log_calls_new_reminder_command_with_same_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.core.interfaces import ServiceLocator

    case = Case.objects.create(name="case-with-reminder")
    actor = _ensure_actor()
    reminder_time = datetime.now(tz=UTC) + timedelta(days=1)
    spy = _ReminderServiceSpy()

    monkeypatch.setattr(ServiceLocator, "get_reminder_service", lambda: spy)
    service = CaseLogMutationService()

    log = service.create_log(
        case_id=case.id,
        content="log-content",
        user=actor,
        perm_open_access=True,
        reminder_type="hearing",
        reminder_time=reminder_time,
    )

    assert isinstance(log, CaseLog)
    assert len(spy.calls) == 1
    assert spy.calls[0]["case_log_id"] == log.id
    assert spy.calls[0]["reminder_type"] == "hearing"
    assert spy.calls[0]["content"] == "log-content"
    assert spy.calls[0]["reminder_time"] == reminder_time


@pytest.mark.django_db
def test_create_log_without_reminder_does_not_call_reminder_service(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.core.interfaces import ServiceLocator

    case = Case.objects.create(name="case-no-reminder")
    actor = _ensure_actor()
    spy = _ReminderServiceSpy()

    monkeypatch.setattr(ServiceLocator, "get_reminder_service", lambda: spy)
    service = CaseLogMutationService()

    log = service.create_log(
        case_id=case.id,
        content="no-reminder-log",
        user=actor,
        perm_open_access=True,
        reminder_type=None,
        reminder_time=None,
    )

    assert isinstance(log, CaseLog)
    assert len(spy.calls) == 0


@pytest.mark.django_db
def test_create_log_keeps_exception_propagation_when_reminder_command_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.core.interfaces import ServiceLocator

    class _FailingReminderService:
        def create_case_log_reminder_internal(self, **_: object) -> object:
            raise RuntimeError("boom")

    case = Case.objects.create(name="case-reminder-error")
    actor = _ensure_actor()
    reminder_time = datetime.now(tz=UTC) + timedelta(days=1)
    before_count = CaseLog.objects.count()

    monkeypatch.setattr(ServiceLocator, "get_reminder_service", lambda: _FailingReminderService())
    service = CaseLogMutationService()

    with pytest.raises(RuntimeError, match="boom"):
        service.create_log(
            case_id=case.id,
            content="error-log",
            user=actor,
            perm_open_access=True,
            reminder_type="hearing",
            reminder_time=reminder_time,
        )

    # create_log 当前不是原子事务，提醒失败时日志已创建，此行为需在重构中保持不变
    assert CaseLog.objects.count() == before_count + 1
