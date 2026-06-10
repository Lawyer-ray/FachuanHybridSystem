"""contracts.services.contract.integrations.folder_scan_service 补充覆盖测试。"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Any

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


# ── _normalize_scan_subfolder ─────────────────────────────────────

class TestNormalizeScanSubfolder:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        return ContractFolderScanService()

    def test_empty_returns_empty(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("") == ""

    def test_slash_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="相对路径"):
            svc._normalize_scan_subfolder("/")

    def test_dot_only_returns_empty(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder(".") == ""

    def test_relative_path(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("subfolder") == "subfolder"

    def test_nested_relative_path(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("a/b/c") == "a/b/c"

    def test_absolute_path_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="相对路径"):
            svc._normalize_scan_subfolder("/absolute/path")

    def test_home_path_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="相对路径"):
            svc._normalize_scan_subfolder("~/documents")

    def test_windows_path_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="相对路径"):
            svc._normalize_scan_subfolder("C:/Users/test")

    def test_dotdot_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="非法"):
            svc._normalize_scan_subfolder("../etc/passwd")

    def test_middle_dotdot_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="非法"):
            svc._normalize_scan_subfolder("sub/../../../etc")

    def test_backslash_normalized(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("sub\\folder") == "sub/folder"


# ── _is_within_root ───────────────────────────────────────────────

class TestIsWithinRoot:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        return ContractFolderScanService()

    def test_within_root(self):
        svc = self._make_service()
        root = Path("/home/user/projects")
        target = Path("/home/user/projects/subfolder")
        assert svc._is_within_root(root, target) is True

    def test_outside_root(self):
        svc = self._make_service()
        root = Path("/home/user/projects")
        target = Path("/home/other/projects")
        assert svc._is_within_root(root, target) is False

    def test_same_path(self):
        svc = self._make_service()
        root = Path("/home/user/projects")
        assert svc._is_within_root(root, root) is True


# ── _extract_scan_subfolder ───────────────────────────────────────

class TestExtractScanSubfolder:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        return ContractFolderScanService()

    def test_none_payload(self):
        svc = self._make_service()
        assert svc._extract_scan_subfolder(None) == ""

    def test_empty_payload(self):
        svc = self._make_service()
        assert svc._extract_scan_subfolder({}) == ""

    def test_with_scan_scope(self):
        svc = self._make_service()
        assert svc._extract_scan_subfolder({"scan_scope": {"scan_subfolder": "sub"}}) == "sub"

    def test_whitespace_stripped(self):
        svc = self._make_service()
        assert svc._extract_scan_subfolder({"scan_scope": {"scan_subfolder": "  sub  "}}) == "sub"


# ── _ensure_contract_exists ───────────────────────────────────────

class TestEnsureContractExists:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        return ContractFolderScanService()

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.Contract")
    def test_exists(self, mock_contract):
        svc = self._make_service()
        mock_contract.objects.filter.return_value.exists.return_value = True
        svc._ensure_contract_exists(1)  # Should not raise

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.Contract")
    def test_not_found(self, mock_contract):
        svc = self._make_service()
        mock_contract.objects.filter.return_value.exists.return_value = False
        with pytest.raises(NotFoundError):
            svc._ensure_contract_exists(999)


# ── _relative_path_str ────────────────────────────────────────────

class TestRelativePathStr:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        return ContractFolderScanService()

    def test_unresolvable_path(self):
        svc = self._make_service()
        result = svc._relative_path_str(
            source_path="/completely/different/path/file.pdf",
            scan_root=Path("/home/user/projects"),
        )
        # If ValueError or RuntimeError, returns ""
        assert isinstance(result, str)


# ── build_status_payload ──────────────────────────────────────────

class TestBuildStatusPayload:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        return ContractFolderScanService()

    def test_basic_payload(self):
        svc = self._make_service()
        session = MagicMock()
        session.id = "session-1"
        session.status = "completed"
        session.progress = 100
        session.current_file = ""
        session.error_message = ""
        session.result_payload = {
            "summary": {"total_files": 10, "deduped_files": 8, "classified_files": 7},
            "candidates": [{"filename": "test.pdf"}],
            "archive_category": "litigation",
            "archive_item_options": [],
            "work_log_suggestions": [],
        }

        payload = svc.build_status_payload(session=session)
        assert payload["session_id"] == "session-1"
        assert payload["status"] == "completed"
        assert payload["summary"]["total_files"] == 10
        assert len(payload["candidates"]) == 1

    def test_empty_payload(self):
        svc = self._make_service()
        session = MagicMock()
        session.id = "session-2"
        session.status = "pending"
        session.progress = 0
        session.current_file = ""
        session.error_message = ""
        session.result_payload = None

        payload = svc.build_status_payload(session=session)
        assert payload["summary"]["total_files"] == 0


# ── _resolve_scan_scope ───────────────────────────────────────────

class TestResolveScanScope:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        return ContractFolderScanService()

    def test_empty_subfolder(self):
        svc = self._make_service()
        result = svc._resolve_scan_scope("/home/user/projects", "")
        assert result["root_folder"] != ""
        assert result["scan_subfolder"] == ""

    def test_cloud_empty_subfolder(self):
        svc = self._make_service()
        provider = MagicMock()
        result = svc._resolve_scan_scope("/bucket/root", "", storage_provider=provider)
        assert result["root_folder"] == "/bucket/root"
        assert result["scan_subfolder"] == ""

    def test_cloud_with_subfolder(self):
        svc = self._make_service()
        provider = MagicMock()
        provider.exists.return_value = True
        result = svc._resolve_scan_scope("/bucket/root", "sub", storage_provider=provider)
        assert result["scan_subfolder"] == "sub"

    def test_cloud_subfolder_not_exists_raises(self):
        svc = self._make_service()
        provider = MagicMock()
        provider.exists.return_value = False
        with pytest.raises(ValidationException, match="不可访问"):
            svc._resolve_scan_scope("/bucket/root", "nonexistent", storage_provider=provider)

    def test_cloud_traversal_raises(self):
        svc = self._make_service()
        provider = MagicMock()
        with pytest.raises(ValidationException):
            svc._resolve_scan_scope("/bucket/root", "../escape", storage_provider=provider)


# ── _get_accessible_binding ───────────────────────────────────────

class TestGetAccessibleBinding:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        return ContractFolderScanService()

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderBinding")
    def test_no_binding_raises(self, mock_binding):
        svc = self._make_service()
        mock_binding.objects.filter.return_value.first.return_value = None
        with pytest.raises(ValidationException, match="未绑定"):
            svc._get_accessible_binding(1)


# ── _make_provider_for_binding ────────────────────────────────────

class TestMakeProviderForBinding:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        return ContractFolderScanService()

    def test_local_returns_none(self):
        svc = self._make_service()
        binding = MagicMock()
        binding.storage_type = "local"
        assert svc._make_provider_for_binding(binding) is None

    @patch("apps.core.cloud_storage.factory.create_provider_for_binding")
    def test_cloud_returns_provider(self, mock_create):
        svc = self._make_service()
        binding = MagicMock()
        binding.storage_type = "oss"
        provider = MagicMock()
        mock_create.return_value = provider
        result = svc._make_provider_for_binding(binding)
        assert result is provider


# ── get_session / get_latest_session ──────────────────────────────

class TestGetSession:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        return ContractFolderScanService()

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanSession")
    def test_not_found_raises(self, mock_session):
        import uuid
        svc = self._make_service()
        mock_session.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_session.objects.get.side_effect = mock_session.DoesNotExist
        with pytest.raises(NotFoundError):
            svc.get_session(contract_id=1, session_id=uuid.uuid4())

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanSession")
    def test_get_latest_session_none(self, mock_session):
        svc = self._make_service()
        mock_session.objects.filter.return_value.order_by.return_value.first.return_value = None
        assert svc.get_latest_session(contract_id=1) is None


# ── _normalize_docx_name (module-level) ───────────────────────────

class TestNormalizeDocxName:
    def test_strips_whitespace(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import _normalize_docx_name
        assert _normalize_docx_name("  hello  world  ") == "helloworld"

    def test_lowercase(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import _normalize_docx_name
        assert _normalize_docx_name("TEST.DOCX") == "test.docx"

    def test_empty(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import _normalize_docx_name
        assert _normalize_docx_name("") == ""

    def test_none(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import _normalize_docx_name
        assert _normalize_docx_name(None) == ""  # type: ignore[arg-type]


# ── _QUALITY_CARD_TITLE constant ──────────────────────────────────

class TestConstants:
    def test_quality_card_title(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        assert "监督卡" in ContractFolderScanService._QUALITY_CARD_TITLE

    def test_active_statuses(self):
        from apps.contracts.models import ContractFolderScanStatus
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService

        assert ContractFolderScanStatus.PENDING in ContractFolderScanService._ACTIVE_STATUSES
        assert ContractFolderScanStatus.RUNNING in ContractFolderScanService._ACTIVE_STATUSES
        assert ContractFolderScanStatus.CLASSIFYING in ContractFolderScanService._ACTIVE_STATUSES


# ── run_contract_folder_scan_task ──────────────────────────────────

class TestRunContractFolderScanTask:
    def test_delegates_to_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import (
            run_contract_folder_scan_task,
        )

        with patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanService") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            run_contract_folder_scan_task("session-id-123")
            mock_instance.run_scan_task.assert_called_once_with(session_id="session-id-123")
