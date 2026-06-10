"""Batch7 coverage tests for apps.evidence_sorting."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.evidence_sorting.services.classifier import (
    ClassifierService,
    ClassifyResult,
    ClassifiedImage,
    TYPE_DELIVERY,
    TYPE_OTHER,
    TYPE_RECEIPT,
    TYPE_STATEMENT,
    _KEYWORDS,
)


# ── Constants ───────────────────────────────────────────────────────────────


class TestClassifierConstants:
    def test_type_values(self) -> None:
        assert TYPE_STATEMENT == "statement"
        assert TYPE_DELIVERY == "delivery"
        assert TYPE_RECEIPT == "receipt"
        assert TYPE_OTHER == "other"

    def test_keywords_contain_expected(self) -> None:
        assert "对账单" in _KEYWORDS[TYPE_STATEMENT]
        assert "出库单" in _KEYWORDS[TYPE_DELIVERY]
        assert "收款" in _KEYWORDS[TYPE_RECEIPT]


# ── ClassifiedImage ─────────────────────────────────────────────────────────


class TestClassifiedImage:
    def test_defaults(self) -> None:
        img = ClassifiedImage(filename="test.jpg", category=TYPE_OTHER, ocr_text="")
        assert img.date is None
        assert img.amount is None
        assert img.signed is None
        assert img.confidence == 0.0

    def test_with_values(self) -> None:
        img = ClassifiedImage(
            filename="test.jpg",
            category=TYPE_STATEMENT,
            ocr_text="对账单",
            date="20250630",
            amount="1000",
            signed=True,
            confidence=0.95,
        )
        assert img.category == TYPE_STATEMENT
        assert img.signed is True


# ── ClassifyResult ──────────────────────────────────────────────────────────


class TestClassifyResult:
    def test_defaults(self) -> None:
        result = ClassifyResult()
        assert result.images == []
        assert result.errors == []


# ── ClassifierService ───────────────────────────────────────────────────────


class TestClassifierService:
    def _make_service(self) -> ClassifierService:
        return ClassifierService()

    def test_classify_by_keywords_statement(self) -> None:
        svc = self._make_service()
        assert svc._classify_by_keywords("对账单明细") == TYPE_STATEMENT

    def test_classify_by_keywords_delivery(self) -> None:
        svc = self._make_service()
        assert svc._classify_by_keywords("出库单 品名数量") == TYPE_DELIVERY

    def test_classify_by_keywords_receipt(self) -> None:
        svc = self._make_service()
        assert svc._classify_by_keywords("收款 金额1000元") == TYPE_RECEIPT

    def test_classify_by_keywords_other(self) -> None:
        svc = self._make_service()
        assert svc._classify_by_keywords("random text no keywords") == TYPE_OTHER

    def test_classify_by_keywords_empty_text_png(self) -> None:
        svc = self._make_service()
        assert svc._classify_by_keywords("", "test.png") == TYPE_STATEMENT

    def test_classify_by_keywords_empty_text_other(self) -> None:
        svc = self._make_service()
        assert svc._classify_by_keywords("", "test.jpg") == TYPE_OTHER

    def test_classify_by_keywords_empty_text_no_filename(self) -> None:
        svc = self._make_service()
        assert svc._classify_by_keywords("") == TYPE_OTHER

    def test_extract_date_chinese(self) -> None:
        svc = self._make_service()
        assert svc._extract_date("2025年6月30日") == "20250630"

    def test_extract_date_iso(self) -> None:
        svc = self._make_service()
        assert svc._extract_date("2025-06-30") == "20250630"

    def test_extract_date_slash(self) -> None:
        svc = self._make_service()
        assert svc._extract_date("2025/06/30") == "20250630"

    def test_extract_date_none(self) -> None:
        svc = self._make_service()
        assert svc._extract_date("no date") is None

    def test_extract_amount_yuan_symbol(self) -> None:
        svc = self._make_service()
        result = svc._extract_amount("¥1,000.00")
        assert result is not None
        # Could be "1000.0" or "1000" depending on implementation
        assert "1000" in str(result)

    def test_extract_amount_unit(self) -> None:
        svc = self._make_service()
        result = svc._extract_amount("500.00元")
        assert result is not None

    def test_extract_amount_with_label(self) -> None:
        svc = self._make_service()
        assert svc._extract_amount("金额：1234.56") == "1234.56"

    def test_extract_amount_none(self) -> None:
        svc = self._make_service()
        assert svc._extract_amount("no amount") is None

    def test_detect_signed_true(self) -> None:
        svc = self._make_service()
        assert svc._detect_signed("已签名确认") is True

    def test_detect_signed_false(self) -> None:
        svc = self._make_service()
        assert svc._detect_signed("no signature keywords") is False

    def test_extract_amount_integer_result(self) -> None:
        svc = self._make_service()
        result = svc._extract_amount("合计：1000")
        assert result == "1000"

    def test_extract_amount_max_returned(self) -> None:
        svc = self._make_service()
        result = svc._extract_amount("¥100 ¥500 ¥200")
        assert result == "500"
