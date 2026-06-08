"""cases/services/case_import_service.py + email_folder_scan_service.py 单元测试。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.cases.services.case_import_service import (
    _CASE_FIELDS,
    _parse_log_reminders_for_create,
)


class TestParseLogRemindersForCreate:
    def test_empty_list(self) -> None:
        assert _parse_log_reminders_for_create([]) == []

    def test_valid_reminder(self) -> None:
        reminders = [{"reminder_type": "DEADLINE", "content": "开庭", "due_at": "2026-06-15T10:00:00", "metadata": {"key": "val"}}]
        result = _parse_log_reminders_for_create(reminders)  # type: ignore[arg-type]
        assert len(result) == 1
        assert result[0]["reminder_type"] == "DEADLINE"
        assert isinstance(result[0]["due_at"], datetime)

    def test_datetime_object_input(self) -> None:
        dt = datetime(2026, 7, 1)
        reminders = [{"reminder_type": "X", "due_at": dt}]
        result = _parse_log_reminders_for_create(reminders)  # type: ignore[arg-type]
        assert result[0]["due_at"] is dt

    def test_missing_reminder_type_skipped(self) -> None:
        reminders = [{"due_at": "2026-06-01T00:00:00"}]
        assert _parse_log_reminders_for_create(reminders) == []  # type: ignore[arg-type]

    def test_none_due_at_skipped(self) -> None:
        reminders = [{"reminder_type": "X", "due_at": None}]
        assert _parse_log_reminders_for_create(reminders) == []  # type: ignore[arg-type]

    def test_invalid_date_string_skipped(self) -> None:
        reminders = [{"reminder_type": "X", "due_at": "bad"}]
        assert _parse_log_reminders_for_create(reminders) == []  # type: ignore[arg-type]

    def test_non_dict_metadata_becomes_empty(self) -> None:
        reminders = [{"reminder_type": "X", "due_at": "2026-06-01T00:00:00", "metadata": "bad"}]
        result = _parse_log_reminders_for_create(reminders)  # type: ignore[arg-type]
        assert result[0]["metadata"] == {}


class TestCaseFields:
    def test_contains_name(self) -> None:
        assert "name" in _CASE_FIELDS

    def test_contains_filing_number(self) -> None:
        assert "filing_number" in _CASE_FIELDS

    def test_is_tuple(self) -> None:
        assert isinstance(_CASE_FIELDS, tuple)


class TestCaseImportService:
    def _make_service(self):
        from apps.cases.services.case_import_service import CaseImportService
        return CaseImportService(contract_import=MagicMock(), client_resolve=MagicMock(), lawyer_resolve=MagicMock())

    def test_init(self) -> None:
        svc = self._make_service()
        assert svc._contract_import is not None

    def test_bind_contract_import(self) -> None:
        svc = self._make_service()
        new_import = MagicMock()
        svc.bind_contract_import(new_import)
        assert svc._contract_import is new_import

    def test_bind_contract_import_none(self) -> None:
        svc = self._make_service()
        svc.bind_contract_import(None)
        assert svc._contract_import is None


class TestEmailFolderScanServiceResolveSubfolder:
    def _make_service(self):
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        return EmailFolderScanService(mutation_service=MagicMock(), query_service=MagicMock())

    def test_empty_subfolder_raises(self) -> None:
        from pathlib import Path
        svc = self._make_service()
        with pytest.raises(Exception) as exc_info:
            svc._resolve_subfolder(Path("/root"), "")
        assert "子文件夹路径不能为空" in str(exc_info.value)

    def test_absolute_path_raises(self) -> None:
        from pathlib import Path
        svc = self._make_service()
        with pytest.raises(Exception) as exc_info:
            svc._resolve_subfolder(Path("/root"), "/etc/passwd")
        assert "相对路径" in str(exc_info.value)

    def test_tilde_path_raises(self) -> None:
        from pathlib import Path
        svc = self._make_service()
        with pytest.raises(Exception) as exc_info:
            svc._resolve_subfolder(Path("/root"), "~/secret")
        assert "相对路径" in str(exc_info.value)

    def test_dotdot_path_raises(self) -> None:
        from pathlib import Path
        svc = self._make_service()
        with pytest.raises(Exception) as exc_info:
            svc._resolve_subfolder(Path("/root"), "../escape")
        assert "非法" in str(exc_info.value)

    def test_hidden_dir_raises(self) -> None:
        from pathlib import Path
        svc = self._make_service()
        with pytest.raises(Exception) as exc_info:
            svc._resolve_subfolder(Path("/root"), ".hidden")
        assert "非法" in str(exc_info.value)

    def test_cloud_provider_joins_path(self) -> None:
        svc = self._make_service()
        provider = MagicMock()
        result = svc._resolve_subfolder("/cloud/root", "subfolder", provider=provider)
        assert result == "/cloud/root/subfolder"


class TestEmailFolderScanServiceBuildLogContent:
    def _make_service(self):
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        return EmailFolderScanService(mutation_service=MagicMock(), query_service=MagicMock())

    def test_date_prefix_stripped(self) -> None:
        svc = self._make_service()
        assert svc._build_log_content("2026-06-01 开庭准备") == "开庭准备"

    def test_date_with_dots_stripped(self) -> None:
        svc = self._make_service()
        assert svc._build_log_content("2026.6.1 补充证据") == "补充证据"

    def test_no_date_returns_original(self) -> None:
        svc = self._make_service()
        assert svc._build_log_content("开庭准备材料") == "开庭准备材料"


class TestEmailFolderScanServiceGetBoundCaseRoot:
    def _make_service(self):
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        return EmailFolderScanService(mutation_service=MagicMock(), query_service=MagicMock())

    @patch("apps.cases.services.log.email_folder_scan_service.CaseFolderBinding")
    def test_no_binding_returns_none(self, MockBinding: MagicMock) -> None:
        svc = self._make_service()
        MockBinding.objects.filter.return_value.first.return_value = None
        root, provider = svc._get_bound_case_root(1)
        assert root is None
        assert provider is None

    @patch("apps.cases.services.log.email_folder_scan_service.CaseFolderBinding")
    def test_binding_no_path_returns_none(self, MockBinding: MagicMock) -> None:
        svc = self._make_service()
        binding = MagicMock()
        binding.resolved_folder_path = ""
        MockBinding.objects.filter.return_value.first.return_value = binding
        root, provider = svc._get_bound_case_root(1)
        assert root is None
