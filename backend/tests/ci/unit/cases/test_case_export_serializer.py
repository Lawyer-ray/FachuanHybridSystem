"""case_export_serializer_service 辅助函数单元测试。

覆盖 _serialize_client、_export_case_log_reminders_map、
_serialize_exported_reminders 的序列化分支。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.cases.services.case.case_export_serializer_service import (
    _export_case_log_reminders_map,
    _serialize_client,
    _serialize_exported_reminders,
)
from apps.testing.factories import CaseLogFactory, ClientFactory, ClientIdentityDocFactory


@pytest.mark.django_db
class TestSerializeClient:
    def test_serializes_client_obj(self) -> None:
        client = ClientFactory(name="导出客户", phone="13900000000")
        ClientIdentityDocFactory(client=client, doc_type="business_license", file_path="docs/bl.pdf")

        payload = _serialize_client(client)

        assert payload["name"] == "导出客户"
        assert payload["client_type"] == client.client_type
        assert payload["phone"] == "13900000000"
        assert payload["identity_docs"] == [{"doc_type": "business_license", "file_path": "docs/bl.pdf"}]
        assert payload["is_our_client"] is False


class TestExportCaseLogRemindersMap:
    def test_empty_logs_return_empty_map(self) -> None:
        with patch("apps.core.interfaces.ServiceLocator.get_reminder_service") as mock_sl:
            result = _export_case_log_reminders_map([])
        assert result == {}
        mock_sl.assert_not_called()

    def test_logs_without_id_filtered(self) -> None:
        log_no_id = SimpleNamespace(id=None)
        with patch("apps.core.interfaces.ServiceLocator.get_reminder_service"):
            result = _export_case_log_reminders_map([log_no_id])
        assert result == {}

    @pytest.mark.django_db
    def test_delegates_to_reminder_service(self) -> None:
        log = CaseLogFactory()
        reminder_service = MagicMock()
        reminder_service.export_case_log_reminders_batch_internal.return_value = {log.pk: [{"due_at": None}]}

        with patch(
            "apps.core.interfaces.ServiceLocator.get_reminder_service",
            return_value=reminder_service,
        ):
            result = _export_case_log_reminders_map([log])

        reminder_service.export_case_log_reminders_batch_internal.assert_called_once_with(case_log_ids=[log.pk])
        assert result == {log.pk: [{"due_at": None}]}


class TestSerializeExportedReminders:
    def test_datetime_isoformatted(self) -> None:
        dt = datetime(2026, 10, 1, 9, 30, 0)
        result = _serialize_exported_reminders(
            [{"reminder_type": "court", "content": "开庭", "due_at": dt, "metadata": {"k": 1}}]
        )
        assert result == [
            {
                "reminder_type": "court",
                "content": "开庭",
                "due_at": "2026-10-01T09:30:00",
                "metadata": {"k": 1},
            }
        ]

    def test_none_due_at_as_empty_string(self) -> None:
        result = _serialize_exported_reminders([{"due_at": None}])
        assert result[0]["due_at"] == ""

    def test_string_due_at_kept_as_string(self) -> None:
        result = _serialize_exported_reminders([{"due_at": "2026-10-01", "content": "x"}])
        assert result[0]["due_at"] == "2026-10-01"

    def test_non_dict_metadata_normalized(self) -> None:
        result = _serialize_exported_reminders([{"due_at": None, "metadata": "not-a-dict"}])
        assert result[0]["metadata"] == {}

    def test_missing_keys_default_none(self) -> None:
        result = _serialize_exported_reminders([{}])
        assert result == [{"reminder_type": None, "content": None, "due_at": "", "metadata": {}}]

    def test_empty_list(self) -> None:
        assert _serialize_exported_reminders([]) == []
