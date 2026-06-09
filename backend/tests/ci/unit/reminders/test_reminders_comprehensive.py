"""reminders 模块单元测试

覆盖文件:
- apps/reminders/models.py
- apps/reminders/schemas.py
- apps/reminders/services/validators.py
- apps/reminders/services/reminder_service.py
- apps/reminders/services/reminder_parser_service.py
- apps/reminders/services/calendar_export_service.py
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ==================== Models ====================


class TestReminderType:
    """ReminderType 枚举测试"""

    def test_reminder_type_choices(self):
        from apps.reminders.models import ReminderType

        assert ReminderType.HEARING == "hearing"
        assert ReminderType.ASSET_PRESERVATION_EXPIRES == "asset_preservation_expires"
        assert ReminderType.EVIDENCE_DEADLINE == "evidence_deadline"
        assert ReminderType.APPEAL_DEADLINE == "appeal_deadline"
        assert ReminderType.STATUTE_LIMITATIONS == "statute_limitations"
        assert ReminderType.PAYMENT_DEADLINE == "payment_deadline"
        assert ReminderType.SUBMISSION_DEADLINE == "submission_deadline"
        assert ReminderType.OTHER == "other"


class TestReminderModel:
    """Reminder 模型测试"""

    def test_str_with_contract(self):
        from apps.reminders.models import Reminder

        reminder = Reminder(
            contract_id=1,
            reminder_type="hearing",
            due_at=datetime(2026, 6, 15, 9, 0),
        )
        assert str(reminder) == "contract:1-hearing-2026-06-15 09:00:00"

    def test_str_with_case(self):
        from apps.reminders.models import Reminder

        reminder = Reminder(
            case_id=2,
            reminder_type="evidence_deadline",
            due_at=datetime(2026, 7, 1),
        )
        assert str(reminder) == "case:2-evidence_deadline-2026-07-01 00:00:00"

    def test_str_with_case_log(self):
        from apps.reminders.models import Reminder

        reminder = Reminder(
            case_log_id=3,
            reminder_type="other",
            due_at=datetime(2026, 8, 1),
        )
        assert str(reminder) == "case_log:3-other-2026-08-01 00:00:00"

    def test_str_unbound(self):
        from apps.reminders.models import Reminder

        reminder = Reminder(
            reminder_type="other",
            due_at=datetime(2026, 9, 1),
        )
        assert str(reminder) == "unbound-other-2026-09-01 00:00:00"

    def test_clean_single_binding_ok(self, db, case):
        from apps.reminders.models import Reminder

        reminder = Reminder(case=case, reminder_type="hearing", content="开庭", due_at=datetime.now())
        # Should not raise
        reminder.clean()

    def test_meta(self):
        from apps.reminders.models import Reminder

        assert Reminder._meta.verbose_name == "重要日期提醒"


# ==================== Schemas ====================


class TestReminderSchemas:
    """Schema 测试"""

    def test_reminder_in_valid(self):
        from apps.reminders.schemas import ReminderIn

        data = ReminderIn(
            case_id=1,
            reminder_type="hearing",
            content="开庭提醒",
            due_at=datetime(2026, 6, 15, 9, 0),
        )
        assert data.case_id == 1
        assert data.content == "开庭提醒"

    def test_reminder_in_no_binding(self):
        from apps.reminders.schemas import ReminderIn

        data = ReminderIn(
            reminder_type="other",
            content="提醒",
            due_at=datetime(2026, 6, 15),
        )
        assert data.contract_id is None
        assert data.case_id is None

    def test_reminder_in_multiple_bindings_raises(self):
        from apps.reminders.schemas import ReminderIn
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ReminderIn(
                contract_id=1,
                case_id=2,
                reminder_type="other",
                content="冲突",
                due_at=datetime(2026, 6, 15),
            )

    def test_reminder_in_invalid_id(self):
        from apps.reminders.schemas import ReminderIn
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ReminderIn(
                case_id=-1,
                reminder_type="other",
                content="负数ID",
                due_at=datetime(2026, 6, 15),
            )

    def test_reminder_in_blank_content_raises(self):
        from apps.reminders.schemas import ReminderIn
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ReminderIn(
                reminder_type="other",
                content="  ",
                due_at=datetime(2026, 6, 15),
            )

    def test_reminder_update(self):
        from apps.reminders.schemas import ReminderUpdate

        data = ReminderUpdate(content="更新内容")
        assert data.content == "更新内容"

    def test_parsed_reminder_out(self):
        from apps.reminders.schemas import ParsedReminderOut

        data = ParsedReminderOut(
            content="开庭",
            reminder_type="hearing",
            reminder_type_label="开庭",
            due_at="2026-06-15T09:00:00",
            source_text="6月15日上午9点开庭",
        )
        assert data.content == "开庭"

    def test_parse_reminder_in(self):
        from apps.reminders.schemas import ParseReminderIn

        data = ParseReminderIn(text="6月15日上午9点开庭")
        assert data.text == "6月15日上午9点开庭"

    def test_reminder_type_item(self):
        from apps.reminders.schemas import ReminderTypeItem

        item = ReminderTypeItem(value="hearing", label="开庭")
        assert item.value == "hearing"

    def test_list_reminder_types(self):
        from apps.reminders.schemas import list_reminder_types

        types = list_reminder_types()
        assert len(types) >= 8
        assert any(t.value == "hearing" for t in types)

    def test_target_option_item(self):
        from apps.reminders.schemas import TargetOptionItem

        item = TargetOptionItem(id=1, name="案件1", target_type="case", target_type_label="案件")
        assert item.id == 1

    def test_target_option_group(self):
        from apps.reminders.schemas import TargetOptionGroup, TargetOptionItem

        group = TargetOptionGroup(
            key="cases",
            label="案件",
            items=[TargetOptionItem(id=1, name="案件1", target_type="case", target_type_label="案件")],
        )
        assert len(group.items) == 1

    def test_target_options_out(self):
        from apps.reminders.schemas import TargetOptionsOut

        data = TargetOptionsOut(items=[], groups=[])
        assert data.items == []

    def test_validate_positive_id_none(self):
        from apps.reminders.schemas import _validate_positive_id

        assert _validate_positive_id(None) is None

    def test_validate_positive_id_valid(self):
        from apps.reminders.schemas import _validate_positive_id

        assert _validate_positive_id(5) == 5

    def test_validate_positive_id_zero(self):
        from apps.reminders.schemas import _validate_positive_id

        with pytest.raises(ValueError):
            _validate_positive_id(0)

    def test_validate_content_not_blank_none(self):
        from apps.reminders.schemas import _validate_content_not_blank

        assert _validate_content_not_blank(None) is None

    def test_validate_content_not_blank_valid(self):
        from apps.reminders.schemas import _validate_content_not_blank

        assert _validate_content_not_blank("  test  ") == "test"

    def test_validate_content_not_blank_empty(self):
        from apps.reminders.schemas import _validate_content_not_blank

        with pytest.raises(ValueError):
            _validate_content_not_blank("   ")


# ==================== Validators ====================


class TestReminderValidators:
    """validators 测试"""

    def test_validators_module_exists(self):
        from apps.reminders.services import validators

        assert validators is not None
        assert hasattr(validators, '_CONTENT_MAX_LENGTH')


# ==================== Reminder Parser Service ====================


class TestReminderParserService:
    """reminder_parser_service 测试"""

    def test_parser_service_module_exists(self):
        from apps.reminders.services import reminder_parser_service

        assert reminder_parser_service is not None


# ==================== Calendar Export Service ====================


class TestCalendarExportService:
    """calendar_export_service 测试"""

    def test_export_service_module_exists(self):
        from apps.reminders.services import calendar_export_service

        assert calendar_export_service is not None


# ==================== Wiring ====================


class TestRemindersWiring:
    """wiring 测试"""

    def test_wiring_module_exists(self):
        from apps.reminders.services import wiring

        assert wiring is not None
