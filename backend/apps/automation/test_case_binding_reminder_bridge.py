"""Regression tests for case-binding reminder bridge behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from apps.automation.services.court_document_recognition.case_binding_service import CaseBindingService
from apps.automation.services.court_document_recognition.data_classes import DocumentType


class _CaseServiceSpy:
    def __init__(self, update_result: bool = True) -> None:
        self.update_result = update_result
        self.calls: list[dict[str, Any]] = []

    def update_case_log_reminder_internal(self, *, case_log_id: int, reminder_time: datetime, reminder_type: str) -> bool:
        self.calls.append(
            {
                "case_log_id": case_log_id,
                "reminder_time": reminder_time,
                "reminder_type": reminder_type,
            }
        )
        return self.update_result


@pytest.mark.parametrize(
    ("document_type", "expected_reminder_type"),
    [
        (DocumentType.SUMMONS, "hearing"),
        (DocumentType.EXECUTION_RULING, "asset_preservation_expires"),
        (DocumentType.OTHER, "other"),
    ],
)
def test_update_log_reminder_delegates_with_expected_type(
    document_type: DocumentType,
    expected_reminder_type: str,
) -> None:
    spy = _CaseServiceSpy(update_result=True)
    service = CaseBindingService(case_service=spy)
    reminder_time = datetime.now(tz=UTC) + timedelta(days=1)

    service._update_log_reminder(case_log_id=42, reminder_time=reminder_time, document_type=document_type)

    assert len(spy.calls) == 1
    assert spy.calls[0]["case_log_id"] == 42
    assert spy.calls[0]["reminder_time"] == reminder_time
    assert spy.calls[0]["reminder_type"] == expected_reminder_type


def test_update_log_reminder_keeps_flow_when_case_service_returns_false() -> None:
    spy = _CaseServiceSpy(update_result=False)
    service = CaseBindingService(case_service=spy)
    reminder_time = datetime.now(tz=UTC) + timedelta(days=1)

    service._update_log_reminder(case_log_id=7, reminder_time=reminder_time, document_type=DocumentType.SUMMONS)

    assert len(spy.calls) == 1
    assert spy.calls[0]["reminder_type"] == "hearing"
