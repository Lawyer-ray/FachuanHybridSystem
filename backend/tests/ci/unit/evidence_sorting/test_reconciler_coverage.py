"""Comprehensive tests for evidence_sorting reconciler data processing functions."""

from __future__ import annotations

import pytest

from apps.evidence_sorting.services.reconciler import (
    STATUS_MATCHED,
    STATUS_UNMATCHED,
    DeliveryNote,
    FOLDER_CONFIRMED,
    FOLDER_DELIVERY_MISMATCH,
    FOLDER_DELIVERY_NOT_ENOUGH,
    FOLDER_MISSING_DELIVERY,
    FOLDER_UNSIGNED,
    LineItem,
    MonthGroup,
    ReconcileResult,
    ReconcilerService,
    StatementInfo,
)


@pytest.fixture
def service():
    return ReconcilerService()


# ---------------------------------------------------------------------------
# _normalize_date
# ---------------------------------------------------------------------------
class TestNormalizeDate:
    def test_valid_8_digit(self, service):
        assert service._normalize_date("20220815") == "20220815"

    def test_with_dashes(self, service):
        assert service._normalize_date("2022-08-15") == "20220815"

    def test_with_slashes(self, service):
        assert service._normalize_date("2022/08/15") == "20220815"

    def test_invalid_length(self, service):
        assert service._normalize_date("202208") is None

    def test_none(self, service):
        assert service._normalize_date(None) is None

    def test_empty(self, service):
        assert service._normalize_date("") is None

    def test_non_digit(self, service):
        assert service._normalize_date("abcdefgh") is None


# ---------------------------------------------------------------------------
# _to_float
# ---------------------------------------------------------------------------
class TestToFloat:
    def test_integer(self, service):
        assert service._to_float(42) == 42.0

    def test_string(self, service):
        assert service._to_float("100.50") == 100.5

    def test_comma_separated(self, service):
        assert service._to_float("1,000.50") == 1000.5

    def test_none(self, service):
        assert service._to_float(None) is None

    def test_invalid(self, service):
        assert service._to_float("abc") is None


# ---------------------------------------------------------------------------
# _parse_llm_response
# ---------------------------------------------------------------------------
class TestParseLlmResponse:
    def test_valid_json(self, service):
        text = '{"month": "2022-08", "total_amount": 187480, "signed": true, "line_items": [{"date": "20220801", "amount": 50000, "description": "test"}]}'
        result = service._parse_llm_response(text)
        assert result.month == "2022-08"
        assert result.total_amount == 187480.0
        assert result.signed is True
        assert len(result.line_items) == 1

    def test_json_in_code_block(self, service):
        text = '```json\n{"month": "2022-09", "total_amount": 10000, "signed": false, "line_items": []}\n```'
        result = service._parse_llm_response(text)
        assert result.month == "2022-09"

    def test_invalid_json(self, service):
        result = service._parse_llm_response("not json at all")
        assert result.month == ""

    def test_empty_string(self, service):
        result = service._parse_llm_response("")
        assert result.month == ""

    def test_json_with_missing_fields(self, service):
        text = '{"month": "2022-08"}'
        result = service._parse_llm_response(text)
        assert result.month == "2022-08"
        assert result.total_amount is None
        assert result.signed is False

    def test_line_items_with_nulls(self, service):
        text = '{"month": "2022-08", "total_amount": null, "signed": false, "line_items": [{"date": null, "amount": null, "description": ""}]}'
        result = service._parse_llm_response(text)
        assert len(result.line_items) == 1
        assert result.line_items[0].date is None
        assert result.line_items[0].amount is None


# ---------------------------------------------------------------------------
# _extract_month_key
# ---------------------------------------------------------------------------
class TestExtractMonthKey:
    def test_standard_format(self, service):
        st = StatementInfo(month="2022-08")
        assert service._extract_month_key(st) == "2022年08月"

    def test_cross_month(self, service):
        st = StatementInfo(month="2022-01~2022-02")
        assert service._extract_month_key(st) == "2022年01-02月"

    def test_empty_month(self, service):
        st = StatementInfo(month="")
        assert service._extract_month_key(st) == ""

    def test_single_digit_month(self, service):
        st = StatementInfo(month="2022-8")
        assert service._extract_month_key(st) == "2022年08月"


# ---------------------------------------------------------------------------
# _month_key_to_yyyymm
# ---------------------------------------------------------------------------
class TestMonthKeyToYyyymm:
    def test_standard(self, service):
        assert service._month_key_to_yyyymm("2022年08月") == "202208"

    def test_cross_month(self, service):
        # Cross month format still extracts first month digits
        result = service._month_key_to_yyyymm("2022年01-02月")
        assert result == "202201"

    def test_invalid(self, service):
        assert service._month_key_to_yyyymm("invalid") is None


# ---------------------------------------------------------------------------
# _match_delivery
# ---------------------------------------------------------------------------
class TestMatchDelivery:
    def test_date_and_amount_match(self, service):
        li = LineItem(date="20220815", amount=50000.0, description="")
        dn = DeliveryNote(date="20220815", amount="50000")
        assert service._match_delivery(li, dn) is True

    def test_date_mismatch(self, service):
        li = LineItem(date="20220815", amount=50000.0, description="")
        dn = DeliveryNote(date="20220816", amount="50000")
        assert service._match_delivery(li, dn) is False

    def test_amount_within_tolerance(self, service):
        li = LineItem(date="20220815", amount=50000.0, description="")
        dn = DeliveryNote(date="20220815", amount="50100")
        # tolerance is max(abs(50000) * 0.01, 1.0) = 500
        assert service._match_delivery(li, dn) is True

    def test_amount_outside_tolerance(self, service):
        # Note: dates still match, so falls through to date-only match
        li = LineItem(date="20220815", amount=50000.0, description="")
        dn = DeliveryNote(date="20220815", amount="55000")
        # Date match means True even with large amount diff
        assert service._match_delivery(li, dn) is True

    def test_amount_outside_tolerance_different_dates(self, service):
        li = LineItem(date="20220815", amount=50000.0, description="")
        dn = DeliveryNote(date="20220820", amount="55000")
        # Different dates, large amount diff - no match
        assert service._match_delivery(li, dn) is False

    def test_no_dates_both_none(self, service):
        li = LineItem(date=None, amount=50000.0, description="")
        dn = DeliveryNote(date=None, amount="50000")
        assert service._match_delivery(li, dn) is False

    def test_only_date_matches(self, service):
        li = LineItem(date="20220815", amount=None, description="")
        dn = DeliveryNote(date="20220815", amount=None)
        assert service._match_delivery(li, dn) is True

    def test_invalid_amount_string(self, service):
        li = LineItem(date="20220815", amount=50000.0, description="")
        dn = DeliveryNote(date="20220815", amount="abc")
        # Falls through to date-only match
        assert service._match_delivery(li, dn) is True


# ---------------------------------------------------------------------------
# _build_folder_name
# ---------------------------------------------------------------------------
class TestBuildFolderName:
    def test_confirmed_with_deliveries(self, service):
        group = MonthGroup(month="2022年08月", folder_name="", deliveries=[
            DeliveryNote(match_status=STATUS_MATCHED),
        ])
        result = service._build_folder_name("2022年08月", StatementInfo(signed=True), group, [])
        assert "已确认" in result
        assert "对账单与出库单" in result

    def test_unsigned(self, service):
        group = MonthGroup(month="2022年08月", folder_name="", deliveries=[])
        result = service._build_folder_name("2022年08月", StatementInfo(signed=False), group, [FOLDER_UNSIGNED])
        assert "未签名" in result

    def test_delivery_mismatch(self, service):
        group = MonthGroup(month="2022年08月", folder_name="", deliveries=[
            DeliveryNote(match_status=STATUS_UNMATCHED),
        ])
        result = service._build_folder_name("2022年08月", StatementInfo(signed=True), group, [FOLDER_DELIVERY_MISMATCH])
        assert "无法确认" in result

    def test_no_deliveries(self, service):
        group = MonthGroup(month="2022年08月", folder_name="", deliveries=[])
        result = service._build_folder_name("2022年08月", StatementInfo(signed=True), group, [])
        assert "对账单" in result
        assert "对账单与出库单" not in result


# ---------------------------------------------------------------------------
# StatementInfo / LineItem / DeliveryNote dataclasses
# ---------------------------------------------------------------------------
class TestDataclasses:
    def test_statement_defaults(self):
        st = StatementInfo()
        assert st.month == ""
        assert st.total_amount is None
        assert st.signed is False
        assert st.line_items == []

    def test_line_item_defaults(self):
        li = LineItem()
        assert li.date is None
        assert li.amount is None
        assert li.description == ""

    def test_delivery_defaults(self):
        dn = DeliveryNote()
        assert dn.filename == ""
        assert dn.match_status == STATUS_UNMATCHED

    def test_reconcile_result_defaults(self):
        r = ReconcileResult()
        assert r.month_groups == []
        assert r.unmatched_deliveries == []

    def test_month_group_defaults(self):
        mg = MonthGroup(month="2022年08月", folder_name="test")
        assert mg.statement is None
        assert mg.deliveries == []
        assert mg.issues == []
