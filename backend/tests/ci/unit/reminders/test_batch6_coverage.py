"""Batch 6 coverage tests for reminders module."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException


class TestValidators:
    def test_normalize_target_id_none(self):
        from apps.reminders.services.validators import normalize_target_id

        assert normalize_target_id(None, field_name="test") is None

    def test_normalize_target_id_valid(self):
        from apps.reminders.services.validators import normalize_target_id

        assert normalize_target_id(5, field_name="test") == 5

    def test_normalize_target_id_zero(self):
        from apps.reminders.services.validators import normalize_target_id

        with pytest.raises(ValidationException):
            normalize_target_id(0, field_name="test")

    def test_normalize_target_id_negative(self):
        from apps.reminders.services.validators import normalize_target_id

        with pytest.raises(ValidationException):
            normalize_target_id(-1, field_name="test")

    def test_normalize_target_id_bool(self):
        from apps.reminders.services.validators import normalize_target_id

        with pytest.raises(ValidationException):
            normalize_target_id(True, field_name="test")

    def test_normalize_target_id_string(self):
        from apps.reminders.services.validators import normalize_target_id

        with pytest.raises(ValidationException):
            normalize_target_id("abc", field_name="test")

    def test_validate_positive_id_valid(self):
        from apps.reminders.services.validators import validate_positive_id

        validate_positive_id(1, field_name="test")  # no error

    def test_validate_positive_id_zero(self):
        from apps.reminders.services.validators import validate_positive_id

        with pytest.raises(ValidationException):
            validate_positive_id(0, field_name="test")

    def test_validate_positive_id_bool(self):
        from apps.reminders.services.validators import validate_positive_id

        with pytest.raises(ValidationException):
            validate_positive_id(True, field_name="test")

    def test_validate_binding_exclusive_none(self):
        from apps.reminders.services.validators import validate_binding_exclusive

        validate_binding_exclusive(contract_id=None, case_id=None, case_log_id=None)

    def test_validate_binding_exclusive_one(self):
        from apps.reminders.services.validators import validate_binding_exclusive

        validate_binding_exclusive(contract_id=1, case_id=None, case_log_id=None)

    def test_validate_binding_exclusive_two_raises(self):
        from apps.reminders.services.validators import validate_binding_exclusive

        with pytest.raises(ValidationException, match="最多只能绑定一个"):
            validate_binding_exclusive(contract_id=1, case_id=2, case_log_id=None)

    def test_validate_binding_exclusive_three_raises(self):
        from apps.reminders.services.validators import validate_binding_exclusive

        with pytest.raises(ValidationException):
            validate_binding_exclusive(contract_id=1, case_id=2, case_log_id=3)

    def test_validate_fk_exists_contract_success(self):
        from apps.reminders.services.validators import validate_fk_exists

        mock_query = MagicMock()
        mock_query.exists.return_value = True
        validate_fk_exists(contract_id=1, case_id=None, case_log_id=None, contract_target_query=mock_query)

    def test_validate_fk_exists_contract_not_found(self):
        from apps.reminders.services.validators import validate_fk_exists

        mock_query = MagicMock()
        mock_query.exists.return_value = False
        with pytest.raises(ValidationException, match="不存在"):
            validate_fk_exists(contract_id=1, case_id=None, case_log_id=None, contract_target_query=mock_query)

    def test_validate_fk_exists_case_success(self):
        from apps.reminders.services.validators import validate_fk_exists

        mock_query = MagicMock()
        mock_query.exists.return_value = True
        validate_fk_exists(contract_id=None, case_id=1, case_log_id=None, case_target_query=mock_query)

    def test_validate_fk_exists_case_log_success(self):
        from apps.reminders.services.validators import validate_fk_exists

        mock_query = MagicMock()
        mock_query.exists.return_value = True
        validate_fk_exists(contract_id=None, case_id=None, case_log_id=1, case_log_target_query=mock_query)

    def test_validate_fk_exists_missing_port(self):
        from apps.reminders.services.validators import validate_fk_exists

        with pytest.raises(RuntimeError, match="not provided"):
            validate_fk_exists(contract_id=1, case_id=None, case_log_id=None)

    def test_normalize_content_valid(self):
        from apps.reminders.services.validators import normalize_content

        assert normalize_content("  提醒事项  ") == "提醒事项"

    def test_normalize_content_empty(self):
        from apps.reminders.services.validators import normalize_content

        with pytest.raises(ValidationException, match="不能为空"):
            normalize_content("")

    def test_normalize_content_too_long(self):
        from apps.reminders.services.validators import normalize_content

        with pytest.raises(ValidationException, match="不能超过"):
            normalize_content("a" * 300)

    def test_normalize_reminder_type_valid(self):
        from apps.reminders.services.validators import normalize_reminder_type

        result = normalize_reminder_type("hearing")
        assert result == "hearing"

    def test_normalize_reminder_type_empty(self):
        from apps.reminders.services.validators import normalize_reminder_type

        with pytest.raises(ValidationException, match="不能为空"):
            normalize_reminder_type("")

    def test_normalize_reminder_type_invalid(self):
        from apps.reminders.services.validators import normalize_reminder_type

        with pytest.raises(ValidationException, match="无效"):
            normalize_reminder_type("nonexistent_type")

    def test_normalize_due_at_aware(self):
        from django.utils import timezone
        from apps.reminders.services.validators import normalize_due_at

        now = timezone.now()
        assert normalize_due_at(now) == now

    def test_normalize_due_at_naive(self):
        from django.utils import timezone
        from apps.reminders.services.validators import normalize_due_at

        naive = datetime(2026, 1, 1, 12, 0, 0)
        result = normalize_due_at(naive)
        assert timezone.is_aware(result)

    def test_normalize_metadata_none(self):
        from apps.reminders.services.validators import normalize_metadata

        assert normalize_metadata(None) == {}

    def test_normalize_metadata_valid(self):
        from apps.reminders.services.validators import normalize_metadata

        data = {"key": "value"}
        assert normalize_metadata(data) == data

    def test_normalize_metadata_not_dict(self):
        from apps.reminders.services.validators import normalize_metadata

        with pytest.raises(ValidationException, match="JSON 对象"):
            normalize_metadata("not a dict")


class TestReminderParser:
    def test_parse_empty_text(self):
        from apps.reminders.services.reminder_parser_service import (
            parse_reminders_from_text,
        )

        assert parse_reminders_from_text("") == []
        assert parse_reminders_from_text(None) == []

    def test_parse_no_date(self):
        from apps.reminders.services.reminder_parser_service import (
            parse_reminders_from_text,
        )

        assert parse_reminders_from_text("今天天气不错") == []

    def test_parse_hearing_date(self):
        from apps.reminders.services.reminder_parser_service import (
            parse_reminders_from_text,
        )

        results = parse_reminders_from_text("开庭日期2026年06月15日")
        assert len(results) > 0
        assert results[0].reminder_type == "hearing"

    def test_parse_evidence_deadline(self):
        from apps.reminders.services.reminder_parser_service import (
            parse_reminders_from_text,
        )

        results = parse_reminders_from_text("举证期限2026年07月20日")
        assert len(results) > 0
        assert results[0].reminder_type == "evidence_deadline"

    def test_parse_appeal_deadline(self):
        from apps.reminders.services.reminder_parser_service import (
            parse_reminders_from_text,
        )

        results = parse_reminders_from_text("上诉期限2026年08月01日")
        assert len(results) > 0
        assert results[0].reminder_type == "appeal_deadline"

    def test_parse_with_time(self):
        from apps.reminders.services.reminder_parser_service import (
            parse_reminders_from_text,
        )

        results = parse_reminders_from_text("开庭日期2026年06月15日下午3点")
        assert len(results) > 0
        assert "15:00" in results[0].due_at

    def test_parse_iso_date(self):
        from apps.reminders.services.reminder_parser_service import (
            parse_reminders_from_text,
        )

        results = parse_reminders_from_text("缴费期限 2026-07-01")
        assert len(results) > 0

    def test_parse_duplicate_date(self):
        from apps.reminders.services.reminder_parser_service import (
            parse_reminders_from_text,
        )

        results = parse_reminders_from_text(
            "开庭日期2026年06月15日，再次提醒2026年06月15日"
        )
        assert len(results) == 1  # deduped

    def test_infer_reminder_type(self):
        from apps.reminders.services.reminder_parser_service import (
            _infer_reminder_type,
        )

        assert _infer_reminder_type("开庭传票") == "hearing"
        assert _infer_reminder_type("保全到期") == "asset_preservation_expires"
        assert _infer_reminder_type("诉讼时效") == "statute_limitations"
        assert _infer_reminder_type("缴费通知") == "payment_deadline"
        assert _infer_reminder_type("补正期限") == "submission_deadline"
        assert _infer_reminder_type("其他内容") == "other"

    def test_parse_date_formats(self):
        from apps.reminders.services.reminder_parser_service import _parse_date

        assert _parse_date("2026-01-15") is not None
        assert _parse_date("2026/01/15") is not None
        assert _parse_date("2026.01.15") is not None
        assert _parse_date("2026年01月15日") is not None
        assert _parse_date("") is None
        assert _parse_date("invalid") is None

    def test_extract_sentence(self):
        from apps.reminders.services.reminder_parser_service import (
            _extract_sentence,
        )

        text = "这是第一句话。开庭日期2026年06月15日下午3点。这是第三句话。"
        sentence = _extract_sentence(text, 7, 25)
        assert "开庭" in sentence or "2026" in sentence

    def test_generate_content(self):
        from apps.reminders.services.reminder_parser_service import _generate_content

        result = _generate_content("开庭传票通知", "开庭", datetime(2026, 6, 15))
        assert "开庭" in result
