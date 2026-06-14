"""Targeted coverage tests for reminders module — Round 6.

Targets: reminder_service_adapter methods (all mocked at ORM level)
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestReminderServiceAdapterExport:
    """Tests for ReminderServiceAdapter export and batch methods."""

    def test_export_case_log_reminders_empty(self):
        with patch("apps.reminders.services.reminder_service_adapter.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.order_by.return_value.values.return_value = []
            from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
            adapter = ReminderServiceAdapter()
            result = adapter.export_case_log_reminders_internal(case_log_id=99999)
            assert result == []

    def test_export_case_log_reminders_batch_empty(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        result = adapter.export_case_log_reminders_batch_internal(case_log_ids=[])
        assert result == {}

    def test_export_case_log_reminders_batch_dedup(self):
        with patch("apps.reminders.services.reminder_service_adapter.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.order_by.return_value.values.return_value = []
            from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
            adapter = ReminderServiceAdapter()
            result = adapter.export_case_log_reminders_batch_internal(case_log_ids=[1, 1, 2, 2])
            assert 1 in result
            assert 2 in result

    def test_get_latest_case_log_reminder_empty(self):
        with patch("apps.reminders.services.reminder_service_adapter.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.order_by.return_value.values.return_value.first.return_value = None
            from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
            adapter = ReminderServiceAdapter()
            result = adapter.get_latest_case_log_reminder_internal(case_log_id=99999)
            assert result is None

    def test_get_existing_reminder_times_internal(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        # Mock the parent class method directly
        with patch("apps.reminders.services.reminder_service.ReminderService.get_existing_due_times", return_value=set()):
            result = adapter.get_existing_reminder_times_internal(99999, "hearing")
            assert isinstance(result, set)

    def test_create_reminder_internal_invalid_type(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        result = adapter.create_reminder_internal(
            case_log_id=1,
            reminder_type="nonexistent_type",
            reminder_time=datetime.now(),
        )
        assert result is None

    def test_create_reminder_internal_no_time(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        result = adapter.create_reminder_internal(
            case_log_id=1,
            reminder_type="hearing",
            reminder_time=None,
        )
        assert result is None

    def test_create_reminder_internal_exception(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        with patch.object(adapter, "create_reminder", side_effect=RuntimeError("db")):
            result = adapter.create_reminder_internal(
                case_log_id=1,
                reminder_type="hearing",
                reminder_time=datetime.now(),
            )
        assert result is None

    def test_create_reminder_internal_success(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        mock_reminder = MagicMock()
        mock_reminder.pk = 10
        mock_reminder.case_log_id = 1
        mock_reminder.reminder_type = "hearing"
        mock_reminder.due_at = datetime(2024, 1, 15, 9, 0)
        mock_reminder.contract_id = None
        mock_reminder.case_id = None
        mock_reminder.created_at = datetime(2024, 1, 1)

        with patch("apps.reminders.services.reminder_service.ReminderService.create_reminder", return_value=mock_reminder):
            result = adapter.create_reminder_internal(
                case_log_id=1,
                reminder_type="hearing",
                reminder_time=datetime(2024, 1, 15, 9, 0),
                user_id=5,
            )
        assert result is not None
        assert result.id == 10

    def test_upsert_case_log_reminder_internal_create(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()

        with patch.object(adapter, "_get_preferred_case_log_reminder", return_value=None):
            with patch.object(adapter, "create_case_log_reminder_internal") as mock_create:
                mock_create.return_value = MagicMock(id=20)
                result = adapter.upsert_case_log_reminder_internal(
                    case_log_id=1,
                    reminder_type="hearing",
                    content="test",
                    reminder_time=datetime(2024, 1, 15),
                )
                assert result is not None
                mock_create.assert_called_once()

    def test_upsert_case_log_reminder_internal_update(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        existing = MagicMock()
        existing.metadata = {"source": "test"}
        existing.id = 5

        updated = MagicMock()
        updated.pk = 5
        updated.case_log_id = 1
        updated.reminder_type = "hearing"
        updated.due_at = datetime(2024, 1, 15)
        updated.contract_id = None
        updated.case_id = None
        updated.created_at = datetime(2024, 1, 1)

        with patch.object(adapter, "_get_preferred_case_log_reminder", return_value=existing):
            with patch("apps.reminders.services.reminder_service.ReminderService.update_reminder", return_value=updated):
                result = adapter.upsert_case_log_reminder_internal(
                    case_log_id=1,
                    reminder_type="hearing",
                    content="test",
                    reminder_time=datetime(2024, 1, 15),
                    metadata_source="test",
                )
                assert result is not None

    def test_clear_case_log_reminder_internal_found(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        existing = SimpleNamespace(id=5)

        with patch.object(adapter, "_get_preferred_case_log_reminder", return_value=existing):
            with patch("apps.reminders.services.reminder_service.ReminderService.delete_reminder") as mock_del:
                result = adapter.clear_case_log_reminder_internal(case_log_id=1)
                assert result is True
                mock_del.assert_called_once_with(5)

    def test_clear_case_log_reminder_internal_not_found(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        with patch.object(adapter, "_get_preferred_case_log_reminder", return_value=None):
            result = adapter.clear_case_log_reminder_internal(case_log_id=1)
            assert result is False

    def test_get_preferred_no_reminders(self):
        with patch("apps.reminders.services.reminder_service_adapter.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.order_by.return_value = []
            from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
            adapter = ReminderServiceAdapter()
            result = adapter._get_preferred_case_log_reminder(case_log_id=1)
            assert result is None

    def test_get_preferred_with_source_match(self):
        r1 = SimpleNamespace(metadata={"source": "other"})
        r2 = SimpleNamespace(metadata={"source": "case_log_api"})
        with patch("apps.reminders.services.reminder_service_adapter.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.order_by.return_value = [r1, r2]
            from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
            adapter = ReminderServiceAdapter()
            result = adapter._get_preferred_case_log_reminder(
                case_log_id=1, metadata_source="case_log_api"
            )
            assert result == r2

    def test_get_preferred_with_source_no_match(self):
        r1 = SimpleNamespace(metadata={"source": "other"})
        with patch("apps.reminders.services.reminder_service_adapter.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.order_by.return_value = [r1]
            from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
            adapter = ReminderServiceAdapter()
            result = adapter._get_preferred_case_log_reminder(
                case_log_id=1, metadata_source="case_log_api"
            )
            assert result is None

    def test_get_preferred_no_source_returns_first(self):
        r1 = SimpleNamespace(id=1, metadata={})
        with patch("apps.reminders.services.reminder_service_adapter.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.order_by.return_value = [r1]
            from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
            adapter = ReminderServiceAdapter()
            result = adapter._get_preferred_case_log_reminder(case_log_id=1)
            assert result == r1

    def test_get_preferred_non_dict_metadata(self):
        r1 = SimpleNamespace(metadata="not_a_dict")
        with patch("apps.reminders.services.reminder_service_adapter.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.order_by.return_value = [r1]
            from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
            adapter = ReminderServiceAdapter()
            result = adapter._get_preferred_case_log_reminder(
                case_log_id=1, metadata_source="test"
            )
            assert result is None

    def test_export_contract_reminders_internal(self):
        with patch("apps.reminders.services.reminder_service_adapter.Reminder") as MockReminder:
            MockReminder.objects.filter.return_value.order_by.return_value.values.return_value = []
            from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
            adapter = ReminderServiceAdapter()
            result = adapter.export_contract_reminders_internal(contract_id=1)
            assert result == []

    def test_create_case_log_reminder_internal_with_metadata(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        mock_reminder = MagicMock()
        mock_reminder.pk = 30
        mock_reminder.case_log_id = 1
        mock_reminder.reminder_type = "hearing"
        mock_reminder.due_at = datetime(2024, 1, 15)
        mock_reminder.contract_id = None
        mock_reminder.case_id = None
        mock_reminder.created_at = datetime(2024, 1, 1)

        with patch("apps.reminders.services.reminder_service.ReminderService.create_reminder", return_value=mock_reminder):
            result = adapter.create_case_log_reminder_internal(
                case_log_id=1,
                reminder_type="hearing",
                content="test",
                reminder_time=datetime(2024, 1, 15),
                metadata={"extra": "data"},
            )
            assert result is not None

    def test_to_reminder_dto(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        reminder = MagicMock()
        reminder.pk = 1
        reminder.case_log_id = 10
        reminder.reminder_type = "hearing"
        reminder.due_at = datetime(2024, 1, 15, 9, 0)
        reminder.contract_id = None
        reminder.case_id = None
        reminder.created_at = datetime(2024, 1, 1)

        dto = adapter._to_reminder_dto(reminder)
        assert dto.id == 1
        assert dto.reminder_type == "hearing"

    def test_get_reminder_type_by_code_internal_invalid(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        assert adapter.get_reminder_type_by_code_internal("nonexistent") is None

    def test_get_reminder_type_by_code_internal_valid(self):
        from apps.reminders.models import ReminderType
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        code = ReminderType.values[0]
        result = adapter.get_reminder_type_by_code_internal(code)
        assert result is not None
        assert result.code == code
        assert result.id >= 1

    def test_get_reminder_type_for_document_internal_unknown(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        assert adapter.get_reminder_type_for_document_internal("unknown_doc_type") is None

    def test_get_reminder_type_for_document_internal_summons(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        result = adapter.get_reminder_type_for_document_internal("court_summons")
        assert result is not None
        assert result.code == "hearing"

    def test_get_reminder_type_for_document_internal_execution(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        result = adapter.get_reminder_type_for_document_internal("ruling")
        assert result is not None
        assert result.code == "appeal_deadline"

    def test_get_reminder_type_for_document_internal_asset(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        result = adapter.get_reminder_type_for_document_internal("asset_preservation")
        assert result is not None
        assert result.code == "asset_preservation_expires"

    def test_enrich_export_row_valid_type(self):
        from apps.reminders.models import ReminderType
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        code = ReminderType.values[0]
        row = {"reminder_type": code}
        result = ReminderServiceAdapter._enrich_export_row(row)
        assert "reminder_type_label" in result

    def test_enrich_export_row_invalid_type(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        row = {"reminder_type": "bad_type"}
        result = ReminderServiceAdapter._enrich_export_row(row)
        assert result["reminder_type_label"] == "bad_type"

    def test_enrich_export_row_empty_type(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        row = {"reminder_type": ""}
        result = ReminderServiceAdapter._enrich_export_row(row)
        assert result["reminder_type_label"] == ""

    def test_document_type_to_reminder_type_mapping(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        m = ReminderServiceAdapter.DOCUMENT_TYPE_TO_REMINDER_TYPE
        assert m["court_summons"] == "hearing"
        assert m["hearing_summons"] == "hearing"
        assert m["evidence_deadline_notice"] == "evidence_deadline"
        assert m["submission_notice"] == "submission_deadline"
        assert m["ruling"] == "appeal_deadline"
        assert m["verdict"] == "appeal_deadline"
        assert m["asset_preservation"] == "asset_preservation_expires"

    def test_reminder_type_code_to_id_mapping(self):
        from apps.reminders.models import ReminderType
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        m = ReminderServiceAdapter._REMINDER_TYPE_CODE_TO_ID
        for idx, code in enumerate(ReminderType.values):
            assert m[code] == idx + 1

    def test_upsert_case_log_reminder_internal_existing_metadata_none(self):
        """Test upsert when existing reminder has non-dict metadata."""
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter
        adapter = ReminderServiceAdapter()
        existing = SimpleNamespace(id=5, metadata="not_a_dict")

        updated = MagicMock()
        updated.pk = 5
        updated.case_log_id = 1
        updated.reminder_type = "hearing"
        updated.due_at = datetime(2024, 1, 15)
        updated.contract_id = None
        updated.case_id = None
        updated.created_at = datetime(2024, 1, 1)

        with patch.object(adapter, "_get_preferred_case_log_reminder", return_value=existing):
            with patch("apps.reminders.services.reminder_service.ReminderService.update_reminder", return_value=updated):
                result = adapter.upsert_case_log_reminder_internal(
                    case_log_id=1,
                    reminder_type="hearing",
                    content="test",
                    reminder_time=datetime(2024, 1, 15),
                )
                assert result is not None
