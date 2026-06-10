"""Tests for CaseFolderScanService - pure logic methods."""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from apps.cases.services.material.folder_scan_service import CaseFolderScanService


class TestNormalizeScanSubfolder:
    def setup_method(self):
        self.service = CaseFolderScanService(scan_service=MagicMock())

    def test_empty_string(self):
        assert self.service._normalize_scan_subfolder("") == ""

    def test_none(self):
        assert self.service._normalize_scan_subfolder(None) == ""

    def test_relative_path(self):
        assert self.service._normalize_scan_subfolder("subfolder") == "subfolder"

    def test_nested_relative_path(self):
        assert self.service._normalize_scan_subfolder("a/b/c") == "a/b/c"

    def test_backslash_normalized(self):
        assert self.service._normalize_scan_subfolder("a\\b\\c") == "a/b/c"

    def test_absolute_path_raises(self):
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException):
            self.service._normalize_scan_subfolder("/absolute/path")

    def test_tilde_path_raises(self):
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException):
            self.service._normalize_scan_subfolder("~/home/path")

    def test_windows_path_raises(self):
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException):
            self.service._normalize_scan_subfolder("C:/windows/path")

    def test_dotdot_raises(self):
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException):
            self.service._normalize_scan_subfolder("../escape")

    def test_dot_segments_removed(self):
        assert self.service._normalize_scan_subfolder("a/./b") == "a/b"

    def test_empty_segments_filtered(self):
        assert self.service._normalize_scan_subfolder("a//b") == "a/b"

    def test_only_dots(self):
        assert self.service._normalize_scan_subfolder("./.") == ""

    def test_whitespace(self):
        assert self.service._normalize_scan_subfolder("  valid  ") == "valid"


class TestIsWithinRoot:
    def setup_method(self):
        self.service = CaseFolderScanService(scan_service=MagicMock())

    def test_within_root(self):
        root = Path("/a/b")
        target = Path("/a/b/c")
        assert self.service._is_within_root(root, target) is True

    def test_outside_root(self):
        root = Path("/a/b")
        target = Path("/x/y")
        assert self.service._is_within_root(root, target) is False

    def test_same_path(self):
        root = Path("/a/b")
        assert self.service._is_within_root(root, root) is True


class TestToNormalizeCandidates:
    def setup_method(self):
        self.service = CaseFolderScanService(scan_service=MagicMock())

    def test_empty_candidates(self):
        result = self.service._normalize_candidates_for_scan_scope([], {})
        assert result == []

    def test_force_our_party_for_filing_materials(self):
        payload = {"scan_scope": {"scan_subfolder": "立案材料"}}
        candidates = [{"source_path": "/test.pdf", "suggested_category": "unknown"}]
        result = self.service._normalize_candidates_for_scan_scope(candidates, payload)
        assert result[0]["suggested_category"] == "party"
        assert result[0]["suggested_side"] == "our"

    def test_force_for_candidate_path(self):
        candidates = [{"source_path": "/data/递交给法院的资料/test.pdf"}]
        result = self.service._normalize_candidates_for_scan_scope(candidates, None)
        assert result[0]["suggested_category"] == "party"
        assert result[0]["suggested_side"] == "our"

    def test_no_force_for_normal(self):
        candidates = [{"source_path": "/normal/test.pdf", "suggested_category": "other"}]
        result = self.service._normalize_candidates_for_scan_scope(candidates, None)
        assert result[0]["suggested_category"] == "other"


class TestContainsForceOurPartyFolderKeyword:
    def test_filing_materials(self):
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("立案材料") is True

    def test_submit_to_court(self):
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("递交给法院的资料") is True

    def test_submit_to_court_alt(self):
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("提交给法院的资料") is True

    def test_normal_text(self):
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("一般文件夹") is False

    def test_empty_string(self):
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("") is False

    def test_none(self):
        assert CaseFolderScanService._contains_force_our_party_folder_keyword(None) is False


class TestShouldForceOurParty:
    def setup_method(self):
        self.service = CaseFolderScanService(scan_service=MagicMock())

    def test_force_for_filing_scope(self):
        payload = {"scan_scope": {"scan_subfolder": "立案材料", "scan_folder": "/root/立案材料"}}
        assert self.service._should_force_our_party_for_filing_materials(payload) is True

    def test_no_force_for_normal_scope(self):
        payload = {"scan_scope": {"scan_subfolder": "普通文件夹"}}
        assert self.service._should_force_our_party_for_filing_materials(payload) is False

    def test_force_for_candidate(self):
        candidate = {"source_path": "/path/立案材料/file.pdf"}
        assert self.service._should_force_our_party_for_candidate(candidate) is True

    def test_no_force_for_normal_candidate(self):
        candidate = {"source_path": "/path/normal/file.pdf"}
        assert self.service._should_force_our_party_for_candidate(candidate) is False

    def test_no_force_for_empty_path(self):
        candidate = {"source_path": ""}
        assert self.service._should_force_our_party_for_candidate(candidate) is False

    def test_no_force_for_none(self):
        assert self.service._should_force_our_party_for_candidate(None) is False


class TestExtractScanSubfolder:
    def setup_method(self):
        self.service = CaseFolderScanService(scan_service=MagicMock())

    def test_with_scan_scope(self):
        payload = {"scan_scope": {"scan_subfolder": "sub"}}
        assert self.service._extract_scan_subfolder(payload) == "sub"

    def test_empty_payload(self):
        assert self.service._extract_scan_subfolder({}) == ""

    def test_none_payload(self):
        assert self.service._extract_scan_subfolder(None) == ""


class TestExtractEnableRecognition:
    def setup_method(self):
        self.service = CaseFolderScanService(scan_service=MagicMock())

    def test_enabled(self):
        payload = {"scan_options": {"enable_recognition": True}}
        assert self.service._extract_enable_recognition(payload) is True

    def test_disabled(self):
        payload = {"scan_options": {"enable_recognition": False}}
        assert self.service._extract_enable_recognition(payload) is False

    def test_missing_defaults_true(self):
        assert self.service._extract_enable_recognition({}) is True

    def test_none_payload(self):
        assert self.service._extract_enable_recognition(None) is True


class TestToInt:
    def test_valid_int(self):
        assert CaseFolderScanService._to_int(5) == 5

    def test_string_int(self):
        assert CaseFolderScanService._to_int("10") == 10

    def test_negative_returns_none(self):
        assert CaseFolderScanService._to_int(-1) is None

    def test_zero_returns_none(self):
        assert CaseFolderScanService._to_int(0) is None

    def test_none_returns_none(self):
        assert CaseFolderScanService._to_int(None) is None

    def test_invalid_string(self):
        assert CaseFolderScanService._to_int("abc") is None


class TestBuildStatusPayload:
    def setup_method(self):
        self.service = CaseFolderScanService(scan_service=MagicMock())

    def test_basic_payload(self):
        session = MagicMock()
        session.id = "test-id"
        session.status = "completed"
        session.progress = 100
        session.current_file = ""
        session.error_message = ""
        session.result_payload = {
            "summary": {"total_files": 10, "deduped_files": 8, "classified_files": 7},
            "candidates": [{"source_path": "/a.pdf"}],
            "scan_scope": {"scan_subfolder": ""},
            "scan_options": {"enable_recognition": True},
        }

        result = self.service.build_status_payload(session=session)
        assert result["session_id"] == "test-id"
        assert result["status"] == "completed"
        assert result["progress"] == 100
        assert result["summary"]["total_files"] == 10
        assert result["scan_subfolder"] == ""
        assert result["enable_recognition"] is True

    def test_empty_payload(self):
        session = MagicMock()
        session.id = "test-id"
        session.status = "pending"
        session.progress = 0
        session.current_file = ""
        session.error_message = ""
        session.result_payload = None

        result = self.service.build_status_payload(session=session)
        assert result["summary"]["total_files"] == 0
        assert result["candidates"] == []


class TestMakeProviderForBinding:
    def setup_method(self):
        self.service = CaseFolderScanService(scan_service=MagicMock())

    def test_local_returns_none(self):
        binding = MagicMock()
        binding.storage_type = "local"
        result = self.service._make_provider_for_binding(binding)
        assert result is None


class TestResolveScanScope:
    def setup_method(self):
        self.service = CaseFolderScanService(scan_service=MagicMock())

    def test_local_root_only(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.service._resolve_scan_scope(tmpdir, "")
            assert result["scan_subfolder"] == ""
            assert result["root_folder"]
            assert result["scan_folder"]

    def test_local_subfolder(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            sub = Path(tmpdir) / "subdir"
            sub.mkdir()
            result = self.service._resolve_scan_scope(tmpdir, "subdir")
            assert result["scan_subfolder"] == "subdir"

    def test_local_subfolder_traversal_blocked(self):
        import tempfile
        from apps.core.exceptions import ValidationException

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValidationException, match="路径非法"):
                self.service._resolve_scan_scope(tmpdir, "../escape")

    def test_local_subfolder_not_exist(self):
        import tempfile
        from apps.core.exceptions import ValidationException

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValidationException, match="不可访问"):
                self.service._resolve_scan_scope(tmpdir, "nonexistent")

    def test_cloud_storage_subfolder(self):
        provider = MagicMock()
        provider.exists.return_value = True
        result = self.service._resolve_scan_scope("/cloud/root", "sub", storage_provider=provider)
        assert result["scan_subfolder"] == "sub"
        provider.exists.assert_called()

    def test_cloud_storage_traversal_blocked(self):
        from apps.core.exceptions import ValidationException

        provider = MagicMock()
        with pytest.raises(ValidationException, match="路径非法"):
            self.service._resolve_scan_scope("/cloud/root", "../escape", storage_provider=provider)

    def test_cloud_storage_not_exist(self):
        from apps.core.exceptions import ValidationException

        provider = MagicMock()
        provider.exists.return_value = False
        with pytest.raises(ValidationException, match="不可访问"):
            self.service._resolve_scan_scope("/cloud/root", "sub", storage_provider=provider)


class TestBuildClassificationContext:
    def setup_method(self):
        self.service = CaseFolderScanService(scan_service=MagicMock())

    def test_basic_context(self):
        case = MagicMock()
        party1 = MagicMock()
        party1.id = 1
        party1.client.name = "我方客户"
        party1.client.is_our_client = True

        party2 = MagicMock()
        party2.id = 2
        party2.client.name = "对方"
        party2.client.is_our_client = False

        case.parties.all.return_value = [party1, party2]
        case.supervising_authorities.all.return_value = []

        result = self.service._build_classification_context(case)
        assert 1 in result["our_party_ids"]
        assert 2 in result["opponent_party_ids"]
        assert "我方客户" in result["our_party_names"]
        assert "对方" in result["opponent_party_names"]
