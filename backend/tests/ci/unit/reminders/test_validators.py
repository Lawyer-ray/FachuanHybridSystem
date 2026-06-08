"""Tests for reminders.services.validators."""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.reminders.services.validators import (
    normalize_content,
    normalize_due_at,
    normalize_metadata,
    normalize_reminder_type,
    normalize_target_id,
    validate_binding_exclusive,
    validate_fk_exists,
    validate_positive_id,
)


class TestNormalizeTargetId:
    def test_none_returns_none(self) -> None:
        assert normalize_target_id(None, field_name="test") is None

    def test_valid_positive_int(self) -> None:
        assert normalize_target_id(1, field_name="test") == 1
        assert normalize_target_id(100, field_name="test") == 100

    def test_zero_raises(self) -> None:
        with pytest.raises(ValidationException):
            normalize_target_id(0, field_name="test")

    def test_negative_raises(self) -> None:
        with pytest.raises(ValidationException):
            normalize_target_id(-1, field_name="test")

    def test_bool_raises(self) -> None:
        with pytest.raises(ValidationException):
            normalize_target_id(True, field_name="test")  # type: ignore[arg-type]

    def test_string_raises(self) -> None:
        with pytest.raises(ValidationException):
            normalize_target_id("1", field_name="test")  # type: ignore[arg-type]


class TestValidatePositiveId:
    def test_valid(self) -> None:
        validate_positive_id(1, field_name="test")  # No error

    def test_zero_raises(self) -> None:
        with pytest.raises(ValidationException):
            validate_positive_id(0, field_name="test")

    def test_negative_raises(self) -> None:
        with pytest.raises(ValidationException):
            validate_positive_id(-5, field_name="test")

    def test_bool_raises(self) -> None:
        with pytest.raises(ValidationException):
            validate_positive_id(True, field_name="test")  # type: ignore[arg-type]


class TestValidateBindingExclusive:
    def test_all_none(self) -> None:
        validate_binding_exclusive(contract_id=None, case_id=None, case_log_id=None)

    def test_one_bound(self) -> None:
        validate_binding_exclusive(contract_id=1, case_id=None, case_log_id=None)

    def test_two_bound_raises(self) -> None:
        with pytest.raises(ValidationException, match="最多只能绑定一个"):
            validate_binding_exclusive(contract_id=1, case_id=2, case_log_id=None)

    def test_three_bound_raises(self) -> None:
        with pytest.raises(ValidationException):
            validate_binding_exclusive(contract_id=1, case_id=2, case_log_id=3)


class TestValidateFkExists:
    def test_all_none(self) -> None:
        validate_fk_exists(contract_id=None, case_id=None, case_log_id=None)

    def test_contract_exists(self) -> None:
        mock_query = MagicMock()
        mock_query.exists.return_value = True
        validate_fk_exists(contract_id=1, case_id=None, case_log_id=None, contract_target_query=mock_query)
        mock_query.exists.assert_called_once_with(1)

    def test_contract_not_exists_raises(self) -> None:
        mock_query = MagicMock()
        mock_query.exists.return_value = False
        with pytest.raises(ValidationException, match="不存在"):
            validate_fk_exists(contract_id=99, case_id=None, case_log_id=None, contract_target_query=mock_query)

    def test_case_exists(self) -> None:
        mock_query = MagicMock()
        mock_query.exists.return_value = True
        validate_fk_exists(contract_id=None, case_id=1, case_log_id=None, case_target_query=mock_query)

    def test_case_not_exists_raises(self) -> None:
        mock_query = MagicMock()
        mock_query.exists.return_value = False
        with pytest.raises(ValidationException, match="不存在"):
            validate_fk_exists(contract_id=None, case_id=99, case_log_id=None, case_target_query=mock_query)

    def test_case_log_exists(self) -> None:
        mock_query = MagicMock()
        mock_query.exists.return_value = True
        validate_fk_exists(contract_id=None, case_id=None, case_log_id=1, case_log_target_query=mock_query)

    def test_case_log_not_exists_raises(self) -> None:
        mock_query = MagicMock()
        mock_query.exists.return_value = False
        with pytest.raises(ValidationException, match="不存在"):
            validate_fk_exists(contract_id=None, case_id=None, case_log_id=99, case_log_target_query=mock_query)

    def test_missing_query_port_contract(self) -> None:
        with pytest.raises(RuntimeError, match="ContractTargetQueryPort"):
            validate_fk_exists(contract_id=1, case_id=None, case_log_id=None)

    def test_missing_query_port_case(self) -> None:
        with pytest.raises(RuntimeError, match="CaseTargetQueryPort"):
            validate_fk_exists(contract_id=None, case_id=1, case_log_id=None)

    def test_missing_query_port_case_log(self) -> None:
        with pytest.raises(RuntimeError, match="CaseLogTargetQueryPort"):
            validate_fk_exists(contract_id=None, case_id=None, case_log_id=1)


class TestNormalizeReminderType:
    def test_valid_type(self) -> None:
        from apps.reminders.models import ReminderType

        valid = ReminderType.values[0]
        assert normalize_reminder_type(valid) == valid

    def test_empty_raises(self) -> None:
        with pytest.raises(ValidationException, match="不能为空"):
            normalize_reminder_type("")

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValidationException, match="无效"):
            normalize_reminder_type("nonexistent_type")


class TestNormalizeContent:
    def test_valid(self) -> None:
        assert normalize_content("开庭提醒") == "开庭提醒"

    def test_strips_whitespace(self) -> None:
        assert normalize_content("  开庭提醒  ") == "开庭提醒"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValidationException, match="不能为空"):
            normalize_content("")

    def test_too_long_raises(self) -> None:
        with pytest.raises(ValidationException, match="不能超过"):
            normalize_content("a" * 256)


class TestNormalizeDueAt:
    def test_aware_datetime(self) -> None:
        from django.utils import timezone

        dt = timezone.now()
        result = normalize_due_at(dt)
        assert result == dt

    def test_naive_datetime_made_aware(self) -> None:
        from django.utils import timezone as dj_tz

        dt = datetime(2026, 6, 1, 10, 0, 0)
        result = normalize_due_at(dt)
        assert dj_tz.is_aware(result)

    def test_non_datetime_raises(self) -> None:
        with pytest.raises(ValidationException, match="格式不正确"):
            normalize_due_at("2026-06-01")  # type: ignore[arg-type]


class TestNormalizeMetadata:
    def test_none_returns_empty_dict(self) -> None:
        assert normalize_metadata(None) == {}

    def test_valid_dict(self) -> None:
        data = {"key": "value", "count": 5}
        assert normalize_metadata(data) == data

    def test_non_dict_raises(self) -> None:
        with pytest.raises(ValidationException, match="JSON 对象"):
            normalize_metadata([1, 2, 3])  # type: ignore[arg-type]

    def test_non_serializable_raises(self) -> None:
        with pytest.raises(ValidationException, match="不可序列化"):
            normalize_metadata({"key": datetime.now()})
