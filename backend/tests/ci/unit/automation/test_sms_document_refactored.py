"""
Refactored pure data processing tests for SMSDocumentMixin.

Tests the extracted data transformation / deduplication / path
construction logic that does NOT require database, model instances,
or external service calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.sms._sms_document_mixin import SMSDocumentMixin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _StubSMSDocumentMixin(SMSDocumentMixin):
    """Concrete subclass that overrides abstract properties with mocks."""

    def __init__(self) -> None:
        self._mock_case_number_extractor = MagicMock()
        self._mock_document_attachment = MagicMock()
        self._mock_matcher = MagicMock()
        self._mock_case_folder_archive = MagicMock()

    @property
    def case_number_extractor(self) -> Any:
        return self._mock_case_number_extractor

    @property
    def document_attachment(self) -> Any:
        return self._mock_document_attachment

    @property
    def matcher(self) -> Any:
        return self._mock_matcher

    @property
    def case_folder_archive(self) -> Any:
        return self._mock_case_folder_archive


def _make_mixin() -> _StubSMSDocumentMixin:
    """Create SMSDocumentMixin with mocked dependencies."""
    return _StubSMSDocumentMixin()


# ═══════════════════════════════════════════════════════════════════════════
# dedup_document_paths (extracted from _get_document_paths_for_extraction)
# ═══════════════════════════════════════════════════════════════════════════

class TestDedupDocumentPaths:
    """Test the deduplication logic used in _get_document_paths_for_extraction."""

    @staticmethod
    def dedup_paths(paths: list[str]) -> list[str]:
        """Extracted deduplication logic from _get_document_paths_for_extraction."""
        return list(dict.fromkeys(paths))

    def test_no_duplicates(self) -> None:
        paths = ["/a/b.pdf", "/c/d.pdf"]
        assert self.dedup_paths(paths) == ["/a/b.pdf", "/c/d.pdf"]

    def test_with_duplicates(self) -> None:
        paths = ["/a/b.pdf", "/c/d.pdf", "/a/b.pdf"]
        assert self.dedup_paths(paths) == ["/a/b.pdf", "/c/d.pdf"]

    def test_all_same(self) -> None:
        paths = ["/a/b.pdf", "/a/b.pdf", "/a/b.pdf"]
        assert self.dedup_paths(paths) == ["/a/b.pdf"]

    def test_empty_list(self) -> None:
        assert self.dedup_paths([]) == []

    def test_preserves_order(self) -> None:
        paths = ["/c.pdf", "/a.pdf", "/b.pdf", "/a.pdf", "/c.pdf"]
        result = self.dedup_paths(paths)
        assert result == ["/c.pdf", "/a.pdf", "/b.pdf"]

    def test_single_path(self) -> None:
        assert self.dedup_paths(["/only.pdf"]) == ["/only.pdf"]

    def test_many_duplicates(self) -> None:
        paths = ["/a.pdf"] * 100 + ["/b.pdf"] * 50
        result = self.dedup_paths(paths)
        assert result == ["/a.pdf", "/b.pdf"]


# ═══════════════════════════════════════════════════════════════════════════
# _extract_from_single_document - document update detection
# ═══════════════════════════════════════════════════════════════════════════

class TestExtractFromSingleDocument:
    """Test _extract_from_single_document logic with mocked extractors."""

    def test_extends_case_numbers_when_empty(self) -> None:
        mixin = _make_mixin()
        mixin._mock_case_number_extractor.extract_from_document.return_value = ["（2025）粤001号"]
        mixin._mock_matcher.extract_parties_from_document.return_value = []

        case_numbers: list[str] = []
        party_names: list[str] = []
        result = mixin._extract_from_single_document("/doc.pdf", case_numbers, party_names)

        assert result is True
        assert case_numbers == ["（2025）粤001号"]

    def test_extends_party_names_when_empty(self) -> None:
        mixin = _make_mixin()
        mixin._mock_case_number_extractor.extract_from_document.return_value = []
        mixin._mock_matcher.extract_parties_from_document.return_value = ["张三", "李四"]

        case_numbers: list[str] = []
        party_names: list[str] = []
        result = mixin._extract_from_single_document("/doc.pdf", case_numbers, party_names)

        assert result is True
        assert party_names == ["张三", "李四"]

    def test_no_extraction_when_already_present(self) -> None:
        mixin = _make_mixin()

        case_numbers = ["existing"]
        party_names = ["existing_party"]
        result = mixin._extract_from_single_document("/doc.pdf", case_numbers, party_names)

        assert result is False
        mixin._mock_case_number_extractor.extract_from_document.assert_not_called()
        mixin._mock_matcher.extract_parties_from_document.assert_not_called()

    def test_returns_false_on_exception(self) -> None:
        mixin = _make_mixin()
        mixin._mock_case_number_extractor.extract_from_document.side_effect = RuntimeError("fail")

        result = mixin._extract_from_single_document("/doc.pdf", [], [])
        assert result is False

    def test_extends_both_lists(self) -> None:
        mixin = _make_mixin()
        mixin._mock_case_number_extractor.extract_from_document.return_value = ["CN001"]
        mixin._mock_matcher.extract_parties_from_document.return_value = ["王五"]

        case_numbers: list[str] = []
        party_names: list[str] = []
        result = mixin._extract_from_single_document("/doc.pdf", case_numbers, party_names)

        assert result is True
        assert "CN001" in case_numbers
        assert "王五" in party_names


# ═══════════════════════════════════════════════════════════════════════════
# _save_renamed_paths - result dict construction
# ═══════════════════════════════════════════════════════════════════════════

class TestSaveRenamedPaths:
    """Test _save_renamed_paths result dict construction logic."""

    def test_skips_when_no_renamed_paths(self) -> None:
        mixin = _make_mixin()
        sms = MagicMock()
        mixin._save_renamed_paths(sms, [])
        sms.scraper_task.save.assert_not_called()

    def test_skips_when_no_scraper_task(self) -> None:
        mixin = _make_mixin()
        sms = MagicMock()
        sms.scraper_task = None
        mixin._save_renamed_paths(sms, ["/a.pdf"])

    def test_sets_renamed_files_in_result(self) -> None:
        mixin = _make_mixin()
        sms = MagicMock()
        sms.scraper_task.result = {"existing": "data"}
        mixin._save_renamed_paths(sms, ["/a.pdf", "/b.pdf"])

        assert sms.scraper_task.result["renamed_files"] == ["/a.pdf", "/b.pdf"]
        assert sms.scraper_task.result["existing"] == "data"

    def test_initializes_result_when_none(self) -> None:
        mixin = _make_mixin()
        sms = MagicMock()
        sms.scraper_task.result = None
        mixin._save_renamed_paths(sms, ["/a.pdf"])

        assert sms.scraper_task.result["renamed_files"] == ["/a.pdf"]

    def test_replaces_non_dict_result(self) -> None:
        mixin = _make_mixin()
        sms = MagicMock()
        sms.scraper_task.result = "invalid"
        mixin._save_renamed_paths(sms, ["/a.pdf"])

        assert sms.scraper_task.result == {"renamed_files": ["/a.pdf"]}


# ═══════════════════════════════════════════════════════════════════════════
# _sync_party_names_from_documents - skip logic
# ═══════════════════════════════════════════════════════════════════════════

class TestSyncPartyNamesLogic:
    """Test the skip logic in _sync_party_names_from_documents."""

    def test_skips_when_no_renamed_paths(self) -> None:
        mixin = _make_mixin()
        sms = MagicMock()
        sms.party_names = []
        mixin._sync_party_names_from_documents(sms, [])
        mixin._mock_matcher.extract_parties_from_document.assert_not_called()

    def test_skips_when_already_has_parties(self) -> None:
        mixin = _make_mixin()
        sms = MagicMock()
        sms.party_names = ["existing"]
        mixin._sync_party_names_from_documents(sms, ["/a.pdf"])
        mixin._mock_matcher.extract_parties_from_document.assert_not_called()
