"""Batch8 coverage tests for apps.evidence_sorting."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.evidence_sorting.services.reconciler import (
    LineItem,
    MonthGroup,
    ReconcileResult,
    ReconcilerService,
    StatementInfo,
    DeliveryNote,
    STATUS_MATCHED,
    STATUS_UNMATCHED,
    STATUS_MISSING,
    FOLDER_CONFIRMED,
    FOLDER_UNSIGNED,
    FOLDER_MISSING_DELIVERY,
)


# ── ReconcilerService helper methods ──────────────────────────────────────


class TestReconcilerServiceHelpers:
    """Test ReconcilerService helper methods."""

    def test_normalize_date_valid(self) -> None:
        svc = ReconcilerService()
        assert svc._normalize_date("20220815") == "20220815"

    def test_normalize_date_with_separators(self) -> None:
        svc = ReconcilerService()
        assert svc._normalize_date("2022-08-15") == "20220815"

    def test_normalize_date_none(self) -> None:
        svc = ReconcilerService()
        assert svc._normalize_date(None) is None

    def test_normalize_date_empty(self) -> None:
        svc = ReconcilerService()
        assert svc._normalize_date("") is None

    def test_normalize_date_too_short(self) -> None:
        svc = ReconcilerService()
        assert svc._normalize_date("2022") is None

    def test_to_float_valid(self) -> None:
        svc = ReconcilerService()
        assert svc._to_float("1234.56") == 1234.56

    def test_to_float_with_comma(self) -> None:
        svc = ReconcilerService()
        assert svc._to_float("1,234.56") == 1234.56

    def test_to_float_none(self) -> None:
        svc = ReconcilerService()
        assert svc._to_float(None) is None

    def test_to_float_invalid(self) -> None:
        svc = ReconcilerService()
        assert svc._to_float("abc") is None

    def test_extract_month_key_standard(self) -> None:
        svc = ReconcilerService()
        st = StatementInfo(month="2022-08")
        assert svc._extract_month_key(st) == "2022年08月"

    def test_extract_month_key_range(self) -> None:
        svc = ReconcilerService()
        st = StatementInfo(month="2022-01~2022-02")
        result = svc._extract_month_key(st)
        assert "01" in result and "02" in result

    def test_extract_month_key_empty(self) -> None:
        svc = ReconcilerService()
        st = StatementInfo(month="")
        assert svc._extract_month_key(st) == ""

    def test_month_key_to_yyyymm_valid(self) -> None:
        svc = ReconcilerService()
        assert svc._month_key_to_yyyymm("2022年08月") == "202208"

    def test_month_key_to_yyyymm_range(self) -> None:
        svc = ReconcilerService()
        result = svc._month_key_to_yyyymm("2022年01-02月")
        assert result == "202201"

    def test_month_key_to_yyyymm_invalid(self) -> None:
        svc = ReconcilerService()
        assert svc._month_key_to_yyyymm("invalid") is None


# ── ReconcilerService.match_delivery ──────────────────────────────────────


class TestMatchDelivery:
    """Test delivery matching logic."""

    def test_match_same_date_and_amount(self) -> None:
        svc = ReconcilerService()
        li = LineItem(date="20220815", amount=1000.0)
        dn = DeliveryNote(date="20220815", amount="1000")
        assert svc._match_delivery(li, dn) is True

    def test_match_different_date(self) -> None:
        svc = ReconcilerService()
        li = LineItem(date="20220815", amount=1000.0)
        dn = DeliveryNote(date="20220816", amount="1000")
        assert svc._match_delivery(li, dn) is False

    def test_match_within_tolerance(self) -> None:
        svc = ReconcilerService()
        li = LineItem(date="20220815", amount=1000.0)
        dn = DeliveryNote(date="20220815", amount="1005")
        assert svc._match_delivery(li, dn) is True

    def test_match_no_dates(self) -> None:
        svc = ReconcilerService()
        li = LineItem(date=None, amount=1000.0)
        dn = DeliveryNote(date=None, amount="1000")
        assert svc._match_delivery(li, dn) is False

    def test_match_date_only(self) -> None:
        svc = ReconcilerService()
        li = LineItem(date="20220815", amount=None)
        dn = DeliveryNote(date="20220815", amount=None)
        assert svc._match_delivery(li, dn) is True


# ── ReconcilerService._build_folder_name ──────────────────────────────────


class TestBuildFolderName:
    """Test folder name building."""

    def test_confirmed_with_deliveries(self) -> None:
        svc = ReconcilerService()
        group = MonthGroup(month="2022年08月", folder_name="")
        group.deliveries = [DeliveryNote(match_status=STATUS_MATCHED)]
        result = svc._build_folder_name("2022年08月", StatementInfo(signed=True), group, [])
        assert "对账单与出库单" in result
        assert "已确认" in result

    def test_unsigned(self) -> None:
        svc = ReconcilerService()
        group = MonthGroup(month="2022年08月", folder_name="")
        result = svc._build_folder_name("2022年08月", StatementInfo(signed=False), group, [FOLDER_UNSIGNED])
        assert "对账单未签名" in result

    def test_no_deliveries(self) -> None:
        svc = ReconcilerService()
        group = MonthGroup(month="2022年08月", folder_name="")
        result = svc._build_folder_name("2022年08月", StatementInfo(signed=True), group, [])
        assert "对账单" in result


# ── ReconcilerService._parse_llm_response ─────────────────────────────────


class TestParseLLMResponse:
    """Test LLM response parsing."""

    def test_parse_valid_json(self) -> None:
        svc = ReconcilerService()
        text = '{"month": "2022-08", "total_amount": 1000, "signed": true, "line_items": [{"date": "20220815", "amount": 1000, "description": "test"}]}'
        result = svc._parse_llm_response(text)
        assert result.month == "2022-08"
        assert result.total_amount == 1000.0
        assert result.signed is True
        assert len(result.line_items) == 1

    def test_parse_json_in_code_block(self) -> None:
        svc = ReconcilerService()
        text = '```json\n{"month": "2022-08", "total_amount": null, "signed": false, "line_items": []}\n```'
        result = svc._parse_llm_response(text)
        assert result.month == "2022-08"

    def test_parse_invalid_json(self) -> None:
        svc = ReconcilerService()
        result = svc._parse_llm_response("not json at all")
        assert result.month == ""


# ── Data classes ──────────────────────────────────────────────────────────


class TestDataClasses:
    """Test reconciler data classes."""

    def test_line_item_defaults(self) -> None:
        li = LineItem()
        assert li.date is None
        assert li.amount is None
        assert li.description == ""

    def test_statement_info_defaults(self) -> None:
        si = StatementInfo()
        assert si.month == ""
        assert si.signed is False
        assert si.line_items == []

    def test_delivery_note_defaults(self) -> None:
        dn = DeliveryNote()
        assert dn.match_status == STATUS_UNMATCHED

    def test_month_group_defaults(self) -> None:
        mg = MonthGroup(month="2022年08月", folder_name="test")
        assert mg.deliveries == []
        assert mg.issues == []

    def test_reconcile_result_defaults(self) -> None:
        rr = ReconcileResult()
        assert rr.month_groups == []
        assert rr.unmatched_deliveries == []
