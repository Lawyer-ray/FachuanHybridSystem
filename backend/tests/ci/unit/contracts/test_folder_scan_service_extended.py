"""
Extended tests for ContractFolderScanService.

Covers: build_status_payload, _post_process_candidates, _learn_from_import_correction,
_normalize_scan_subfolder, _extract_scan_subfolder, _is_within_root, _relative_path_str,
_normalize_docx_name, get_session, _import_work_log_suggestions.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.contract.integrations.folder_scan_service import (
    ContractFolderScanService,
    _normalize_docx_name,
)
from apps.core.exceptions import NotFoundError, ValidationException

def _make_service():
    return ContractFolderScanService(scan_service=MagicMock())


def _make_processor():
    from apps.contracts.services.contract.integrations._candidate_post_processor import CandidatePostProcessor
    return CandidatePostProcessor(scan_service=MagicMock())


def _make_pipeline():
    from apps.contracts.services.contract.integrations._import_pipeline import ImportPipeline
    return ImportPipeline()


# ═══════════════════════════════════════════════════════════════════════════════
# build_status_payload
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildStatusPayload:
    def test_full_payload(self):
        svc = _make_service()
        session = MagicMock()
        session.id = "sess-1"
        session.status = "completed"
        session.progress = 100
        session.current_file = ""
        session.error_message = ""
        session.result_payload = {
            "summary": {"total_files": 10, "deduped_files": 8, "classified_files": 7},
            "candidates": [{"filename": "test.pdf"}],
            "archive_category": "civil",
            "archive_item_options": [{"code": "c1"}],
            "work_log_suggestions": [{"content": "log1"}],
        }
        result = svc.build_status_payload(session=session)
        assert result["session_id"] == "sess-1"
        assert result["status"] == "completed"
        assert result["progress"] == 100
        assert result["summary"]["total_files"] == 10
        assert result["archive_category"] == "civil"
        assert len(result["archive_item_options"]) == 1
        assert len(result["work_log_suggestions"]) == 1

    def test_none_payload(self):
        svc = _make_service()
        session = MagicMock()
        session.id = "sess-2"
        session.status = "pending"
        session.progress = None
        session.current_file = None
        session.error_message = None
        session.result_payload = None
        result = svc.build_status_payload(session=session)
        assert result["progress"] == 0
        assert result["current_file"] == ""
        assert result["summary"]["total_files"] == 0
        assert result["archive_category"] == ""
        assert result["archive_item_options"] == []

    def test_empty_summary(self):
        svc = _make_service()
        session = MagicMock()
        session.id = "sess-3"
        session.status = "running"
        session.progress = 50
        session.current_file = "file.pdf"
        session.error_message = ""
        session.result_payload = {"summary": {}, "candidates": []}
        result = svc.build_status_payload(session=session)
        assert result["summary"]["total_files"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# get_session
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetSession:
    @patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanSession")
    def test_found(self, MockSession):
        svc = _make_service()
        mock_session = MagicMock()
        MockSession.objects.get.return_value = mock_session
        result = svc.get_session(contract_id=1, session_id="abc")
        assert result == mock_session

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanSession")
    def test_not_found_raises(self, MockSession):
        svc = _make_service()
        MockSession.objects.get.side_effect = Exception("DoesNotExist")
        # The actual code catches ContractFolderScanSession.DoesNotExist
        # which is a subclass of Exception, so we need the real exception
        from apps.contracts.models import ContractFolderScanSession as RealSession
        MockSession.DoesNotExist = RealSession.DoesNotExist
        MockSession.objects.get.side_effect = RealSession.DoesNotExist()
        with pytest.raises(NotFoundError):
            svc.get_session(contract_id=1, session_id="abc")


# ═══════════════════════════════════════════════════════════════════════════════
# _normalize_scan_subfolder
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeScanSubfolderExtended:
    def test_single_dot(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder(".") == ""

    def test_only_slashes_raises(self):
        svc = _make_service()
        with pytest.raises(ValidationException, match="相对路径"):
            svc._normalize_scan_subfolder("///")

    def test_dot_in_middle(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("a/./b") == "a/b"

    def test_backslash_path(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("a\\b\\c") == "a/b/c"

    def test_empty_string(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("") == ""

    def test_none(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder(None) == ""

    def test_absolute_path_raises(self):
        svc = _make_service()
        with pytest.raises(ValidationException, match="相对路径"):
            svc._normalize_scan_subfolder("/etc/passwd")

    def test_dot_dot_raises(self):
        svc = _make_service()
        with pytest.raises(ValidationException, match="非法"):
            svc._normalize_scan_subfolder("a/../b")

    def test_tilde_raises(self):
        svc = _make_service()
        with pytest.raises(ValidationException):
            svc._normalize_scan_subfolder("~/path")

    def test_windows_drive_raises(self):
        svc = _make_service()
        with pytest.raises(ValidationException):
            svc._normalize_scan_subfolder("C:/path")


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_scan_subfolder
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractScanSubfolder:
    def test_present(self):
        svc = _make_service()
        payload = {"scan_scope": {"scan_subfolder": "my_folder"}}
        assert svc._extract_scan_subfolder(payload) == "my_folder"

    def test_missing_key(self):
        svc = _make_service()
        assert svc._extract_scan_subfolder({}) == ""

    def test_none_payload(self):
        svc = _make_service()
        assert svc._extract_scan_subfolder(None) == ""

    def test_whitespace_trimmed(self):
        svc = _make_service()
        payload = {"scan_scope": {"scan_subfolder": "  folder  "}}
        assert svc._extract_scan_subfolder(payload) == "folder"


# ═══════════════════════════════════════════════════════════════════════════════
# _is_within_root
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsWithinRoot:
    def test_child_is_within(self):
        svc = _make_service()
        assert svc._is_within_root(Path("/a/b"), Path("/a/b/c/d")) is True

    def test_same_path(self):
        svc = _make_service()
        assert svc._is_within_root(Path("/a/b"), Path("/a/b")) is True

    def test_outside(self):
        svc = _make_service()
        assert svc._is_within_root(Path("/a/b"), Path("/c/d")) is False

    def test_similar_prefix_not_within(self):
        svc = _make_service()
        assert svc._is_within_root(Path("/a/bc"), Path("/a/bcde")) is False


# ═══════════════════════════════════════════════════════════════════════════════
# _relative_path_str
# ═══════════════════════════════════════════════════════════════════════════════


class TestRelativePathStr:
    def test_nested_file(self):
        svc = _make_processor()
        result = svc._relative_path_str(
            source_path="/a/b/c/file.pdf",
            scan_root=Path("/a/b"),
        )
        assert result == "c"

    def test_direct_child_returns_empty(self):
        svc = _make_processor()
        result = svc._relative_path_str(
            source_path="/a/b/file.pdf",
            scan_root=Path("/a/b"),
        )
        assert result == ""

    def test_deeply_nested(self):
        svc = _make_processor()
        result = svc._relative_path_str(
            source_path="/a/b/c/d/e/file.pdf",
            scan_root=Path("/a/b"),
        )
        assert result == "c/d/e"

    def test_outside_root_returns_empty(self):
        svc = _make_processor()
        result = svc._relative_path_str(
            source_path="/x/y/file.pdf",
            scan_root=Path("/a/b"),
        )
        assert result == ""


# ═══════════════════════════════════════════════════════════════════════════════
# _normalize_docx_name
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeDocxName:
    def test_basic(self):
        assert _normalize_docx_name("文件 名称.docx") == "文件名称.docx"

    def test_empty(self):
        assert _normalize_docx_name("") == ""

    def test_none(self):
        assert _normalize_docx_name(None) == ""

    def test_uppercase(self):
        assert _normalize_docx_name("FILE.DOCX") == "file.docx"

    def test_multiple_spaces(self):
        assert _normalize_docx_name("a  b  c.docx") == "abc.docx"

    def test_tabs(self):
        assert _normalize_docx_name("a\tb.docx") == "ab.docx"


# ═══════════════════════════════════════════════════════════════════════════════
# _post_process_candidates
# ═══════════════════════════════════════════════════════════════════════════════


class TestPostProcessCandidates:
    def _make_service(self):
        from apps.contracts.services.contract.integrations._candidate_post_processor import CandidatePostProcessor
        svc = CandidatePostProcessor(scan_service=MagicMock())
        return svc

    @patch("apps.contracts.services.contract.integrations._candidate_post_processor.classify_archive_material")
    def test_archive_document_with_match(self, mock_classify):
        mock_classify.return_value = {
            "category": "archive_document",
            "archive_item_code": "c1",
            "archive_item_name": "Item 1",
            "confidence": 0.9,
            "reason": "matched",
        }
        svc = self._make_service()
        candidates = [{"suggested_category": "archive_document", "filename": "test.pdf", "source_path": "/root/test.pdf"}]
        with patch.object(svc, "_relative_path_str", return_value=""):
            result = svc.post_process_candidates(
                candidates=candidates,
                archive_category="civil",
                scan_folder="/root",
                contract_id=0,
            )
            assert result[0]["archive_item_code"] == "c1"
            assert result[0]["suggested_category"] == "case_material"

    @patch("apps.contracts.services.contract.integrations._candidate_post_processor.classify_archive_material")
    def test_archive_document_skip(self, mock_classify):
        mock_classify.return_value = {
            "category": "skip",
            "archive_item_code": "",
            "archive_item_name": "",
            "confidence": 0,
            "reason": "skip rule",
        }
        svc = self._make_service()
        candidates = [{"suggested_category": "archive_document", "filename": "保单.pdf", "source_path": "/root/保单.pdf"}]
        with patch.object(svc, "_relative_path_str", return_value=""):
            result = svc.post_process_candidates(
                candidates=candidates,
                archive_category="civil",
                scan_folder="/root",
                contract_id=0,
            )
            assert result[0]["selected"] is False
            assert result[0]["skip_reason"] == "skip rule"

    @patch("apps.contracts.services.contract.integrations._candidate_post_processor.classify_archive_material")
    def test_archive_document_no_match(self, mock_classify):
        mock_classify.return_value = {
            "category": "archive_document",
            "archive_item_code": "",
            "archive_item_name": "",
            "confidence": 0,
            "reason": "no match",
        }
        svc = self._make_service()
        candidates = [{"suggested_category": "archive_document", "filename": "unknown.pdf", "source_path": "/root/unknown.pdf"}]
        with patch.object(svc, "_relative_path_str", return_value=""):
            result = svc.post_process_candidates(
                candidates=candidates,
                archive_category="civil",
                scan_folder="/root",
                contract_id=0,
            )
            assert result[0]["selected"] is False
            assert result[0]["archive_item_name"] == "未匹配"

    @patch("apps.contracts.services.contract.integrations._candidate_post_processor.classify_archive_material")
    def test_authorization_material_with_match(self, mock_classify):
        mock_classify.return_value = {
            "category": "case_material",
            "archive_item_code": "auth_1",
            "archive_item_name": "Auth Item",
            "confidence": 0.8,
            "reason": "matched",
        }
        svc = self._make_service()
        candidates = [{"suggested_category": "authorization_material", "filename": "委托书.pdf", "source_path": "/root/委托书.pdf"}]
        with patch.object(svc, "_relative_path_str", return_value=""):
            result = svc.post_process_candidates(
                candidates=candidates,
                archive_category="civil",
                scan_folder="/root",
                contract_id=0,
            )
            assert result[0]["suggested_category"] == "case_material"
            assert result[0]["archive_item_code"] == "auth_1"

    @patch("apps.contracts.services.contract.integrations._candidate_post_processor.classify_archive_material")
    def test_authorization_material_no_match(self, mock_classify):
        mock_classify.return_value = {
            "category": "case_material",
            "archive_item_code": "",
            "archive_item_name": "",
            "confidence": 0,
            "reason": "no match",
        }
        svc = self._make_service()
        candidates = [{"suggested_category": "authorization_material", "filename": "授权.pdf", "source_path": "/root/授权.pdf"}]
        with patch.object(svc, "_relative_path_str", return_value=""):
            result = svc.post_process_candidates(
                candidates=candidates,
                archive_category="civil",
                scan_folder="/root",
                contract_id=0,
            )
            assert result[0]["selected"] is False

    @patch("apps.contracts.services.contract.integrations._candidate_post_processor.classify_archive_material")
    def test_case_material_with_match(self, mock_classify):
        mock_classify.return_value = {
            "category": "case_material",
            "archive_item_code": "cm_1",
            "archive_item_name": "Case Material",
            "confidence": 0.7,
            "reason": "matched",
        }
        svc = self._make_service()
        candidates = [{"suggested_category": "case_material", "filename": "证据.pdf", "source_path": "/root/证据.pdf"}]
        with patch.object(svc, "_relative_path_str", return_value="sub"):
            result = svc.post_process_candidates(
                candidates=candidates,
                archive_category="civil",
                scan_folder="/root",
                contract_id=0,
            )
            assert result[0]["archive_item_code"] == "cm_1"
            assert result[0]["reason"] == "sub"

    @patch("apps.contracts.services.contract.integrations._candidate_post_processor.classify_archive_material")
    def test_case_material_no_match(self, mock_classify):
        mock_classify.return_value = {
            "category": "case_material",
            "archive_item_code": "",
            "archive_item_name": "",
            "confidence": 0,
            "reason": "no match",
        }
        svc = self._make_service()
        candidates = [{"suggested_category": "case_material", "filename": "misc.pdf", "source_path": "/root/misc.pdf"}]
        with patch.object(svc, "_relative_path_str", return_value=""):
            result = svc.post_process_candidates(
                candidates=candidates,
                archive_category="civil",
                scan_folder="/root",
                contract_id=0,
            )
            assert result[0]["selected"] is False

    def test_baoxian_keyword_deselected(self):
        svc = self._make_service()
        candidates = [
            {"suggested_category": "contract_original", "filename": "保单.pdf", "source_path": "/root/保单.pdf"},
            {"suggested_category": "contract_original", "filename": "保函.pdf", "source_path": "/root/保函.pdf"},
        ]
        with patch("apps.contracts.services.contract.integrations._candidate_post_processor.classify_archive_material") as mock_c:
            mock_c.return_value = {"category": "case_material", "archive_item_code": "", "archive_item_name": "", "confidence": 0, "reason": ""}
            with patch.object(svc, "_relative_path_str", return_value=""):
                result = svc.post_process_candidates(
                    candidates=candidates,
                    archive_category="civil",
                    scan_folder="/root",
                    contract_id=0,
                )
                for c in result:
                    assert c.get("selected") is False

    def test_empty_candidates(self):
        svc = self._make_service()
        with patch.object(svc, "_collect_docx_files", return_value=[]):
            result = svc.post_process_candidates(
                candidates=[],
                archive_category="civil",
                scan_folder="/root",
                contract_id=0,
            )
            assert result == []

    @patch("apps.contracts.services.contract.integrations._candidate_post_processor.classify_archive_material")
    def test_non_litigation_collects_docx(self, mock_classify):
        mock_classify.return_value = {"category": "case_material", "archive_item_code": "", "archive_item_name": "", "confidence": 0, "reason": ""}
        svc = self._make_service()
        with patch.object(svc, "_collect_docx_files", return_value=[{"filename": "修订版.docx"}]) as mock_docx:
            with patch.object(svc, "_relative_path_str", return_value=""):
                with patch.object(svc, "_mark_already_imported"):
                    result = svc.post_process_candidates(
                        candidates=[],
                        archive_category="non_litigation",
                        scan_folder="/root",
                        contract_id=0,
                    )
                    mock_docx.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# _learn_from_import_correction
# ═══════════════════════════════════════════════════════════════════════════════


class TestLearnFromImportCorrection:
    def test_empty_actual_code_skips(self):
        svc = _make_service()
        # Should not raise
        svc._learn_from_import_correction(
            candidate={"archive_item_code": "old", "filename": "test.pdf", "suggested_category": "case_material"},
            actual_archive_item_code="",
            contract_id=1,
        )

    def test_same_code_skips(self):
        svc = _make_service()
        svc._learn_from_import_correction(
            candidate={"archive_item_code": "c1", "filename": "test.pdf", "suggested_category": "case_material"},
            actual_archive_item_code="c1",
            contract_id=1,
        )

    def test_non_case_material_skips(self):
        svc = _make_service()
        svc._learn_from_import_correction(
            candidate={"archive_item_code": "old", "filename": "test.pdf", "suggested_category": "contract_original"},
            actual_archive_item_code="new",
            contract_id=1,
        )

    def test_empty_filename_skips(self):
        svc = _make_service()
        svc._learn_from_import_correction(
            candidate={"archive_item_code": "old", "filename": "", "suggested_category": "case_material"},
            actual_archive_item_code="new",
            contract_id=1,
        )

    @patch("apps.contracts.models.Contract.objects")
    @patch("apps.contracts.models.ArchiveClassificationRule.objects")
    @patch("apps.contracts.services.archive.learning_service.extract_keywords")
    @patch("apps.contracts.services.archive.category_mapping.get_archive_category")
    def test_learns_new_rule(self, mock_cat, mock_keywords, mock_rule_objects, mock_contract_objects):
        mock_keywords.return_value = ["测试"]
        mock_cat.return_value = "civil"
        mock_contract_objects.filter.return_value.values_list.return_value.first.return_value = "civil"
        mock_rule_objects.filter.return_value.exclude.return_value.first.return_value = None
        mock_rule_objects.get_or_create.return_value = (MagicMock(), True)

        svc = _make_service()
        svc._learn_from_import_correction(
            candidate={"archive_item_code": "old", "filename": "测试文件.pdf", "suggested_category": "case_material"},
            actual_archive_item_code="new_code",
            contract_id=1,
        )
        mock_rule_objects.get_or_create.assert_called_once()

    @patch("apps.contracts.models.Contract.objects")
    @patch("apps.contracts.models.ArchiveClassificationRule.objects")
    @patch("apps.contracts.services.archive.learning_service.extract_keywords")
    @patch("apps.contracts.services.archive.category_mapping.get_archive_category")
    def test_skips_ambiguous_keyword(self, mock_cat, mock_keywords, mock_rule_objects, mock_contract_objects):
        mock_keywords.return_value = ["测试"]
        mock_cat.return_value = "civil"
        mock_contract_objects.filter.return_value.values_list.return_value.first.return_value = "civil"
        existing_rule = MagicMock()
        mock_rule_objects.filter.return_value.exclude.return_value.first.return_value = existing_rule

        svc = _make_service()
        svc._learn_from_import_correction(
            candidate={"archive_item_code": "old", "filename": "测试文件.pdf", "suggested_category": "case_material"},
            actual_archive_item_code="new_code",
            contract_id=1,
        )
        mock_rule_objects.get_or_create.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# _import_work_log_suggestions
# ═══════════════════════════════════════════════════════════════════════════════


class TestImportWorkLogSuggestions:
    def test_empty_logs_returns_zero(self):
        svc = _make_pipeline()
        assert svc._import_work_log_suggestions(contract_id=1, confirmed_logs=[]) == 0

    @patch("apps.core.interfaces.ServiceLocator")
    def test_no_cases_returns_zero(self, MockSL):
        MockSL.get_case_service.return_value.get_cases_by_contract.return_value = []
        svc = _make_pipeline()
        assert svc._import_work_log_suggestions(
            contract_id=1,
            confirmed_logs=[{"content": "log entry"}],
        ) == 0

    @patch("apps.cases.models.CaseLog")
    @patch("apps.core.interfaces.ServiceLocator")
    def test_imports_new_logs(self, MockSL, MockCaseLog):
        mock_case = MagicMock()
        mock_case.id = 10
        MockSL.get_case_service.return_value.get_cases_by_contract.return_value = [mock_case]
        MockCaseLog.objects.filter.return_value.values_list.return_value = set()

        svc = _make_pipeline()
        count = svc._import_work_log_suggestions(
            contract_id=1,
            confirmed_logs=[{"content": "第一次开庭"}, {"content": "提交证据"}],
            actor_id=100,
        )
        assert count == 2

    @patch("apps.cases.models.CaseLog")
    @patch("apps.core.interfaces.ServiceLocator")
    def test_skips_duplicate_logs(self, MockSL, MockCaseLog):
        mock_case = MagicMock()
        mock_case.id = 10
        MockSL.get_case_service.return_value.get_cases_by_contract.return_value = [mock_case]
        MockCaseLog.objects.filter.return_value.values_list.return_value = {"第一次开庭"}

        svc = _make_pipeline()
        count = svc._import_work_log_suggestions(
            contract_id=1,
            confirmed_logs=[{"content": "第一次开庭"}],
        )
        assert count == 0

    @patch("apps.cases.models.CaseLog")
    @patch("apps.core.interfaces.ServiceLocator")
    def test_skips_empty_content(self, MockSL, MockCaseLog):
        mock_case = MagicMock()
        mock_case.id = 10
        MockSL.get_case_service.return_value.get_cases_by_contract.return_value = [mock_case]
        MockCaseLog.objects.filter.return_value.values_list.return_value = set()

        svc = _make_pipeline()
        count = svc._import_work_log_suggestions(
            contract_id=1,
            confirmed_logs=[{"content": ""}, {"content": "  "}],
        )
        assert count == 0

    @patch("apps.cases.models.CaseLog")
    @patch("apps.core.interfaces.ServiceLocator")
    def test_handles_creation_exception(self, MockSL, MockCaseLog):
        mock_case = MagicMock()
        mock_case.id = 10
        MockSL.get_case_service.return_value.get_cases_by_contract.return_value = [mock_case]
        MockCaseLog.objects.filter.return_value.values_list.return_value = set()
        MockSL.get_case_service.return_value.create_case_log_internal.side_effect = RuntimeError("db error")

        svc = _make_pipeline()
        count = svc._import_work_log_suggestions(
            contract_id=1,
            confirmed_logs=[{"content": "test log"}],
        )
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# build_status_payload with archive fields
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildStatusPayloadArchiveFields:
    def test_archive_fields_present(self):
        svc = _make_service()
        session = MagicMock()
        session.id = "s1"
        session.status = "completed"
        session.progress = 100
        session.current_file = ""
        session.error_message = ""
        session.result_payload = {
            "summary": {},
            "candidates": [],
            "archive_category": "civil_litigation",
            "archive_item_options": [{"code": "c1", "name": "起诉状"}],
            "work_log_suggestions": [{"content": "开庭"}],
        }
        result = svc.build_status_payload(session=session)
        assert result["archive_category"] == "civil_litigation"
        assert len(result["archive_item_options"]) == 1
        assert len(result["work_log_suggestions"]) == 1
