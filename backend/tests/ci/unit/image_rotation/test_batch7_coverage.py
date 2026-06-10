"""Batch7 coverage tests for apps.image_rotation."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.image_rotation.services.auto_rename_service import (
    AutoRenameService,
    ExtractionResult,
    RenameSuggestion,
)


# ── ExtractionResult ────────────────────────────────────────────────────────


class TestExtractionResult:
    def test_defaults(self) -> None:
        result = ExtractionResult()
        assert result.date is None
        assert result.amount is None
        assert result.raw_date is None
        assert result.raw_amount is None

    def test_with_values(self) -> None:
        result = ExtractionResult(
            date="20250630", amount="65500元", raw_date="2025年6月30日", raw_amount="65500元"
        )
        assert result.date == "20250630"
        assert result.amount == "65500元"


# ── RenameSuggestion ────────────────────────────────────────────────────────


class TestRenameSuggestion:
    def test_defaults(self) -> None:
        suggestion = RenameSuggestion(
            original_filename="test.jpg", suggested_filename="20250630.jpg"
        )
        assert suggestion.success is True
        assert suggestion.error is None


# ── AutoRenameService ───────────────────────────────────────────────────────


class TestAutoRenameService:
    def _make_service(self, llm_client: object | None = None) -> AutoRenameService:
        return AutoRenameService(
            ollama_model="test",
            ollama_base_url="http://localhost",
            llm_client=llm_client,
        )

    def test_generate_filename_date_and_amount(self) -> None:
        svc = self._make_service()
        result = svc.generate_filename(
            "receipt.jpg",
            ExtractionResult(date="20250630", amount="65500元"),
        )
        assert result == "20250630_65500元.jpg"

    def test_generate_filename_date_only(self) -> None:
        svc = self._make_service()
        result = svc.generate_filename(
            "receipt.jpg",
            ExtractionResult(date="20250630"),
        )
        assert result == "20250630.jpg"

    def test_generate_filename_amount_only(self) -> None:
        svc = self._make_service()
        result = svc.generate_filename(
            "receipt.jpg",
            ExtractionResult(amount="65500元"),
        )
        assert result == "65500元.jpg"

    def test_generate_filename_nothing(self) -> None:
        svc = self._make_service()
        result = svc.generate_filename("receipt.jpg", ExtractionResult())
        assert result == "receipt.jpg"

    def test_get_file_extension(self) -> None:
        svc = self._make_service()
        assert svc._get_file_extension("test.jpg") == ".jpg"
        assert svc._get_file_extension("test.tar.gz") == ".gz"
        assert svc._get_file_extension("noext") == ""

    def test_normalize_date_valid(self) -> None:
        svc = self._make_service()
        assert svc._normalize_date("20250630") == "20250630"

    def test_normalize_date_with_separators(self) -> None:
        svc = self._make_service()
        assert svc._normalize_date("2025-06-30") == "20250630"

    def test_normalize_date_six_digits(self) -> None:
        svc = self._make_service()
        assert svc._normalize_date("250630") == "20250630"

    def test_normalize_date_empty(self) -> None:
        svc = self._make_service()
        assert svc._normalize_date("") is None

    def test_normalize_date_invalid(self) -> None:
        svc = self._make_service()
        assert svc._normalize_date("123") is None

    def test_extract_json_block_markdown(self) -> None:
        svc = self._make_service()
        text = '```json\n{"date": "20250630"}\n```'
        result = svc._extract_json_block(text)
        assert '"date"' in result

    def test_extract_json_block_braces(self) -> None:
        svc = self._make_service()
        text = 'Here is the result: {"date": "20250630"} done'
        result = svc._extract_json_block(text)
        assert '"date"' in result

    def test_extract_json_block_no_json(self) -> None:
        svc = self._make_service()
        text = "no json here"
        result = svc._extract_json_block(text)
        assert result == "no json here"

    def test_parse_extraction_response_valid_json(self) -> None:
        svc = self._make_service()
        text = '{"date": "20250630", "amount": "65500元", "raw_date": "2025年6月30日", "raw_amount": "65500元"}'
        result = svc._parse_extraction_response(text)
        assert result.date == "20250630"
        assert result.amount == "65500元"

    def test_parse_extraction_response_invalid_json(self) -> None:
        svc = self._make_service()
        text = 'not json but "date": "20250630" and "amount": "100元"'
        result = svc._parse_extraction_response(text)
        # Should fall back to regex
        assert result is not None

    def test_fallback_regex_extraction(self) -> None:
        svc = self._make_service()
        text = '"date": "2025-06-30", "amount": "100元", "raw_date": "2025年6月30日", "raw_amount": "一百元"'
        result = svc._fallback_regex_extraction(text)
        assert result.date == "20250630"
        assert result.amount == "100元"

    def test_suggest_rename_success(self) -> None:
        mock_client = MagicMock()
        mock_client.complete.return_value = SimpleNamespace(
            content='{"date": "20250630", "amount": "1000元", "raw_date": null, "raw_amount": null}'
        )
        svc = self._make_service(llm_client=mock_client)
        result = svc.suggest_rename("test.jpg", "发票金额1000元 2025年6月30日")
        assert result.success is True
        assert "20250630" in result.suggested_filename

    def test_extract_info_empty_text(self) -> None:
        svc = self._make_service()
        result = svc.extract_info("")
        assert result.date is None
        assert result.amount is None

    def test_extract_info_whitespace_only(self) -> None:
        svc = self._make_service()
        result = svc.extract_info("   ")
        assert result.date is None

    def test_normalize_date_old_century(self) -> None:
        svc = self._make_service()
        result = svc._normalize_date("800101")
        assert result == "19800101"
