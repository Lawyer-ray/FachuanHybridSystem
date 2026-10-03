"""Tests for document_processing helpers (get_doc_config, _apply_pdf_limits)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.automation.services.document.document_processing import _apply_pdf_limits, get_doc_config

# ---------------------------------------------------------------------------
# get_doc_config
# ---------------------------------------------------------------------------


class TestGetDocConfig:
    def test_default(self):
        with patch("apps.automation.services.document.document_processing.settings") as mock_settings:
            mock_settings.DOCUMENT_PROCESSING = {
                "DEFAULT_TEXT_LIMIT": 1500,
                "DEFAULT_PREVIEW_PAGE": 1,
                "MAX_TEXT_LIMIT": 10000,
                "MAX_PREVIEW_PAGES": 5,
            }
            result = get_doc_config()
            assert "DEFAULT_TEXT_LIMIT" in result
            assert result["DEFAULT_TEXT_LIMIT"] == 1500

    def test_custom(self):
        with patch("apps.automation.services.document.document_processing.settings") as mock_settings:
            mock_settings.DOCUMENT_PROCESSING = {"DEFAULT_TEXT_LIMIT": 500}
            result = get_doc_config()
            assert result["DEFAULT_TEXT_LIMIT"] == 500


# ---------------------------------------------------------------------------
# _apply_pdf_limits
# ---------------------------------------------------------------------------


class TestApplyPdfLimits:
    def test_defaults(self):
        config = {
            "DEFAULT_TEXT_LIMIT": 1500,
            "DEFAULT_PREVIEW_PAGE": 1,
            "MAX_TEXT_LIMIT": 10000,
            "MAX_PREVIEW_PAGES": 5,
        }
        lim, page = _apply_pdf_limits(None, None, config)
        assert lim == 1500
        assert page == 1

    def test_custom_values(self):
        config = {
            "DEFAULT_TEXT_LIMIT": 1500,
            "DEFAULT_PREVIEW_PAGE": 1,
            "MAX_TEXT_LIMIT": 10000,
            "MAX_PREVIEW_PAGES": 5,
        }
        lim, page = _apply_pdf_limits(500, 3, config)
        assert lim == 500
        assert page == 3

    def test_exceed_max(self):
        config = {
            "DEFAULT_TEXT_LIMIT": 1500,
            "DEFAULT_PREVIEW_PAGE": 1,
            "MAX_TEXT_LIMIT": 10000,
            "MAX_PREVIEW_PAGES": 5,
        }
        lim, page = _apply_pdf_limits(50000, 100, config)
        assert lim == 10000
        assert page == 5
