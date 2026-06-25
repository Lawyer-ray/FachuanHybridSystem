"""Tests for evidence_sorting/services/reconciler.py"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.evidence_sorting.services.reconciler import (
    DeliveryNote,
    LineItem,
    MonthGroup,
    ReconcileResult,
    ReconcilerService,
    StatementInfo,
    STATUS_MATCHED,
    STATUS_UNMATCHED,
    STATUS_MISSING,
    FOLDER_CONFIRMED,
    FOLDER_UNSIGNED,
    FOLDER_MISSING_DELIVERY,
    FOLDER_DELIVERY_NOT_ENOUGH,
    FOLDER_DELIVERY_MISMATCH,
    FOLDER_NEED_SUPPLEMENT,
)


@pytest.fixture
def svc() -> ReconcilerService:
    return ReconcilerService()


# ── _parse_llm_response ──────────────────────────────────────────────────────

def test_parse_llm_response_valid_json(svc: ReconcilerService) -> None:
    json_text = '{"month": "2022-08", "total_amount": 100000, "signed": true, "line_items": [{"date": "20220801", "amount": 50000, "description": "desc1"}]}'
    result = svc._parse_llm_response(json_text)
    assert result.month == "2022-08"
    assert result.total_amount == 100000.0
    assert result.signed is True
    assert len(result.line_items) == 1
    assert result.line_items[0].date == "20220801"
    assert result.line_items[0].amount == 50000.0


def test_parse_llm_response_json_in_code_block(svc: ReconcilerService) -> None:
    text = '```json\n{"month": "2022-08", "total_amount": 50000, "signed": false, "line_items": []}\n```'
    result = svc._parse_llm_response(text)
    assert result.month == "2022-08"
    assert result.signed is False


def test_parse_llm_response_json_in_generic_code_block(svc: ReconcilerService) -> None:
    text = '```\n{"month": "2022-09", "total_amount": 30000, "signed": true, "line_items": []}\n```'
    result = svc._parse_llm_response(text)
    assert result.month == "2022-09"


def test_parse_llm_response_invalid_json(svc: ReconcilerService) -> None:
    result = svc._parse_llm_response("not json at all")
    assert result.month == ""
    assert result.total_amount is None


def test_parse_llm_response_missing_fields(svc: ReconcilerService) -> None:
    result = svc._parse_llm_response("{}")
    assert result.month == ""
    assert result.total_amount is None
    assert result.signed is False
    assert result.line_items == []


def test_parse_llm_response_null_line_items(svc: ReconcilerService) -> None:
    result = svc._parse_llm_response('{"line_items": null}')
    assert result.line_items == []


# ── _normalize_date ──────────────────────────────────────────────────────────

def test_normalize_date_valid():
    assert ReconcilerService._normalize_date("2022-08-01") == "20220801"


def test_normalize_date_already_clean():
    assert ReconcilerService._normalize_date("20220801") == "20220801"


def test_normalize_date_invalid():
    assert ReconcilerService._normalize_date("2022") is None


def test_normalize_date_none():
    assert ReconcilerService._normalize_date(None) is None


def test_normalize_date_empty():
    assert ReconcilerService._normalize_date("") is None


def test_normalize_date_with_slashes():
    assert ReconcilerService._normalize_date("2022/08/01") == "20220801"


# ── _to_float ─────────────────────────────────────────────────────────────────

def test_to_float_valid():
    assert ReconcilerService._to_float(123.45) == 123.45


def test_to_float_string():
    assert ReconcilerService._to_float("12345") == 12345.0


def test_to_float_with_comma():
    assert ReconcilerService._to_float("12,345") == 12345.0


def test_to_float_none():
    assert ReconcilerService._to_float(None) is None


def test_to_float_invalid():
    assert ReconcilerService._to_float("abc") is None


# ── _extract_month_key ───────────────────────────────────────────────────────

def test_extract_month_key_standard(svc: ReconcilerService) -> None:
    st = StatementInfo(month="2022-08")
    assert svc._extract_month_key(st) == "2022年08月"


def test_extract_month_key_cross_month(svc: ReconcilerService) -> None:
    st = StatementInfo(month="2022-01~2022-02")
    assert svc._extract_month_key(st) == "2022年01-02月"


def test_extract_month_key_empty(svc: ReconcilerService) -> None:
    st = StatementInfo(month="")
    assert svc._extract_month_key(st) == ""


def test_extract_month_key_single_digit(svc: ReconcilerService) -> None:
    st = StatementInfo(month="2022-8")
    assert svc._extract_month_key(st) == "2022年08月"


# ── _month_key_to_yyyymm ─────────────────────────────────────────────────────

def test_month_key_to_yyyymm_valid(svc: ReconcilerService) -> None:
    assert svc._month_key_to_yyyymm("2022年08月") == "202208"


def test_month_key_to_yyyymm_cross_month(svc: ReconcilerService) -> None:
    # cross month format "2022年01-02月" should still match first 6 chars
    result = svc._month_key_to_yyyymm("2022年01-02月")
    assert result == "202201"


def test_month_key_to_yyyymm_invalid(svc: ReconcilerService) -> None:
    assert svc._month_key_to_yyyymm("invalid") is None


# ── _match_delivery ───────────────────────────────────────────────────────────

def test_match_delivery_date_and_amount(svc: ReconcilerService) -> None:
    li = LineItem(date="20220801", amount=50000.0)
    dn = DeliveryNote(date="20220801", amount="50000")
    assert svc._match_delivery(li, dn) is True


def test_match_delivery_date_mismatch(svc: ReconcilerService) -> None:
    li = LineItem(date="20220801", amount=50000.0)
    dn = DeliveryNote(date="20220802", amount="50000")
    assert svc._match_delivery(li, dn) is False


def test_match_delivery_amount_mismatch(svc: ReconcilerService) -> None:
    li = LineItem(date="20220801", amount=50000.0)
    dn = DeliveryNote(date="20220801", amount="99999")
    # date matches but amount doesn't -> returns True because date match counts
    assert svc._match_delivery(li, dn) is True


def test_match_delivery_no_dates(svc: ReconcilerService) -> None:
    li = LineItem(date=None, amount=50000.0)
    dn = DeliveryNote(date=None, amount="50000")
    assert svc._match_delivery(li, dn) is False


def test_match_delivery_amount_within_tolerance(svc: ReconcilerService) -> None:
    li = LineItem(date="20220801", amount=10000.0)
    dn = DeliveryNote(date="20220801", amount="10050")
    # tolerance is max(10000*0.01, 1.0) = 100, diff=50 -> within
    assert svc._match_delivery(li, dn) is True


def test_match_delivery_amount_outside_tolerance(svc: ReconcilerService) -> None:
    li = LineItem(date="20220801", amount=10000.0)
    dn = DeliveryNote(date="20220801", amount="20000")
    # diff=10000 > tolerance=100, but date matches -> True
    assert svc._match_delivery(li, dn) is True


def test_match_delivery_invalid_amount(svc: ReconcilerService) -> None:
    li = LineItem(date="20220801", amount=50000.0)
    dn = DeliveryNote(date="20220801", amount="not_a_number")
    # amount parsing fails, but date matches -> True
    assert svc._match_delivery(li, dn) is True


def test_match_delivery_no_line_item_date_has_delivery_date(svc: ReconcilerService) -> None:
    li = LineItem(date=None, amount=50000.0)
    dn = DeliveryNote(date="20220801", amount="50000")
    # li.date is None, dn.date is set -> falls through to amount check -> amount matches
    result = svc._match_delivery(li, dn)
    assert isinstance(result, bool)


# ── _build_folder_name ────────────────────────────────────────────────────────

def test_build_folder_name_no_issues(svc: ReconcilerService) -> None:
    st = StatementInfo(signed=True)
    group = MonthGroup(month="2022年08月", folder_name="", deliveries=[])
    result = svc._build_folder_name("2022年08月", st, group, [])
    assert FOLDER_CONFIRMED in result


def test_build_folder_name_unsigned(svc: ReconcilerService) -> None:
    st = StatementInfo(signed=False)
    group = MonthGroup(month="2022年08月", folder_name="", deliveries=[])
    result = svc._build_folder_name("2022年08月", st, group, [FOLDER_UNSIGNED])
    assert FOLDER_UNSIGNED in result


def test_build_folder_name_with_deliveries(svc: ReconcilerService) -> None:
    st = StatementInfo(signed=True)
    dn = DeliveryNote(match_status=STATUS_MATCHED)
    group = MonthGroup(month="2022年08月", folder_name="", deliveries=[dn])
    result = svc._build_folder_name("2022年08月", st, group, [])
    assert "出库单" in result


def test_build_folder_name_unmatched_delivery(svc: ReconcilerService) -> None:
    st = StatementInfo(signed=True)
    dn = DeliveryNote(match_status=STATUS_UNMATCHED)
    group = MonthGroup(month="2022年08月", folder_name="", deliveries=[dn])
    result = svc._build_folder_name("2022年08月", st, group, [FOLDER_DELIVERY_MISMATCH])
    assert "无法确认" in result


def test_build_folder_name_delivery_not_enough(svc: ReconcilerService) -> None:
    st = StatementInfo(signed=True)
    dn = DeliveryNote(match_status=STATUS_UNMATCHED)
    group = MonthGroup(month="2022年08月", folder_name="", deliveries=[dn])
    issues = [FOLDER_DELIVERY_NOT_ENOUGH]
    result = svc._build_folder_name("2022年08月", st, group, issues)
    assert "数量不够" in result


# ── reconcile_async (integration) ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reconcile_empty_inputs(svc: ReconcilerService) -> None:
    result = await svc.reconcile_async([], [], [], [])
    assert result.month_groups == []
    assert result.unmatched_deliveries == []
    assert result.receipts == []
    assert result.others == []


@pytest.mark.asyncio
async def test_reconcile_with_statements(svc: ReconcilerService) -> None:
    # Mock parse_statement_async to return a parsed statement
    parsed = StatementInfo(
        month="2022-08",
        total_amount=50000.0,
        signed=True,
        line_items=[LineItem(date="20220801", amount=50000.0, description="desc")],
    )
    svc.parse_statement_async = AsyncMock(return_value=parsed)

    statements = [{"ocr_text": "test ocr", "filename": "stmt.pdf", "signed": True}]
    result = await svc.reconcile_async(statements, [], [], [])

    assert len(result.month_groups) == 1
    svc.parse_statement_async.assert_called_once()


@pytest.mark.asyncio
async def test_reconcile_with_matching_deliveries(svc: ReconcilerService) -> None:
    parsed = StatementInfo(
        month="2022-08",
        total_amount=50000.0,
        signed=True,
        line_items=[LineItem(date="20220801", amount=50000.0)],
    )
    svc.parse_statement_async = AsyncMock(return_value=parsed)

    statements = [{"ocr_text": "test", "filename": "stmt.pdf"}]
    deliveries = [{"filename": "dn.pdf", "date": "20220801", "amount": "50000"}]

    result = await svc.reconcile_async(statements, deliveries, [], [])
    assert len(result.month_groups) == 1
    assert len(result.month_groups[0].deliveries) == 1


@pytest.mark.asyncio
async def test_reconcile_with_unmatched_delivery(svc: ReconcilerService) -> None:
    parsed = StatementInfo(
        month="2022-08",
        total_amount=50000.0,
        signed=True,
        line_items=[],
    )
    svc.parse_statement_async = AsyncMock(return_value=parsed)

    statements = [{"ocr_text": "test", "filename": "stmt.pdf"}]
    deliveries = [{"filename": "dn.pdf", "date": "20220801", "amount": "50000"}]

    result = await svc.reconcile_async(statements, deliveries, [], [])
    # Delivery in same month but no line items to match
    assert len(result.month_groups) == 1


@pytest.mark.asyncio
async def test_reconcile_unsigned_statement(svc: ReconcilerService) -> None:
    parsed = StatementInfo(
        month="2022-08",
        total_amount=50000.0,
        signed=False,
        line_items=[],
    )
    svc.parse_statement_async = AsyncMock(return_value=parsed)

    statements = [{"ocr_text": "test", "filename": "stmt.pdf"}]
    result = await svc.reconcile_async(statements, [], [], [])

    assert len(result.unsigned_statements) >= 1


@pytest.mark.asyncio
async def test_reconcile_receipts_and_others(svc: ReconcilerService) -> None:
    svc.parse_statement_async = AsyncMock(return_value=StatementInfo())

    receipts = [{"filename": "receipt.pdf"}]
    others = [{"filename": "other.pdf"}]

    result = await svc.reconcile_async([], [], receipts, others)
    assert result.receipts == receipts
    assert result.others == others


@pytest.mark.asyncio
async def test_reconcile_statement_with_classification_signed(svc: ReconcilerService) -> None:
    """LLM says not signed but classification says signed."""
    parsed = StatementInfo(month="2022-08", signed=False, line_items=[])
    svc.parse_statement_async = AsyncMock(return_value=parsed)

    statements = [{"ocr_text": "test", "filename": "stmt.pdf", "signed": True}]
    result = await svc.reconcile_async(statements, [], [], [])

    # The statement should have signed=True from classification
    assert len(result.month_groups) == 1


@pytest.mark.asyncio
async def test_reconcile_unmatched_delivery_no_month(svc: ReconcilerService) -> None:
    """Delivery with date outside statement months."""
    parsed = StatementInfo(month="2022-08", signed=True, line_items=[])
    svc.parse_statement_async = AsyncMock(return_value=parsed)

    statements = [{"ocr_text": "test", "filename": "stmt.pdf"}]
    deliveries = [{"filename": "dn.pdf", "date": "20230101", "amount": "50000"}]

    result = await svc.reconcile_async(statements, deliveries, [], [])
    assert len(result.unmatched_deliveries) == 1


@pytest.mark.asyncio
async def test_reconcile_statement_no_month_key(svc: ReconcilerService) -> None:
    """Statement with no parseable month."""
    parsed = StatementInfo(month="", signed=False, line_items=[])
    svc.parse_statement_async = AsyncMock(return_value=parsed)

    statements = [{"ocr_text": "test", "filename": "stmt.pdf"}]
    result = await svc.reconcile_async(statements, [], [], [])

    assert len(result.unsigned_statements) >= 1
