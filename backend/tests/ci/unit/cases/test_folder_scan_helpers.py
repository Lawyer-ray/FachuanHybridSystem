"""Tests for folder scan service helpers: normalization, scope resolution, classification context."""
from __future__ import annotations

import os
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException


# ── ContractFolderScanService helpers ──


class TestContractFolderScanNormalize:
    """Test _normalize_scan_subfolder from ContractFolderScanService."""

    @pytest.fixture
    def svc(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        return ContractFolderScanService.__new__(ContractFolderScanService)

    def test_empty_string(self, svc):
        assert svc._normalize_scan_subfolder("") == ""

    def test_whitespace_only(self, svc):
        assert svc._normalize_scan_subfolder("   ") == ""

    def test_simple_name(self, svc):
        assert svc._normalize_scan_subfolder("subfolder") == "subfolder"

    def test_nested_path(self, svc):
        assert svc._normalize_scan_subfolder("a/b/c") == "a/b/c"

    def test_backslash_normalized(self, svc):
        assert svc._normalize_scan_subfolder("a\\b") == "a/b"

    def test_leading_slash_raises(self, svc):
        with pytest.raises(ValidationException, match="相对路径"):
            svc._normalize_scan_subfolder("/etc/passwd")

    def test_tilde_raises(self, svc):
        with pytest.raises(ValidationException, match="相对路径"):
            svc._normalize_scan_subfolder("~/secret")

    def test_windows_absolute_raises(self, svc):
        with pytest.raises(ValidationException, match="相对路径"):
            svc._normalize_scan_subfolder("C:/Windows")

    def test_dotdot_raises(self, svc):
        with pytest.raises(ValidationException, match="路径非法"):
            svc._normalize_scan_subfolder("../escape")

    def test_dot_stripped(self, svc):
        assert svc._normalize_scan_subfolder("./folder") == "folder"

    def test_empty_after_cleaning(self, svc):
        assert svc._normalize_scan_subfolder("./.") == ""


class TestContractFolderScanIsWithinRoot:
    @pytest.fixture
    def svc(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        return ContractFolderScanService.__new__(ContractFolderScanService)

    def test_within_root(self, svc):
        root = Path("/data/root")
        target = Path("/data/root/sub")
        assert svc._is_within_root(root, target) is True

    def test_outside_root(self, svc):
        root = Path("/data/root")
        target = Path("/data/other/sub")
        assert svc._is_within_root(root, target) is False

    def test_same_path(self, svc):
        root = Path("/data/root")
        target = Path("/data/root")
        assert svc._is_within_root(root, target) is True


class TestContractFolderScanExtractScanSubfolder:
    @pytest.fixture
    def svc(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        return ContractFolderScanService.__new__(ContractFolderScanService)

    def test_empty_payload(self, svc):
        assert svc._extract_scan_subfolder(None) == ""
        assert svc._extract_scan_subfolder({}) == ""

    def test_with_scan_scope(self, svc):
        payload = {"scan_scope": {"scan_subfolder": "subfolder"}}
        assert svc._extract_scan_subfolder(payload) == "subfolder"


class TestContractFolderScanBuildStatusPayload:
    @pytest.fixture
    def svc(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        return ContractFolderScanService.__new__(ContractFolderScanService)

    def test_build_status_payload(self, svc):
        session = MagicMock()
        session.id = "test-id"
        session.status = "completed"
        session.progress = 100
        session.current_file = ""
        session.error_message = ""
        session.result_payload = {
            "summary": {"total_files": 5, "deduped_files": 3, "classified_files": 2},
            "candidates": [{"filename": "test.pdf"}],
            "archive_category": "litigation",
            "archive_item_options": [],
            "work_log_suggestions": [],
        }

        result = svc.build_status_payload(session=session)
        assert result["session_id"] == "test-id"
        assert result["status"] == "completed"
        assert result["summary"]["total_files"] == 5
        assert len(result["candidates"]) == 1


class TestContractFolderScanRelativePathStr:
    @pytest.fixture
    def svc(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        return ContractFolderScanService.__new__(ContractFolderScanService)

    def test_relative_path(self, svc):
        result = svc._relative_path_str(
            source_path="/data/scan/sub/file.pdf",
            scan_root=Path("/data/scan"),
        )
        assert result == "sub"

    def test_direct_in_root(self, svc):
        result = svc._relative_path_str(
            source_path="/data/scan/file.pdf",
            scan_root=Path("/data/scan"),
        )
        assert result == ""

    def test_invalid_path(self, svc):
        result = svc._relative_path_str(
            source_path="/unrelated/path",
            scan_root=Path("/data/scan"),
        )
        assert result == ""


class TestContractNormalizeDocxName:
    def test_normalize_docx_name(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import _normalize_docx_name
        assert _normalize_docx_name("  修订 版.docx") == "修订版.docx"
        assert _normalize_docx_name("") == ""


# ── CaseFolderScanService helpers ──


class TestCaseFolderScanNormalize:
    @pytest.fixture
    def svc(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        return CaseFolderScanService.__new__(CaseFolderScanService)

    def test_empty(self, svc):
        assert svc._normalize_scan_subfolder("") == ""

    def test_simple(self, svc):
        assert svc._normalize_scan_subfolder("subfolder") == "subfolder"

    def test_raises_absolute(self, svc):
        with pytest.raises(ValidationException, match="相对路径"):
            svc._normalize_scan_subfolder("/absolute")

    def test_raises_dotdot(self, svc):
        with pytest.raises(ValidationException, match="路径非法"):
            svc._normalize_scan_subfolder("../escape")


class TestCaseFolderScanForceOurParty:
    @pytest.fixture
    def svc(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        return CaseFolderScanService.__new__(CaseFolderScanService)

    def test_contains_force_keyword(self, svc):
        assert svc._contains_force_our_party_folder_keyword("/data/立案材料/doc.pdf") is True

    def test_contains_keyword_in_text(self, svc):
        assert svc._contains_force_our_party_folder_keyword("递交给法院的资料") is True

    def test_no_keyword(self, svc):
        assert svc._contains_force_our_party_folder_keyword("/data/普通文件夹") is False

    def test_empty_text(self, svc):
        assert svc._contains_force_our_party_folder_keyword("") is False


class TestCaseFolderScanExtractEnableRecognition:
    @pytest.fixture
    def svc(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        return CaseFolderScanService.__new__(CaseFolderScanService)

    def test_default_true(self, svc):
        assert svc._extract_enable_recognition(None) is True
        assert svc._extract_enable_recognition({}) is True

    def test_explicit_true(self, svc):
        payload = {"scan_options": {"enable_recognition": True}}
        assert svc._extract_enable_recognition(payload) is True

    def test_explicit_false(self, svc):
        payload = {"scan_options": {"enable_recognition": False}}
        assert svc._extract_enable_recognition(payload) is False


class TestCaseFolderScanBuildStatusPayload:
    @pytest.fixture
    def svc(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        return CaseFolderScanService.__new__(CaseFolderScanService)

    def test_build_status_payload(self, svc):
        session = MagicMock()
        session.id = "test-id"
        session.status = "completed"
        session.progress = 100
        session.current_file = ""
        session.error_message = ""
        session.result_payload = {
            "summary": {"total_files": 10, "deduped_files": 8, "classified_files": 5},
            "candidates": [{"filename": "doc.pdf", "source_path": "/data/doc.pdf"}],
            "scan_scope": {"scan_subfolder": "sub"},
            "scan_options": {"enable_recognition": True},
            "stage_result": {"prefill_map": {}},
        }

        result = svc.build_status_payload(session=session)
        assert result["session_id"] == "test-id"
        assert result["scan_subfolder"] == "sub"
        assert result["enable_recognition"] is True


class TestCaseFolderScanToInt:
    @pytest.fixture
    def svc(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        return CaseFolderScanService.__new__(CaseFolderScanService)

    def test_valid_int(self, svc):
        assert svc._to_int(42) == 42

    def test_string_int(self, svc):
        assert svc._to_int("10") == 10

    def test_none(self, svc):
        assert svc._to_int(None) is None

    def test_negative(self, svc):
        assert svc._to_int(-1) is None

    def test_zero(self, svc):
        assert svc._to_int(0) is None

    def test_invalid_string(self, svc):
        assert svc._to_int("abc") is None


class TestCaseFolderScanBuildClassificationContext:
    @pytest.fixture
    def svc(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        return CaseFolderScanService.__new__(CaseFolderScanService)

    def test_build_context_with_parties(self, svc):
        case = MagicMock()
        party1 = MagicMock()
        party1.id = 1
        party1.client.name = "张三"
        party1.client.is_our_client = True

        party2 = MagicMock()
        party2.id = 2
        party2.client.name = "李四"
        party2.client.is_our_client = False

        case.parties.all.return_value = [party1, party2]
        case.supervising_authorities.all.return_value = []

        result = svc._build_classification_context(case)
        assert 1 in result["our_party_ids"]
        assert 2 in result["opponent_party_ids"]
        assert "张三" in result["our_party_names"]
        assert "李四" in result["opponent_party_names"]

    def test_build_context_no_client(self, svc):
        case = MagicMock()
        party = MagicMock()
        party.client = None
        case.parties.all.return_value = [party]
        case.supervising_authorities.all.return_value = []

        result = svc._build_classification_context(case)
        assert result["our_party_ids"] == []
        assert result["opponent_party_ids"] == []


class TestCaseFolderScanShouldForceOurPartyForCandidate:
    @pytest.fixture
    def svc(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        return CaseFolderScanService.__new__(CaseFolderScanService)

    def test_candidate_in_filing_folder(self, svc):
        candidate = {"source_path": "/data/立案材料/doc.pdf"}
        assert svc._should_force_our_party_for_candidate(candidate) is True

    def test_candidate_not_in_filing_folder(self, svc):
        candidate = {"source_path": "/data/普通文件夹/doc.pdf"}
        assert svc._should_force_our_party_for_candidate(candidate) is False

    def test_empty_source_path(self, svc):
        assert svc._should_force_our_party_for_candidate({}) is False
        assert svc._should_force_our_party_for_candidate(None) is False


class TestCaseFolderScanNormalizeCandidates:
    @pytest.fixture
    def svc(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        return CaseFolderScanService.__new__(CaseFolderScanService)

    def test_empty_candidates(self, svc):
        assert svc._normalize_candidates_for_scan_scope([], None) == []

    def test_normal_candidate_not_changed(self, svc):
        candidates = [{"source_path": "/data/doc.pdf", "suggested_category": "unknown"}]
        result = svc._normalize_candidates_for_scan_scope(candidates, None)
        assert result[0]["suggested_category"] == "unknown"

    def test_candidate_in_filing_material_folder(self, svc):
        candidates = [{"source_path": "/data/立案材料/doc.pdf", "suggested_category": "unknown"}]
        result = svc._normalize_candidates_for_scan_scope(candidates, None)
        assert result[0]["suggested_category"] == "party"
        assert result[0]["suggested_side"] == "our"
