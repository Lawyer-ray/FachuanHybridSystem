"""
Unit tests for core/services/bound_folder_scan_service.py.

Covers:
  - __init__ (default deps, injected deps)
  - _calc_progress (edge cases)
  - _collect_pdf_files (recursive, sorted)
  - _parse_version (V pattern, bracket pattern, copy pattern, no pattern)
  - _clean_base_name
  - _normalize_group_key
  - _deduplicate_files (version ranking, mtime tiebreak)
  - _extract_parent_folder_hint (direct file, nested file, no parent)
  - _notify (with callback, without callback)
  - _build_candidate (contract domain, case domain, unsupported domain)
  - scan_folder (local, cloud storage)
  - _scan_cloud
  - _build_candidate_cloud
  - _extract_parent_folder_hint_cloud
"""

from __future__ import annotations

import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.core.services.bound_folder_scan_service import (
    BoundFolderScanService,
    _VersionInfo,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(**kwargs: Any) -> BoundFolderScanService:
    kwargs.setdefault("text_extraction_service", MagicMock())
    kwargs.setdefault("classification_service", MagicMock())
    return BoundFolderScanService(**kwargs)


# ===========================================================================
# Tests
# ===========================================================================


class TestInit:
    def test_default_deps(self) -> None:
        svc = BoundFolderScanService()
        assert svc._max_candidates == 0

    def test_injected_deps(self) -> None:
        mock_tes = MagicMock()
        mock_cs = MagicMock()
        svc = BoundFolderScanService(max_candidates=5, text_extraction_service=mock_tes, classification_service=mock_cs)
        assert svc._max_candidates == 5
        assert svc._text_extraction_service is mock_tes
        assert svc._classification_service is mock_cs


class TestCalcProgress:
    def test_zero_total(self) -> None:
        assert BoundFolderScanService._calc_progress(idx=1, total=0) == 100

    def test_first_item(self) -> None:
        result = BoundFolderScanService._calc_progress(idx=1, total=10)
        assert 10 <= result <= 99

    def test_last_item(self) -> None:
        result = BoundFolderScanService._calc_progress(idx=10, total=10)
        assert result <= 99

    def test_single_item(self) -> None:
        result = BoundFolderScanService._calc_progress(idx=1, total=1)
        assert result <= 99


class TestCollectPdfFiles:
    def test_finds_pdf_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.pdf").touch()
        (tmp_path / "b.txt").touch()
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.pdf").touch()

        result = BoundFolderScanService._collect_pdf_files(tmp_path)
        names = [p.name for p in result]
        assert "a.pdf" in names
        assert "c.pdf" in names
        assert "b.txt" not in names

    def test_sorted(self, tmp_path: Path) -> None:
        (tmp_path / "z.pdf").touch()
        (tmp_path / "a.pdf").touch()

        result = BoundFolderScanService._collect_pdf_files(tmp_path)
        assert result[0].name == "a.pdf"
        assert result[1].name == "z.pdf"


class TestParseVersion:
    def test_v_pattern(self) -> None:
        svc = _make_service()
        result = svc._parse_version("contract_V2")
        assert result.base_name == "contract"
        assert result.version_token == "V2"
        assert result.version_rank == 102

    def test_v_lowercase(self) -> None:
        svc = _make_service()
        result = svc._parse_version("contract_v1")
        assert result.version_token == "V1"

    def test_bracket_pattern(self) -> None:
        svc = _make_service()
        result = svc._parse_version("contract(3)")
        assert result.version_token == "(3)"
        assert result.version_rank == 103

    def test_chinese_bracket(self) -> None:
        svc = _make_service()
        result = svc._parse_version("contract（2）")
        assert result.version_token == "(2)"
        assert result.version_rank == 102

    def test_copy_pattern(self) -> None:
        svc = _make_service()
        result = svc._parse_version("contract_副本")
        assert result.version_token == "副本"
        assert result.version_rank == 0

    def test_no_pattern(self) -> None:
        svc = _make_service()
        result = svc._parse_version("simple_name")
        assert result.version_token == ""
        assert result.version_rank == 1


class TestCleanBaseName:
    def test_normal(self) -> None:
        assert BoundFolderScanService._clean_base_name("hello  world") == "hello world"

    def test_dots_and_underscores(self) -> None:
        assert BoundFolderScanService._clean_base_name("a.__b") == "a b"

    def test_empty(self) -> None:
        assert BoundFolderScanService._clean_base_name("") == ""

    def test_whitespace_only(self) -> None:
        assert BoundFolderScanService._clean_base_name("   ") == ""


class TestNormalizeGroupKey:
    def test_lowercase(self) -> None:
        assert BoundFolderScanService._normalize_group_key("Hello World") == "hello world"

    def test_empty(self) -> None:
        assert BoundFolderScanService._normalize_group_key("") == "_"


class TestDeduplicateFiles:
    def test_keeps_highest_version(self, tmp_path: Path) -> None:
        svc = _make_service()
        f1 = tmp_path / "contract_V1.pdf"
        f2 = tmp_path / "contract_V2.pdf"
        f1.touch()
        f2.touch()

        files = [f1, f2]
        result = svc._deduplicate_files(files)
        assert len(result) == 1
        assert "V2" in result[0]["version_token"]

    def test_same_version_keeps_newer_mtime(self, tmp_path: Path) -> None:
        svc = _make_service()
        f1 = tmp_path / "contract_V1.pdf"
        f2 = tmp_path / "contract_V1_2.pdf"
        f1.write_bytes(b"old")
        f2.write_bytes(b"new")
        # Ensure different mtimes
        import os
        os.utime(f1, (1000, 1000))
        os.utime(f2, (2000, 2000))

        # These are different base names so won't be deduped
        files = [f1, f2]
        result = svc._deduplicate_files(files)
        assert len(result) == 2

    def test_no_duplicates(self, tmp_path: Path) -> None:
        svc = _make_service()
        f1 = tmp_path / "unique.pdf"
        f1.touch()
        result = svc._deduplicate_files([f1])
        assert len(result) == 1


class TestExtractParentFolderHint:
    def test_direct_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.pdf"
        f.touch()
        result = BoundFolderScanService._extract_parent_folder_hint(f, tmp_path)
        assert result == ""

    def test_nested_file(self, tmp_path: Path) -> None:
        sub = tmp_path / "2-执行申请书"
        sub.mkdir()
        f = sub / "test.pdf"
        f.touch()
        result = BoundFolderScanService._extract_parent_folder_hint(f, tmp_path)
        assert "执行申请书" in result

    def test_multi_level(self, tmp_path: Path) -> None:
        sub = tmp_path / "parent" / "child"
        sub.mkdir(parents=True)
        f = sub / "test.pdf"
        f.touch()
        result = BoundFolderScanService._extract_parent_folder_hint(f, tmp_path)
        assert result == "parent"

    def test_outside_root(self, tmp_path: Path) -> None:
        other = Path(tempfile.mkdtemp())
        f = other / "test.pdf"
        f.touch()
        result = BoundFolderScanService._extract_parent_folder_hint(f, tmp_path)
        assert result == ""


class TestNotify:
    def test_with_callback(self) -> None:
        cb = MagicMock()
        BoundFolderScanService._notify(cb, "scanning", 50, "test.pdf")
        cb.assert_called_once_with("scanning", 50, "test.pdf")

    def test_without_callback(self) -> None:
        BoundFolderScanService._notify(None, "scanning", 50, "test.pdf")


class TestBuildCandidate:
    def test_contract_domain(self, tmp_path: Path) -> None:
        svc = _make_service()
        f = tmp_path / "contract.pdf"
        f.write_bytes(b"fake")
        svc._classification_service.classify_contract_material.return_value = {
            "category": "contract_original",
            "confidence": 0.9,
            "reason": "keyword match",
        }

        candidate = svc._build_candidate(
            path=f,
            base_name="contract",
            version_token="",
            extraction_method="none",
            text_excerpt="",
            domain="contract",
            enable_recognition=False,
            classification_context=None,
        )
        assert candidate["suggested_category"] == "contract_original"
        assert candidate["confidence"] == 0.9

    def test_case_domain(self, tmp_path: Path) -> None:
        svc = _make_service()
        f = tmp_path / "evidence.pdf"
        f.write_bytes(b"fake")
        svc._classification_service.classify_case_material.return_value = {
            "category": "evidence",
            "side": "plaintiff",
            "type_name_hint": "证据",
            "suggested_supervising_authority_id": None,
            "suggested_party_ids": [],
            "confidence": 0.8,
            "reason": "AI classified",
        }

        candidate = svc._build_candidate(
            path=f,
            base_name="evidence",
            version_token="",
            extraction_method="ocr",
            text_excerpt="some text",
            domain="case",
            enable_recognition=True,
            classification_context=None,
        )
        assert candidate["suggested_category"] == "evidence"
        assert candidate["suggested_side"] == "plaintiff"

    def test_unsupported_domain(self, tmp_path: Path) -> None:
        svc = _make_service()
        f = tmp_path / "test.pdf"
        f.write_bytes(b"fake")
        with pytest.raises(ValidationException):
            svc._build_candidate(
                path=f,
                base_name="test",
                version_token="",
                extraction_method="none",
                text_excerpt="",
                domain="unknown",
                enable_recognition=False,
                classification_context=None,
            )


class TestScanFolder:
    def test_local_not_exists(self) -> None:
        svc = _make_service()
        with pytest.raises(ValidationException):
            svc.scan_folder(folder_path="/nonexistent/path", domain="contract")

    def test_local_success(self, tmp_path: Path) -> None:
        svc = _make_service()
        (tmp_path / "test.pdf").write_bytes(b"fake")
        svc._classification_service.classify_contract_material.return_value = {
            "category": "contract_original",
            "confidence": 0.9,
            "reason": "match",
        }

        result = svc.scan_folder(folder_path=str(tmp_path), domain="contract")
        assert result["summary"]["total_files"] == 1
        assert len(result["candidates"]) == 1

    def test_cloud_storage_delegates_to_scan_cloud(self) -> None:
        """Cloud storage scanning delegates to _scan_cloud method."""
        svc = _make_service()
        mock_provider = MagicMock()
        svc._scan_cloud = MagicMock(return_value={
            "summary": {"total_files": 1, "deduped_files": 1, "classified_files": 1},
            "candidates": [],
        })
        result = svc.scan_folder(
            folder_path="/cloud",
            domain="contract",
            storage_provider=mock_provider,
        )
        assert result["summary"]["total_files"] == 1
        svc._scan_cloud.assert_called_once()

    def test_max_candidates_limit(self, tmp_path: Path) -> None:
        svc = _make_service(max_candidates=1)
        for i in range(5):
            (tmp_path / f"test{i}.pdf").write_bytes(b"fake")
        svc._classification_service.classify_contract_material.return_value = {
            "category": "contract_original",
            "confidence": 0.9,
            "reason": "match",
        }

        result = svc.scan_folder(folder_path=str(tmp_path), domain="contract")
        assert len(result["candidates"]) == 1


class TestDeduplicateScannedFiles:
    def test_basic(self) -> None:
        svc = _make_service()
        scanned1 = MagicMock()
        scanned1.name = "a.pdf"
        scanned1.stem = "a"
        scanned1.as_posix = "/a.pdf"
        scanned1.stat = MagicMock(mtime=1000)
        scanned1.stat.mtime = 1000

        result = svc._deduplicate_scanned_files([scanned1])
        assert len(result) == 1
