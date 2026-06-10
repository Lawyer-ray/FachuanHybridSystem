"""Batch7 coverage tests for apps.reminders."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from django.utils import timezone

from apps.core.exceptions import ValidationException
from apps.reminders.models import ReminderType
from apps.reminders.schemas import (
    ParseReminderIn,
    ParsedReminderOut,
    ReminderIn,
    ReminderTypeItem,
    ReminderUpdate,
    TargetOptionGroup,
    TargetOptionItem,
    TargetOptionsOut,
    list_reminder_types,
    _validate_content_not_blank,
    _validate_positive_id,
)
from apps.reminders.services.validators import (
    normalize_content,
    normalize_due_at,
    normalize_metadata,
    normalize_reminder_type,
    normalize_target_id,
    validate_binding_exclusive,
    validate_positive_id,
    _CONTENT_MAX_LENGTH,
)


# ── ReminderType ────────────────────────────────────────────────────────────


class TestReminderType:
    def test_hearing(self) -> None:
        assert ReminderType.HEARING == "hearing"

    def test_asset_preservation(self) -> None:
        assert ReminderType.ASSET_PRESERVATION_EXPIRES == "asset_preservation_expires"

    def test_evidence_deadline(self) -> None:
        assert ReminderType.EVIDENCE_DEADLINE == "evidence_deadline"

    def test_appeal_deadline(self) -> None:
        assert ReminderType.APPEAL_DEADLINE == "appeal_deadline"

    def test_statute_limitations(self) -> None:
        assert ReminderType.STATUTE_LIMITATIONS == "statute_limitations"

    def test_values_count(self) -> None:
        assert len(ReminderType.values) == 8


# ── Schema validators ───────────────────────────────────────────────────────


class TestSchemaValidators:
    def test_validate_positive_id_none(self) -> None:
        assert _validate_positive_id(None) is None

    def test_validate_positive_id_valid(self) -> None:
        assert _validate_positive_id(5) == 5

    def test_validate_positive_id_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="正整数"):
            _validate_positive_id(0)

    def test_validate_positive_id_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="正整数"):
            _validate_positive_id(-1)

    def test_validate_positive_id_bool_raises(self) -> None:
        with pytest.raises(ValueError, match="正整数"):
            _validate_positive_id(True)

    def test_validate_content_not_blank_none(self) -> None:
        assert _validate_content_not_blank(None) is None

    def test_validate_content_not_blank_valid(self) -> None:
        assert _validate_content_not_blank("hello") == "hello"

    def test_validate_content_not_blank_strips(self) -> None:
        assert _validate_content_not_blank("  hello  ") == "hello"

    def test_validate_content_not_blank_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="不能为空"):
            _validate_content_not_blank("   ")


# ── Reminder service validators ─────────────────────────────────────────────


class TestServiceValidators:
    def test_normalize_target_id_none(self) -> None:
        assert normalize_target_id(None, field_name="test") is None

    def test_normalize_target_id_valid(self) -> None:
        assert normalize_target_id(5, field_name="test") == 5

    def test_normalize_target_id_zero_raises(self) -> None:
        with pytest.raises(ValidationException):
            normalize_target_id(0, field_name="test")

    def test_normalize_target_id_bool_raises(self) -> None:
        with pytest.raises(ValidationException):
            normalize_target_id(True, field_name="test")

    def test_validate_positive_id_service_valid(self) -> None:
        validate_positive_id(5, field_name="test")

    def test_validate_positive_id_service_zero_raises(self) -> None:
        with pytest.raises(ValidationException):
            validate_positive_id(0, field_name="test")

    def test_validate_binding_exclusive_none(self) -> None:
        validate_binding_exclusive(contract_id=None, case_id=None, case_log_id=None)

    def test_validate_binding_exclusive_one(self) -> None:
        validate_binding_exclusive(contract_id=1, case_id=None, case_log_id=None)

    def test_validate_binding_exclusive_two_raises(self) -> None:
        with pytest.raises(ValidationException, match="最多只能绑定一个"):
            validate_binding_exclusive(contract_id=1, case_id=2, case_log_id=None)

    def test_normalize_reminder_type_valid(self) -> None:
        assert normalize_reminder_type("hearing") == "hearing"

    def test_normalize_reminder_type_empty_raises(self) -> None:
        with pytest.raises(ValidationException, match="不能为空"):
            normalize_reminder_type("")

    def test_normalize_reminder_type_invalid_raises(self) -> None:
        with pytest.raises(ValidationException, match="无效"):
            normalize_reminder_type("nonexistent")

    def test_normalize_content_valid(self) -> None:
        assert normalize_content("hello") == "hello"

    def test_normalize_content_empty_raises(self) -> None:
        with pytest.raises(ValidationException, match="不能为空"):
            normalize_content("")

    def test_normalize_content_too_long_raises(self) -> None:
        with pytest.raises(ValidationException, match="不能超过"):
            normalize_content("x" * 300)

    def test_normalize_due_at_naive(self) -> None:
        naive_dt = datetime(2025, 6, 30, 10, 0, 0)
        result = normalize_due_at(naive_dt)
        assert timezone.is_aware(result)

    def test_normalize_due_at_aware(self) -> None:
        aware_dt = timezone.make_aware(datetime(2025, 6, 30, 10, 0, 0))
        result = normalize_due_at(aware_dt)
        assert timezone.is_aware(result)

    def test_normalize_metadata_none(self) -> None:
        assert normalize_metadata(None) == {}

    def test_normalize_metadata_valid(self) -> None:
        data = {"key": "value"}
        assert normalize_metadata(data) == data

    def test_normalize_metadata_non_dict_raises(self) -> None:
        with pytest.raises(ValidationException, match="JSON 对象"):
            normalize_metadata("not a dict")

    def test_content_max_length(self) -> None:
        assert _CONTENT_MAX_LENGTH == 255


# ── list_reminder_types ─────────────────────────────────────────────────────


class TestListReminderTypes:
    def test_returns_list(self) -> None:
        result = list_reminder_types()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_items_have_value_and_label(self) -> None:
        result = list_reminder_types()
        for item in result:
            assert hasattr(item, "value")
            assert hasattr(item, "label")


# ── Schema classes ──────────────────────────────────────────────────────────


class TestSchemas:
    def test_reminder_type_item(self) -> None:
        item = ReminderTypeItem(value="hearing", label="开庭")
        assert item.value == "hearing"

    def test_target_option_item(self) -> None:
        item = TargetOptionItem(id=1, name="Test", target_type="case", target_type_label="案件")
        assert item.id == 1

    def test_target_option_group(self) -> None:
        group = TargetOptionGroup(key="cases", label="案件", items=[])
        assert group.key == "cases"

    def test_target_options_out(self) -> None:
        out = TargetOptionsOut(items=[], groups=[])
        assert out.items == []
