"""folder_scan_service.py — round8 tests for remaining uncovered branches.

Covers 37 missing: build_status_payload, _normalize_scan_subfolder,
_is_within_root, _relative_path_str, _extract_scan_subfolder,
_post_process_candidates, _collect_docx_files, _learn_from_import_correction,
_normalize_docx_name.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.contract.integrations.folder_scan_service import (
    ContractFolderScanService,
    _normalize_docx_name,
)


def _make_service():
    return ContractFolderScanService(scan_service=MagicMock())


# ── _normalize_docx_name ───────────────────────────────────────────────


class TestNormalizeDocxName:
    def test_basic(self):
        assert _normalize_docx_name("Test File.docx") == "testfile.docx"

    def test_spaces(self):
        assert _normalize_docx_name("  A  B  C  ") == "abc"

    def test_empty(self):
        assert _normalize_docx_name("") == ""

    def test_none(self):
        assert _normalize_docx_name(None) == ""


# ── _normalize_scan_subfolder ──────────────────────────────────────────


class TestNormalizeScanSubfolder:
    def test_empty_string(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("") == ""

    def test_whitespace_only(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("   ") == ""

    def test_valid_relative(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("sub/folder") == "sub/folder"

    def test_leading_slash_rejected(self):
        svc = _make_service()
        with pytest.raises(Exception, match="相对路径"):
            svc._normalize_scan_subfolder("/etc/passwd")

    def test_tilde_rejected(self):
        svc = _make_service()
        with pytest.raises(Exception, match="相对路径"):
            svc._normalize_scan_subfolder("~/secret")

    def test_windows_drive_rejected(self):
        svc = _make_service()
        with pytest.raises(Exception, match="相对路径"):
            svc._normalize_scan_subfolder("C:/Windows")

    def test_dotdot_rejected(self):
        svc = _make_service()
        with pytest.raises(Exception, match="非法"):
            svc._normalize_scan_subfolder("../escape")

    def test_dot_dot_slash(self):
        svc = _make_service()
        with pytest.raises(Exception, match="非法"):
            svc._normalize_scan_subfolder("a/../../b")

    def test_dots_removed(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("a/./b") == "a/b"

    def test_backslash_normalized(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("a\\b") == "a/b"

    def test_single_dot(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder(".") == ""


# ── _is_within_root ────────────────────────────────────────────────────


class TestIsWithinRoot:
    def test_within_root(self):
        svc = _make_service()
        root = Path("/tmp/project")
        target = Path("/tmp/project/sub")
        assert svc._is_within_root(root, target) is True

    def test_outside_root(self):
        svc = _make_service()
        root = Path("/tmp/project")
        target = Path("/tmp/other")
        assert svc._is_within_root(root, target) is False

    def test_equal_path(self):
        svc = _make_service()
        root = Path("/tmp/project")
        assert svc._is_within_root(root, root) is True

    def test_exception_returns_false(self):
        svc = _make_service()
        # Trigger ValueError in commonpath
        assert svc._is_within_root(Path(""), Path("/other")) is False


# ── _relative_path_str ─────────────────────────────────────────────────


class TestRelativePathStr:
    def test_within_root(self, tmp_path):
        svc = _make_service()
        root = tmp_path / "project"
        root.mkdir()
        sub = root / "sub"
        sub.mkdir()
        target = sub / "file.pdf"
        target.touch()

        result = svc._relative_path_str(
            source_path=str(target),
            scan_root=root,
        )
        assert result == "sub"

    def test_at_root(self, tmp_path):
        svc = _make_service()
        root = tmp_path / "project"
        root.mkdir()
        target = root / "file.pdf"
        target.touch()

        result = svc._relative_path_str(
            source_path=str(target),
            scan_root=root,
        )
        assert result == ""

    def test_outside_root(self, tmp_path):
        svc = _make_service()
        root = tmp_path / "project"
        root.mkdir()
        other = tmp_path / "other"
        other.mkdir()
        target = other / "file.pdf"
        target.touch()

        result = svc._relative_path_str(
            source_path=str(target),
            scan_root=root,
        )
        assert result == ""


# ── _extract_scan_subfolder ────────────────────────────────────────────


class TestExtractScanSubfolder:
    def test_empty_payload(self):
        svc = _make_service()
        assert svc._extract_scan_subfolder(None) == ""
        assert svc._extract_scan_subfolder({}) == ""

    def test_with_scope(self):
        svc = _make_service()
        payload = {"scan_scope": {"scan_subfolder": "sub/folder"}}
        assert svc._extract_scan_subfolder(payload) == "sub/folder"

    def test_scope_no_subfolder(self):
        svc = _make_service()
        payload = {"scan_scope": {}}
        assert svc._extract_scan_subfolder(payload) == ""


# ── build_status_payload ───────────────────────────────────────────────


class TestBuildStatusPayload:
    def test_basic(self):
        svc = _make_service()
        session = MagicMock()
        session.id = "test-uuid"
        session.status = "completed"
        session.progress = 100
        session.current_file = ""
        session.error_message = ""
        session.result_payload = {
            "summary": {"total_files": 10, "deduped_files": 8, "classified_files": 5},
            "candidates": [{"filename": "test.pdf"}],
            "archive_category": "litigation",
            "archive_item_options": [{"code": "l_1"}],
            "work_log_suggestions": [{"content": "log"}],
        }

        result = svc.build_status_payload(session=session)
        assert result["session_id"] == "test-uuid"
        assert result["status"] == "completed"
        assert result["summary"]["total_files"] == 10
        assert len(result["candidates"]) == 1
        assert result["archive_category"] == "litigation"

    def test_empty_payload(self):
        svc = _make_service()
        session = MagicMock()
        session.id = "test-uuid"
        session.status = "running"
        session.progress = 50
        session.current_file = "test.pdf"
        session.error_message = ""
        session.result_payload = None

        result = svc.build_status_payload(session=session)
        assert result["summary"]["total_files"] == 0
        assert result["candidates"] == []


# ── get_session ────────────────────────────────────────────────────────


class TestGetSession:
    def test_not_found(self):
        from uuid import UUID

        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanSession") as MockSession:
            MockSession.DoesNotExist = Exception
            MockSession.objects.get.side_effect = MockSession.DoesNotExist

            from apps.core.exceptions import NotFoundError
            with pytest.raises(NotFoundError):
                svc.get_session(contract_id=1, session_id=UUID("12345678-1234-5678-1234-567812345678"))


# ── _post_process_candidates ───────────────────────────────────────────


class TestPostProcessCandidates:
    def test_archive_document_with_match(self):
        svc = _make_service()
        candidate = {
            "filename": "起诉状.pdf",
            "source_path": "/tmp/起诉状.pdf",
            "suggested_category": "archive_document",
        }

        with patch("apps.contracts.services.contract.integrations.folder_scan_service.classify_archive_material") as mock_cls:
            mock_cls.return_value = {
                "category": "matched",
                "archive_item_code": "l_0",
                "archive_item_name": "起诉状",
                "confidence": 0.9,
                "reason": "匹配",
            }
            with patch.object(svc, "_relative_path_str", return_value=""):
                result = svc._post_process_candidates(
                    candidates=[candidate],
                    archive_category="litigation",
                    scan_folder="/tmp/scan",
                )
        assert result[0]["suggested_category"] == "case_material"
        assert result[0]["archive_item_code"] == "l_0"

    def test_archive_document_skip(self):
        svc = _make_service()
        candidate = {
            "filename": "skip.pdf",
            "source_path": "/tmp/skip.pdf",
            "suggested_category": "archive_document",
        }

        with patch("apps.contracts.services.contract.integrations.folder_scan_service.classify_archive_material") as mock_cls:
            mock_cls.return_value = {"category": "skip", "reason": "不需要"}
            result = svc._post_process_candidates(
                candidates=[candidate],
                archive_category="litigation",
                scan_folder="/tmp/scan",
            )
        assert result[0]["selected"] is False
        assert result[0]["skip_reason"] == "不需要"

    def test_archive_document_no_match(self):
        svc = _make_service()
        candidate = {
            "filename": "unknown.pdf",
            "source_path": "/tmp/unknown.pdf",
            "suggested_category": "archive_document",
        }

        with patch("apps.contracts.services.contract.integrations.folder_scan_service.classify_archive_material") as mock_cls:
            mock_cls.return_value = {
                "category": "unmatched",
                "archive_item_code": "",
                "archive_item_name": "未匹配",
                "reason": "未匹配",
            }
            result = svc._post_process_candidates(
                candidates=[candidate],
                archive_category="litigation",
                scan_folder="/tmp/scan",
            )
        assert result[0]["selected"] is False
        assert result[0]["archive_item_code"] == ""

    def test_authorization_material(self):
        svc = _make_service()
        candidate = {
            "filename": "授权.pdf",
            "source_path": "/tmp/auth.pdf",
            "suggested_category": "authorization_material",
        }

        with patch("apps.contracts.services.contract.integrations.folder_scan_service.classify_archive_material") as mock_cls:
            mock_cls.return_value = {
                "category": "matched",
                "archive_item_code": "l_2",
                "archive_item_name": "授权书",
                "confidence": 0.8,
                "reason": "授权",
            }
            result = svc._post_process_candidates(
                candidates=[candidate],
                archive_category="litigation",
                scan_folder="/tmp/scan",
            )
        assert result[0]["suggested_category"] == "case_material"
        assert result[0]["archive_item_code"] == "l_2"

    def test_case_material_with_match(self):
        svc = _make_service()
        candidate = {
            "filename": "合同.pdf",
            "source_path": "/tmp/contract.pdf",
            "suggested_category": "case_material",
        }

        with patch("apps.contracts.services.contract.integrations.folder_scan_service.classify_archive_material") as mock_cls:
            mock_cls.return_value = {
                "category": "matched",
                "archive_item_code": "l_1",
                "archive_item_name": "合同",
                "confidence": 0.9,
                "reason": "合同",
            }
            with patch.object(svc, "_relative_path_str", return_value="sub"):
                result = svc._post_process_candidates(
                    candidates=[candidate],
                    archive_category="litigation",
                    scan_folder="/tmp/scan",
                )
        assert result[0]["archive_item_code"] == "l_1"
        assert result[0]["reason"] == "sub"

    def test_保单_keyword_deselects(self):
        svc = _make_service()
        candidate = {
            "filename": "保单.pdf",
            "source_path": "/tmp/保单.pdf",
            "suggested_category": "case_material",
            "selected": True,
        }

        with patch("apps.contracts.services.contract.integrations.folder_scan_service.classify_archive_material") as mock_cls:
            mock_cls.return_value = {"category": "matched", "archive_item_code": "x", "archive_item_name": "x", "confidence": 0.5, "reason": ""}
            result = svc._post_process_candidates(
                candidates=[candidate],
                archive_category="litigation",
                scan_folder="/tmp/scan",
            )
        assert result[0]["selected"] is False

    def test_non_litigation_collects_docx(self):
        svc = _make_service()
        candidate = {
            "filename": "test.pdf",
            "source_path": "/tmp/test.pdf",
            "suggested_category": "other",
        }

        with patch.object(svc, "_collect_docx_files", return_value=[{"filename": "doc.docx"}]):
            with patch.object(svc, "_mark_already_imported"):
                result = svc._post_process_candidates(
                    candidates=[candidate],
                    archive_category="non_litigation",
                    scan_folder="/tmp/scan",
                    contract_id=1,
                )
        assert len(result) == 2

    def test_cloud_storage_relative_path(self):
        svc = _make_service()
        candidate = {
            "filename": "test.pdf",
            "source_path": "/cloud/scan/test.pdf",
            "suggested_category": "case_material",
        }

        with patch("apps.contracts.services.contract.integrations.folder_scan_service.classify_archive_material") as mock_cls:
            mock_cls.return_value = {"category": "matched", "archive_item_code": "x", "archive_item_name": "x", "confidence": 0.5, "reason": ""}
            result = svc._post_process_candidates(
                candidates=[candidate],
                archive_category="litigation",
                scan_folder="/cloud/scan",
                storage_provider=MagicMock(),
            )
        assert result[0]["reason"] == "test.pdf"


# ── _collect_docx_files ───────────────────────────────────────────────


class TestCollectDocxFiles:
    def test_non_litigation_returns_empty(self):
        svc = _make_service()
        assert svc._collect_docx_files("/tmp", "litigation") == []

    def test_local_no_files(self):
        svc = _make_service()
        with patch("pathlib.Path") as MockPath:
            mock_root = MagicMock()
            mock_root.exists.return_value = False
            MockPath.return_value = mock_root
            result = svc._collect_docx_files("/tmp/scan", "non_litigation")
            assert result == []


# ── _learn_from_import_correction ──────────────────────────────────────


class TestLearnFromImportCorrection:
    def test_no_code_returns(self):
        svc = _make_service()
        svc._learn_from_import_correction(
            candidate={}, actual_archive_item_code="", contract_id=1
        )
        # Should return without doing anything

    def test_same_code_returns(self):
        svc = _make_service()
        candidate = {"archive_item_code": "l_1"}
        svc._learn_from_import_correction(
            candidate=candidate, actual_archive_item_code="l_1", contract_id=1
        )
        # No learning needed

    def test_non_case_material_returns(self):
        svc = _make_service()
        candidate = {"archive_item_code": "old", "suggested_category": "other"}
        svc._learn_from_import_correction(
            candidate=candidate, actual_archive_item_code="l_1", contract_id=1
        )

    def test_no_filename_returns(self):
        svc = _make_service()
        candidate = {"archive_item_code": "old", "suggested_category": "case_material", "filename": ""}
        svc._learn_from_import_correction(
            candidate=candidate, actual_archive_item_code="l_1", contract_id=1
        )

    def test_successful_learning(self):
        svc = _make_service()
        candidate = {
            "archive_item_code": "old_code",
            "suggested_category": "case_material",
            "filename": "合同原件.pdf",
        }

        with patch("apps.contracts.services.contract.integrations.folder_scan_service.Contract") as MockContract:
            MockContract.objects.filter.return_value.values_list.return_value.first.return_value = "litigation"

            with patch("apps.contracts.services.archive.category_mapping.get_archive_category") as mock_cat:
                mock_cat.return_value = "litigation"

                with patch("apps.contracts.services.archive.learning_service.extract_keywords") as mock_kw:
                    mock_kw.return_value = ["合同"]

                    with patch("apps.contracts.models.ArchiveClassificationRule") as MockRule:
                        MockRule.objects.filter.return_value.exclude.return_value.first.return_value = None
                        MockRule.objects.get_or_create.return_value = (MagicMock(), True)

                        svc._learn_from_import_correction(
                            candidate=candidate, actual_archive_item_code="l_1", contract_id=1
                        )
                        MockRule.objects.get_or_create.assert_called()

    def test_existing_rule_skipped(self):
        svc = _make_service()
        candidate = {
            "archive_item_code": "old",
            "suggested_category": "case_material",
            "filename": "test.pdf",
        }

        with patch("apps.contracts.services.contract.integrations.folder_scan_service.Contract") as MockContract:
            MockContract.objects.filter.return_value.values_list.return_value.first.return_value = "litigation"

            with patch("apps.contracts.services.archive.category_mapping.get_archive_category") as mock_cat:
                mock_cat.return_value = "litigation"

                with patch("apps.contracts.services.archive.learning_service.extract_keywords") as mock_kw:
                    mock_kw.return_value = ["test"]

                    with patch("apps.contracts.models.ArchiveClassificationRule") as MockRule:
                        existing_rule = MagicMock()
                        MockRule.objects.filter.return_value.exclude.return_value.first.return_value = existing_rule

                        svc._learn_from_import_correction(
                            candidate=candidate, actual_archive_item_code="l_1", contract_id=1
                        )
                        MockRule.objects.get_or_create.assert_not_called()

    def test_exception_handled(self):
        svc = _make_service()
        candidate = {
            "archive_item_code": "old",
            "suggested_category": "case_material",
            "filename": "test.pdf",
        }

        with patch("apps.contracts.services.contract.integrations.folder_scan_service.Contract") as MockContract:
            MockContract.objects.filter.return_value.values_list.return_value.first.return_value = "litigation"

            with patch("apps.contracts.services.archive.category_mapping.get_archive_category") as mock_cat:
                mock_cat.return_value = "litigation"

                with patch("apps.contracts.services.archive.learning_service.extract_keywords") as mock_kw:
                    mock_kw.return_value = ["test"]

                    with patch("apps.contracts.models.ArchiveClassificationRule") as MockRule:
                        MockRule.objects.filter.side_effect = ValueError("db error")

                        # Should not raise - exception is caught inside the method
                        svc._learn_from_import_correction(
                            candidate=candidate, actual_archive_item_code="l_1", contract_id=1
                        )

    def test_no_contract_type(self):
        svc = _make_service()
        candidate = {
            "archive_item_code": "old",
            "suggested_category": "case_material",
            "filename": "test.pdf",
        }

        with patch("apps.contracts.services.contract.integrations.folder_scan_service.Contract") as MockContract:
            MockContract.objects.filter.return_value.values_list.return_value.first.return_value = None

            with patch("apps.contracts.services.archive.category_mapping.get_archive_category") as mock_cat:
                mock_cat.return_value = "litigation"

                svc._learn_from_import_correction(
                    candidate=candidate, actual_archive_item_code="l_1", contract_id=999999
                )
