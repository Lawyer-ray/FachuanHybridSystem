"""Regression tests for _CaseLogReminderMixin Pydantic v2 model_fields_set leak.

Bug: Pydantic v2.13.3 model_validator(mode="after") that assigns to self.field
mutates model_fields_set, causing model_dump(exclude_unset=True) to leak
default values that were never provided by the caller.

Fix: Snapshot model_fields_set before assignments and restore after.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from apps.cases.schemas.log_schemas import CaseLogCreate, CaseLogIn, CaseLogUpdate


class TestCaseLogReminderMixinFieldsSet:
    """Ensure model_fields_set is not polluted by validator assignments."""

    def test_update_only_content_no_reminder_leak(self) -> None:
        """CaseLogUpdate with only content should not include reminder fields."""
        schema = CaseLogUpdate(content="test content")
        dumped = schema.model_dump(exclude_unset=True)
        assert "reminder_type" not in dumped
        assert "reminder_time" not in dumped
        assert "content" in dumped

    def test_update_empty_body_no_reminder_leak(self) -> None:
        """CaseLogUpdate with no fields should produce empty dict."""
        schema = CaseLogUpdate()
        dumped = schema.model_dump(exclude_unset=True)
        assert dumped == {}

    def test_update_both_reminders_no_leak(self) -> None:
        """CaseLogUpdate with both reminder fields should include both."""
        now = datetime.now(tz=timezone.utc)
        schema = CaseLogUpdate(content="x", reminder_type="hearing", reminder_time=now)
        dumped = schema.model_dump(exclude_unset=True)
        assert "reminder_type" in dumped
        assert "reminder_time" in dumped
        assert "content" in dumped

    def test_in_only_content_no_reminder_leak(self) -> None:
        """CaseLogIn with only case_id and content should not leak reminders."""
        schema = CaseLogIn(case_id=1, content="test")
        dumped = schema.model_dump(exclude_unset=True)
        assert "reminder_type" not in dumped
        assert "reminder_time" not in dumped
        assert "case_id" in dumped
        assert "content" in dumped

    def test_create_only_content_no_reminder_leak(self) -> None:
        """CaseLogCreate with only content should not leak reminders."""
        schema = CaseLogCreate(content="test")
        dumped = schema.model_dump(exclude_unset=True)
        assert "reminder_type" not in dumped
        assert "reminder_time" not in dumped
        assert "content" in dumped

    def test_update_reminder_type_without_time_rejected(self) -> None:
        """Providing only reminder_type (no time) should raise."""
        with pytest.raises(Exception, match="提醒类型和提醒时间必须同时提供"):
            CaseLogUpdate(content="x", reminder_type="hearing")

    def test_update_reminder_time_without_type_rejected(self) -> None:
        """Providing only reminder_time (no type) should raise."""
        now = datetime.now(tz=timezone.utc)
        with pytest.raises(Exception, match="提醒类型和提醒时间必须同时提供"):
            CaseLogUpdate(content="x", reminder_time=now)

    def test_reminder_type_validation_preserved(self) -> None:
        """Invalid reminder type should still be rejected."""
        now = datetime.now(tz=timezone.utc)
        with pytest.raises(Exception, match="无效的提醒类型"):
            CaseLogUpdate(content="x", reminder_type="invalid_type", reminder_time=now)
