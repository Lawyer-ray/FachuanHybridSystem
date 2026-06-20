"""合同/案件文件夹扫描服务测试。"""

from unittest.mock import MagicMock, patch

import pytest

from apps.cases.services.material.folder_scan_service import CaseFolderScanService
from apps.contracts.services.contract.integrations.folder_scan_service import (
    ContractFolderScanService,
    _normalize_docx_name,
)


class TestContractFolderScanServiceHelpers:
    """ContractFolderScanService 辅助方法测试。"""

    def _make_service(self):
        return ContractFolderScanService(scan_service=MagicMock())

    def _make_processor(self):
        from apps.contracts.services.contract.integrations._candidate_post_processor import CandidatePostProcessor
        return CandidatePostProcessor(scan_service=MagicMock())

    # ── _normalize_scan_subfolder ──

    def test_normalize_empty(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("") == ""

    def test_normalize_whitespace(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("  ") == ""

    def test_normalize_valid_relative(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("subfolder") == "subfolder"

    def test_normalize_multi_segment(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("a/b/c") == "a/b/c"

    def test_normalize_backslash(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("a\\b") == "a/b"

    def test_normalize_absolute_raises(self):
        svc = self._make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException):
            svc._normalize_scan_subfolder("/absolute")

    def test_normalize_tilde_raises(self):
        svc = self._make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException):
            svc._normalize_scan_subfolder("~/path")

    def test_normalize_windows_path_raises(self):
        svc = self._make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException):
            svc._normalize_scan_subfolder("C:/path")

    def test_normalize_dotdot_raises(self):
        svc = self._make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException):
            svc._normalize_scan_subfolder("../escape")

    def test_normalize_dot_filtered(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("a/./b") == "a/b"

    def test_normalize_double_slash(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("a//b") == "a/b"

    # ── _extract_scan_subfolder ──

    def test_extract_scan_subfolder_from_payload(self):
        svc = self._make_service()
        payload = {"scan_scope": {"scan_subfolder": "test_folder"}}
        assert svc._extract_scan_subfolder(payload) == "test_folder"

    def test_extract_scan_subfolder_none_payload(self):
        svc = self._make_service()
        assert svc._extract_scan_subfolder(None) == ""

    def test_extract_scan_subfolder_empty_payload(self):
        svc = self._make_service()
        assert svc._extract_scan_subfolder({}) == ""

    # ── _is_within_root ──

    def test_is_within_root_true(self):
        svc = self._make_service()
        from pathlib import Path
        assert svc._is_within_root(Path("/a/b"), Path("/a/b/c")) is True

    def test_is_within_root_false(self):
        svc = self._make_service()
        from pathlib import Path
        assert svc._is_within_root(Path("/a/b"), Path("/c/d")) is False

    # ── _relative_path_str ──

    def test_relative_path_str(self):
        svc = self._make_processor()
        from pathlib import Path
        result = svc._relative_path_str(
            source_path="/a/b/c/file.pdf",
            scan_root=Path("/a/b"),
        )
        assert result == "c"

    def test_relative_path_str_root_file(self):
        svc = self._make_processor()
        from pathlib import Path
        result = svc._relative_path_str(
            source_path="/a/b/file.pdf",
            scan_root=Path("/a/b"),
        )
        assert result == ""

    # ── build_status_payload ──

    def test_build_status_payload(self):
        svc = self._make_service()
        session = MagicMock()
        session.id = "test-id"
        session.status = "completed"
        session.progress = 100
        session.current_file = ""
        session.result_payload = {
            "summary": {"total_files": 5, "deduped_files": 3, "classified_files": 3},
            "candidates": [{"name": "test.pdf"}],
        }
        session.error_message = ""
        result = svc.build_status_payload(session=session)
        assert result["session_id"] == "test-id"
        assert result["status"] == "completed"
        assert result["summary"]["total_files"] == 5

    def test_build_status_payload_none_values(self):
        svc = self._make_service()
        session = MagicMock()
        session.id = "test-id"
        session.status = "pending"
        session.progress = None
        session.current_file = None
        session.result_payload = None
        session.error_message = None
        result = svc.build_status_payload(session=session)
        assert result["progress"] == 0
        assert result["current_file"] == ""


class TestCaseFolderScanServiceHelpers:
    """CaseFolderScanService 辅助方法测试。"""

    def _make_service(self):
        return CaseFolderScanService(scan_service=MagicMock())

    # ── _normalize_scan_subfolder ──

    def test_normalize_empty(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("") == ""

    def test_normalize_valid(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("subfolder") == "subfolder"

    def test_normalize_absolute_raises(self):
        svc = self._make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException):
            svc._normalize_scan_subfolder("/absolute")

    def test_normalize_dotdot_raises(self):
        svc = self._make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException):
            svc._normalize_scan_subfolder("../escape")

    # ── _to_int ──

    def test_to_int_valid(self):
        assert CaseFolderScanService._to_int("5") == 5

    def test_to_int_negative(self):
        assert CaseFolderScanService._to_int(-1) is None

    def test_to_int_zero(self):
        assert CaseFolderScanService._to_int(0) is None

    def test_to_int_none(self):
        assert CaseFolderScanService._to_int(None) is None

    def test_to_int_invalid(self):
        assert CaseFolderScanService._to_int("abc") is None

    # ── _contains_force_our_party_folder_keyword ──

    def test_contains_force_keyword_filing(self):
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("/path/立案材料/sub") is True

    def test_contains_force_keyword_court_submission(self):
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("递交给法院的资料") is True

    def test_contains_force_keyword_none(self):
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("") is False

    def test_contains_force_keyword_no_match(self):
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("/random/path") is False

    # ── _should_force_our_party_for_filing_materials ──

    def test_should_force_for_filing_in_scan_subfolder(self):
        svc = self._make_service()
        payload = {"scan_scope": {"scan_subfolder": "立案材料", "scan_folder": "/root"}}
        assert svc._should_force_our_party_for_filing_materials(payload) is True

    def test_should_force_for_filing_none(self):
        svc = self._make_service()
        assert svc._should_force_our_party_for_filing_materials(None) is False

    def test_should_force_for_filing_no_match(self):
        svc = self._make_service()
        payload = {"scan_scope": {"scan_subfolder": "random", "scan_folder": "/root"}}
        assert svc._should_force_our_party_for_filing_materials(payload) is False

    # ── _should_force_our_party_for_candidate ──

    def test_should_force_for_candidate_match(self):
        svc = self._make_service()
        candidate = {"source_path": "/path/立案材料/file.pdf"}
        assert svc._should_force_our_party_for_candidate(candidate) is True

    def test_should_force_for_candidate_no_match(self):
        svc = self._make_service()
        candidate = {"source_path": "/random/path/file.pdf"}
        assert svc._should_force_our_party_for_candidate(candidate) is False

    def test_should_force_for_candidate_none(self):
        svc = self._make_service()
        assert svc._should_force_our_party_for_candidate(None) is False

    # ── _normalize_candidates_for_scan_scope ──

    def test_normalize_candidates_force_our(self):
        svc = self._make_service()
        candidates = [{"source_path": "/path/file.pdf", "suggested_category": "unknown"}]
        payload = {"scan_scope": {"scan_subfolder": "立案材料", "scan_folder": "/root"}}
        result = svc._normalize_candidates_for_scan_scope(candidates, payload)
        assert result[0]["suggested_category"] == "party"
        assert result[0]["suggested_side"] == "our"

    def test_normalize_candidates_empty(self):
        svc = self._make_service()
        assert svc._normalize_candidates_for_scan_scope([], {}) == []

    def test_normalize_candidates_no_force(self):
        svc = self._make_service()
        candidates = [{"source_path": "/random/file.pdf", "suggested_category": "unknown"}]
        payload = {"scan_scope": {"scan_subfolder": "", "scan_folder": "/root"}}
        result = svc._normalize_candidates_for_scan_scope(candidates, payload)
        assert result[0]["suggested_category"] == "unknown"

    # ── _extract_scan_subfolder ──

    def test_extract_scan_subfolder(self):
        svc = self._make_service()
        payload = {"scan_scope": {"scan_subfolder": "test"}}
        assert svc._extract_scan_subfolder(payload) == "test"

    def test_extract_scan_subfolder_empty(self):
        svc = self._make_service()
        assert svc._extract_scan_subfolder({}) == ""

    # ── _extract_enable_recognition ──

    def test_extract_enable_recognition_true(self):
        svc = self._make_service()
        payload = {"scan_options": {"enable_recognition": True}}
        assert svc._extract_enable_recognition(payload) is True

    def test_extract_enable_recognition_false(self):
        svc = self._make_service()
        payload = {"scan_options": {"enable_recognition": False}}
        assert svc._extract_enable_recognition(payload) is False

    def test_extract_enable_recognition_default(self):
        svc = self._make_service()
        assert svc._extract_enable_recognition({}) is True

    # ── _build_materials_url ──

    def test_build_materials_url(self):
        from uuid import uuid4
        url = CaseFolderScanService._build_materials_url(case_id=1, session_id=uuid4())
        assert "scan_session" in url
        assert "open_scan" in url


class TestNormalizeDocxName:
    """_normalize_docx_name 测试。"""

    def test_normalize_basic(self):
        assert _normalize_docx_name("文件 名称.docx") == "文件名称.docx"

    def test_normalize_empty(self):
        assert _normalize_docx_name("") == ""

    def test_normalize_none(self):
        assert _normalize_docx_name(None) == ""

    def test_normalize_lower(self):
        assert _normalize_docx_name("FILE.DOCX") == "file.docx"
