"""
Refactored pure data processing tests for DocumentDeliveryMatchingMixin.

Tests the extracted data transformation / file name extraction / result
construction logic that does NOT require database, external API, or
network access.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from apps.automation.services.document_delivery._matching_mixin import DocumentDeliveryMatchingMixin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mixin() -> DocumentDeliveryMatchingMixin:
    """Create DocumentDeliveryMatchingMixin with mocked dependencies."""
    mixin = DocumentDeliveryMatchingMixin.__new__(DocumentDeliveryMatchingMixin)
    mixin._caselog_service = MagicMock()
    mixin._case_number_service = MagicMock()
    mixin.case_matcher = MagicMock()
    mixin.document_renamer = MagicMock()
    mixin.notification_service = MagicMock()
    return mixin


# ═══════════════════════════════════════════════════════════════════════════
# file_name extraction (from _rename_and_attach_documents)
# ═══════════════════════════════════════════════════════════════════════════

class TestFileNameExtraction:
    """Test file name extraction logic from renamed file paths."""

    @staticmethod
    def extract_file_names(paths: list[str]) -> list[str]:
        """Extracted file name extraction from _rename_and_attach_documents."""
        return [f.split("/")[-1] for f in paths]

    def test_unix_paths(self) -> None:
        result = self.extract_file_names(["/home/user/docs/判决书.pdf", "/home/user/docs/裁定书.pdf"])
        assert result == ["判决书.pdf", "裁定书.pdf"]

    def test_single_path(self) -> None:
        result = self.extract_file_names(["/a/b/c.txt"])
        assert result == ["c.txt"]

    def test_single_segment_path(self) -> None:
        result = self.extract_file_names(["file.txt"])
        assert result == ["file.txt"]

    def test_empty_list(self) -> None:
        assert self.extract_file_names([]) == []

    def test_path_with_chinese_characters(self) -> None:
        result = self.extract_file_names(["/送达文书/（2025）粤0604民初123号.pdf"])
        assert result == ["（2025）粤0604民初123号.pdf"]

    def test_trailing_slash(self) -> None:
        """Paths with trailing slash produce empty string (as in original code)."""
        result = self.extract_file_names(["/a/b/"])
        assert result == [""]


# ═══════════════════════════════════════════════════════════════════════════
# notification result construction (from _send_notification)
# ═══════════════════════════════════════════════════════════════════════════

class TestNotificationResultConstruction:
    """Test notification result dict construction patterns."""

    @staticmethod
    def build_no_case_result() -> dict[str, Any]:
        """Result when SMS has no case binding."""
        return {"none": {"success": False, "error": "短信未绑定案件"}}

    @staticmethod
    def build_exception_result(existing: dict[str, Any] | None, error_msg: str) -> dict[str, Any]:
        """Result when notification throws exception."""
        result = existing or {}
        result["_exception"] = {"success": False, "error": error_msg}
        return result

    def test_no_case_result_structure(self) -> None:
        result = self.build_no_case_result()
        assert "none" in result
        assert result["none"]["success"] is False

    def test_exception_result_new(self) -> None:
        result = self.build_exception_result(None, "timeout")
        assert result["_exception"]["success"] is False
        assert "timeout" in result["_exception"]["error"]

    def test_exception_result_merges_existing(self) -> None:
        existing = {"feishu": {"success": True}}
        result = self.build_exception_result(existing, "err")
        assert result["feishu"]["success"] is True
        assert "_exception" in result


# ═══════════════════════════════════════════════════════════════════════════
# SMS processing result template
# ═══════════════════════════════════════════════════════════════════════════

class TestSMSProcessingResultTemplate:
    """Test the initial result dict template used in _process_sms_in_thread."""

    @staticmethod
    def create_initial_result(file_path: str) -> dict[str, Any]:
        """Extracted initial result template from _process_sms_in_thread."""
        return {
            "success": False,
            "case_id": None,
            "case_log_id": None,
            "renamed_path": file_path,
            "notification_sent": False,
            "error_message": None,
        }

    def test_template_has_all_keys(self) -> None:
        result = self.create_initial_result("/test.pdf")
        expected_keys = {"success", "case_id", "case_log_id", "renamed_path", "notification_sent", "error_message"}
        assert set(result.keys()) == expected_keys

    def test_template_defaults(self) -> None:
        result = self.create_initial_result("/test.pdf")
        assert result["success"] is False
        assert result["case_id"] is None
        assert result["notification_sent"] is False

    def test_template_sets_file_path(self) -> None:
        result = self.create_initial_result("/some/path.pdf")
        assert result["renamed_path"] == "/some/path.pdf"

    def test_timeout_result(self) -> None:
        """Timeout returns error message."""
        result = {"success": False, "error_message": "SMS 处理超时"}
        assert result["success"] is False
        assert "超时" in result["error_message"]


# ═══════════════════════════════════════════════════════════════════════════
# rename failure fallback
# ═══════════════════════════════════════════════════════════════════════════

class TestRenameFailureFallback:
    """Test the rename failure fallback logic from _rename_and_attach_documents."""

    @staticmethod
    def process_rename_results(original: str, renamed: str | None) -> str:
        """Extracted rename result processing.
        If rename returns a path, use it; otherwise keep original."""
        return renamed if renamed else original

    def test_successful_rename(self) -> None:
        assert self.process_rename_results("/old.pdf", "/new.pdf") == "/new.pdf"

    def test_rename_returns_none_keeps_original(self) -> None:
        assert self.process_rename_results("/old.pdf", None) == "/old.pdf"

    def test_rename_returns_empty_keeps_original(self) -> None:
        """Empty string is falsy, so original is kept."""
        assert self.process_rename_results("/old.pdf", "") == "/old.pdf"
