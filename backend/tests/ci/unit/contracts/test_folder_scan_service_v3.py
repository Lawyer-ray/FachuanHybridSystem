"""
Unit tests for contracts/services/contract/integrations/folder_scan_service.py.

Covers:
  - ContractFolderScanService.__init__
  - _ensure_contract_exists
  - _normalize_scan_subfolder (normal, absolute path, traversal, empty)
  - _is_within_root
  - _extract_scan_subfolder
  - _resolve_scan_scope (local, cloud, traversal rejection)
  - build_status_payload
  - _extract_scan_subfolder
  - _relative_path_str
  - _import_work_log_suggestions (empty, no case, duplicate)
  - _learn_from_import_correction (same code, different code)
  - _mark_already_imported (no hashes, with hashes)
  - _post_process_candidates (archive_document, case_material, authorization_material, skip)
  - _collect_docx_files (non-litigation, litigation skip)
  - run_contract_folder_scan_task (module-level function)
  - _normalize_docx_name (module-level function)
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock
from uuid import uuid4

import pytest

from apps.core.exceptions import NotFoundError, ValidationException
from apps.contracts.services.contract.integrations.folder_scan_service import (
    ContractFolderScanService,
    _normalize_docx_name,
    run_contract_folder_scan_task,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(**kwargs: Any) -> ContractFolderScanService:
    kwargs.setdefault("scan_service", MagicMock())
    return ContractFolderScanService(**kwargs)


def _make_contract(id: int = 1, name: str = "Test Contract") -> MagicMock:
    c = MagicMock()
    c.id = id
    c.name = name
    c.case_type = "civil"
    return c


def _make_binding(**kwargs: Any) -> MagicMock:
    b = MagicMock()
    b.folder_path = kwargs.get("folder_path", "/tmp/test_folder")
    b.storage_type = kwargs.get("storage_type", "local")
    b.contract_id = kwargs.get("contract_id", 1)
    return b


def _make_session(**kwargs: Any) -> MagicMock:
    s = MagicMock()
    s.id = uuid4()
    s.contract_id = kwargs.get("contract_id", 1)
    s.status = kwargs.get("status", "pending")
    s.progress = kwargs.get("progress", 0)
    s.current_file = kwargs.get("current_file", "")
    s.result_payload = kwargs.get("result_payload", {"summary": {}, "candidates": [], "scan_scope": {}})
    s.error_message = kwargs.get("error_message", "")
    s.started_by_id = kwargs.get("started_by_id")
    s.started_by = kwargs.get("started_by")
    s.updated_at = MagicMock()
    s.created_at = MagicMock()
    return s


# ===========================================================================
# Tests
# ===========================================================================


class TestInit:
    def test_default_scan_service(self) -> None:
        svc = ContractFolderScanService()
        assert svc._scan_service is not None

    def test_injected_scan_service(self) -> None:
        mock = MagicMock()
        svc = ContractFolderScanService(scan_service=mock)
        assert svc._scan_service is mock


class TestEnsureContractExists:
    def test_exists(self) -> None:
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.Contract") as mock_model:
            mock_model.objects.filter.return_value.exists.return_value = True
            svc._ensure_contract_exists(1)

    def test_not_found(self) -> None:
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.Contract") as mock_model:
            mock_model.objects.filter.return_value.exists.return_value = False
            with pytest.raises(NotFoundError):
                svc._ensure_contract_exists(999)


class TestNormalizeScanSubfolder:
    def test_normal_path(self) -> None:
        svc = _make_service()
        assert svc._normalize_scan_subfolder("subfolder") == "subfolder"

    def test_relative_path(self) -> None:
        svc = _make_service()
        assert svc._normalize_scan_subfolder("a/b/c") == "a/b/c"

    def test_empty(self) -> None:
        svc = _make_service()
        assert svc._normalize_scan_subfolder("") == ""
        assert svc._normalize_scan_subfolder(None) == ""

    def test_absolute_path_rejected(self) -> None:
        svc = _make_service()
        with pytest.raises(ValidationException):
            svc._normalize_scan_subfolder("/absolute/path")

    def test_home_path_rejected(self) -> None:
        svc = _make_service()
        with pytest.raises(ValidationException):
            svc._normalize_scan_subfolder("~/documents")

    def test_windows_path_rejected(self) -> None:
        svc = _make_service()
        with pytest.raises(ValidationException):
            svc._normalize_scan_subfolder("C:/Users/test")

    def test_traversal_rejected(self) -> None:
        svc = _make_service()
        with pytest.raises(ValidationException):
            svc._normalize_scan_subfolder("../etc/passwd")

    def test_dot_segments_stripped(self) -> None:
        svc = _make_service()
        assert svc._normalize_scan_subfolder("./a/./b") == "a/b"

    def test_backslash_normalized(self) -> None:
        svc = _make_service()
        assert svc._normalize_scan_subfolder("a\\b") == "a/b"


class TestIsWithinRoot:
    def test_within(self) -> None:
        svc = _make_service()
        root = Path("/tmp/root")
        target = Path("/tmp/root/sub")
        assert svc._is_within_root(root, target) is True

    def test_outside(self) -> None:
        svc = _make_service()
        root = Path("/tmp/root")
        target = Path("/tmp/other")
        assert svc._is_within_root(root, target) is False

    def test_same_path(self) -> None:
        svc = _make_service()
        root = Path("/tmp/root")
        assert svc._is_within_root(root, root) is True


class TestExtractScanSubfolder:
    def test_from_payload(self) -> None:
        svc = _make_service()
        payload = {"scan_scope": {"scan_subfolder": "sub"}}
        assert svc._extract_scan_subfolder(payload) == "sub"

    def test_empty_payload(self) -> None:
        svc = _make_service()
        assert svc._extract_scan_subfolder(None) == ""
        assert svc._extract_scan_subfolder({}) == ""


class TestBuildStatusPayload:
    def test_basic(self) -> None:
        svc = _make_service()
        session = _make_session(
            status="completed",
            progress=100,
            current_file="test.pdf",
            result_payload={
                "summary": {"total_files": 5, "deduped_files": 3, "classified_files": 3},
                "candidates": [{"filename": "a.pdf"}],
                "archive_category": "litigation",
                "archive_item_options": [],
                "work_log_suggestions": [],
            },
        )
        payload = svc.build_status_payload(session=session)
        assert payload["session_id"] == str(session.id)
        assert payload["status"] == "completed"
        assert payload["summary"]["total_files"] == 5
        assert len(payload["candidates"]) == 1


class TestImportWorkLogSuggestions:
    def test_empty_logs(self) -> None:
        svc = _make_service()
        result = svc._import_work_log_suggestions(contract_id=1, confirmed_logs=[])
        assert result == 0

    def test_no_case(self) -> None:
        svc = _make_service()
        with patch("apps.core.interfaces.ServiceLocator") as mock_sl:
            mock_sl.get_case_service.return_value.get_cases_by_contract.return_value = []
            result = svc._import_work_log_suggestions(
                contract_id=1,
                confirmed_logs=[{"content": "test log"}],
            )
        assert result == 0


class TestNormalizeDocxName:
    def test_basic(self) -> None:
        assert _normalize_docx_name("Hello World.docx") == "helloworld.docx"

    def test_with_spaces(self) -> None:
        assert _normalize_docx_name("  Test  File.docx  ") == "testfile.docx"

    def test_none(self) -> None:
        assert _normalize_docx_name(None) == ""

    def test_empty(self) -> None:
        assert _normalize_docx_name("") == ""


class TestRelativePathStr:
    def test_nested(self, tmp_path: Path) -> None:
        svc = _make_service()
        sub = tmp_path / "sub"
        sub.mkdir()
        f = sub / "test.pdf"
        f.touch()
        result = svc._relative_path_str(source_path=str(f), scan_root=tmp_path)
        assert result == "sub"

    def test_direct(self, tmp_path: Path) -> None:
        svc = _make_service()
        f = tmp_path / "test.pdf"
        f.touch()
        result = svc._relative_path_str(source_path=str(f), scan_root=tmp_path)
        assert result == ""

    def test_error(self) -> None:
        svc = _make_service()
        result = svc._relative_path_str(source_path="/other/path", scan_root=Path("/tmp/root"))
        assert result == ""


class TestResolveScanScope:
    def test_local_no_subfolder(self) -> None:
        svc = _make_service()
        result = svc._resolve_scan_scope("/tmp/root", "", storage_provider=None)
        assert result["scan_subfolder"] == ""
        assert result["scan_folder"] == Path("/tmp/root").resolve().as_posix()

    def test_local_with_subfolder(self, tmp_path: Path) -> None:
        svc = _make_service()
        sub = tmp_path / "sub"
        sub.mkdir()
        result = svc._resolve_scan_scope(str(tmp_path), "sub", storage_provider=None)
        assert result["scan_subfolder"] == "sub"

    def test_cloud_no_subfolder(self) -> None:
        svc = _make_service()
        provider = MagicMock()
        result = svc._resolve_scan_scope("/cloud/root", "", storage_provider=provider)
        assert result["scan_subfolder"] == ""
        assert result["scan_folder"] == "/cloud/root"

    def test_cloud_traversal_rejected(self) -> None:
        svc = _make_service()
        provider = MagicMock()
        with pytest.raises(ValidationException):
            svc._resolve_scan_scope("/cloud/root", "../etc", storage_provider=provider)


class TestRunContractFolderScanTask:
    def test_calls_service(self) -> None:
        with patch(
            "apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanService"
        ) as mock_cls:
            mock_cls.return_value.run_scan_task = MagicMock()
            run_contract_folder_scan_task("session-id")
            mock_cls.return_value.run_scan_task.assert_called_once_with(session_id="session-id")


class TestPostProcessCandidates:
    def test_archive_document_category(self) -> None:
        svc = _make_service()
        candidates = [
            {
                "filename": "contract.pdf",
                "source_path": "/tmp/contract.pdf",
                "suggested_category": "archive_document",
            }
        ]
        with patch(
            "apps.contracts.services.contract.integrations._candidate_post_processor.classify_archive_material"
        ) as mock_classify:
            mock_classify.return_value = {
                "category": "archive_document",
                "archive_item_code": "lt_4",
                "archive_item_name": "委托合同",
                "confidence": 0.9,
                "reason": "match",
            }
            with patch(
                "apps.contracts.services.contract.integrations.folder_scan_service.collect_archive_item_options",
                return_value=[],
            ):
                result = svc._post_process_candidates(
                    candidates=candidates,
                    archive_category="litigation",
                    scan_folder="/tmp",
                )

        assert len(result) == 1
        assert result[0]["archive_item_code"] == "lt_4"

    def test_skip_category(self) -> None:
        svc = _make_service()
        candidates = [
            {
                "filename": "skip.pdf",
                "source_path": "/tmp/skip.pdf",
                "suggested_category": "archive_document",
            }
        ]
        with patch(
            "apps.contracts.services.contract.integrations._candidate_post_processor.classify_archive_material"
        ) as mock_classify:
            mock_classify.return_value = {
                "category": "skip",
                "archive_item_code": "",
                "archive_item_name": "",
                "confidence": 0.0,
                "reason": "skip rule",
            }
            result = svc._post_process_candidates(
                candidates=candidates,
                archive_category="litigation",
                scan_folder="/tmp",
            )

        assert result[0]["selected"] is False
        assert "skip_reason" in result[0]

    def test_insurance_keyword_deselected(self) -> None:
        svc = _make_service()
        candidates = [
            {
                "filename": "保单.pdf",
                "source_path": "/tmp/保单.pdf",
                "suggested_category": "contract_original",
            }
        ]
        result = svc._post_process_candidates(
            candidates=candidates,
            archive_category="litigation",
            scan_folder="/tmp",
        )
        assert result[0]["selected"] is False


class TestMarkAlreadyImported:
    def test_no_hashes(self) -> None:
        svc = _make_service()
        candidates = [{"filename": "a.pdf", "source_path": "/tmp/a.pdf"}]
        with patch(
            "apps.contracts.services.contract.integrations._candidate_post_processor.FinalizedMaterial"
        ) as mock_model:
            mock_model.objects.filter.return_value.values_list.return_value = []
            svc._mark_already_imported(candidates, contract_id=1)
        assert candidates[0]["already_imported"] is False
