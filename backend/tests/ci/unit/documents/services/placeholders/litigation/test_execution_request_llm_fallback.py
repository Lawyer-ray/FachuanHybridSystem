"""Tests for execution_request_llm_fallback module.

Covers:
  - should_try_llm_fallback
  - _has_fee_prepaid_context
  - merge_llm_fallback
  - _extract_json_object
  - _parse_iso_date
  - _parse_bool
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.documents.services.placeholders.litigation.execution_request_llm_fallback import (
    _extract_json_object,
    _has_fee_prepaid_context,
    _parse_bool,
    _parse_iso_date,
    merge_llm_fallback,
    should_try_llm_fallback,
)
from apps.documents.services.placeholders.litigation.execution_request_models import (
    ParsedAmounts,
    ParsedInterestParams,
)


# ---------------------------------------------------------------------------
# should_try_llm_fallback
# ---------------------------------------------------------------------------


class TestShouldTryLlmFallback:
    def test_principal_fallback_to_target(self) -> None:
        amounts = ParsedAmounts()
        params = ParsedInterestParams()
        assert should_try_llm_fallback(
            text="test", amounts=amounts, params=params, principal_fallback_to_target=True
        ) is True

    def test_wan_unit_mismatch(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100"))
        params = ParsedInterestParams()
        assert should_try_llm_fallback(
            text="被告支付52万元", amounts=amounts, params=params, principal_fallback_to_target=False
        ) is True

    def test_wan_unit_matched(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("520000"))
        params = ParsedInterestParams()
        assert should_try_llm_fallback(
            text="被告支付52万元", amounts=amounts, params=params, principal_fallback_to_target=False
        ) is False

    def test_fee_prepaid_context(self) -> None:
        amounts = ParsedAmounts(litigation_fee=Decimal("0"))
        params = ParsedInterestParams()
        assert should_try_llm_fallback(
            text="受理费5000元由被告负担，原告已预交",
            amounts=amounts,
            params=params,
            principal_fallback_to_target=False,
        ) is True

    def test_preservation_fee_prepaid(self) -> None:
        amounts = ParsedAmounts(preservation_fee=Decimal("0"))
        params = ParsedInterestParams()
        assert should_try_llm_fallback(
            text="保全费3000元由被告负担，原告已缴纳",
            amounts=amounts,
            params=params,
            principal_fallback_to_target=False,
        ) is True

    def test_start_date_no_rate(self) -> None:
        amounts = ParsedAmounts()
        params = ParsedInterestParams(start_date=date(2020, 1, 1))
        assert should_try_llm_fallback(
            text="test", amounts=amounts, params=params, principal_fallback_to_target=False
        ) is True

    def test_no_trigger(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"), litigation_fee=Decimal("5000"))
        params = ParsedInterestParams(multiplier=Decimal("1"))
        assert should_try_llm_fallback(
            text="被告支付10万元", amounts=amounts, params=params, principal_fallback_to_target=False
        ) is False


# ---------------------------------------------------------------------------
# _has_fee_prepaid_context
# ---------------------------------------------------------------------------


class TestHasFeePrepaidContext:
    def test_prepaid_match(self) -> None:
        text = "受理费5000元由被告负担，原告已预交"
        assert _has_fee_prepaid_context(text, fee_keywords=("受理费",)) is True

    def test_no_burden(self) -> None:
        text = "受理费5000元"
        assert _has_fee_prepaid_context(text, fee_keywords=("受理费",)) is False

    def test_no_prepaid(self) -> None:
        text = "受理费5000元由被告负担"
        assert _has_fee_prepaid_context(text, fee_keywords=("受理费",)) is False

    def test_no_keyword(self) -> None:
        text = "被告负担5000元，原告已预交"
        assert _has_fee_prepaid_context(text, fee_keywords=("受理费",)) is False

    def test_empty(self) -> None:
        assert _has_fee_prepaid_context("", fee_keywords=("受理费",)) is False


# ---------------------------------------------------------------------------
# merge_llm_fallback
# ---------------------------------------------------------------------------


class TestMergeLlmFallback:
    def test_merge_principal_when_fallback_to_target(self) -> None:
        amounts = ParsedAmounts()
        params = ParsedInterestParams()
        llm_data: dict[str, Any] = {
            "principal_amount": Decimal("100000"),
            "principal_label": "借款本金",
        }
        changed = merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=True
        )
        assert changed is True
        assert amounts.principal == Decimal("100000")

    def test_merge_principal_when_current_zero(self) -> None:
        amounts = ParsedAmounts()
        params = ParsedInterestParams()
        llm_data: dict[str, Any] = {"principal_amount": Decimal("50000")}
        changed = merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        assert changed is True
        assert amounts.principal == Decimal("50000")

    def test_merge_principal_when_current_small(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100"))
        params = ParsedInterestParams()
        llm_data: dict[str, Any] = {"principal_amount": Decimal("100000")}
        changed = merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        assert changed is True
        assert amounts.principal == Decimal("100000")

    def test_merge_litigation_fee(self) -> None:
        amounts = ParsedAmounts(litigation_fee=Decimal("0"))
        params = ParsedInterestParams()
        llm_data: dict[str, Any] = {"litigation_fee": Decimal("5000")}
        changed = merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        assert changed is True
        assert amounts.litigation_fee == Decimal("5000")

    def test_merge_start_date(self) -> None:
        amounts = ParsedAmounts()
        params = ParsedInterestParams()
        llm_data: dict[str, Any] = {"interest_start_date": date(2020, 6, 15)}
        changed = merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        assert changed is True
        assert params.start_date == date(2020, 6, 15)

    def test_merge_lpr_multiplier(self) -> None:
        amounts = ParsedAmounts()
        params = ParsedInterestParams()
        llm_data: dict[str, Any] = {"lpr_multiplier": Decimal("1.5")}
        changed = merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        assert changed is True
        assert params.multiplier == Decimal("1.5")
        assert "1.5倍" in params.rate_description

    def test_merge_fixed_rate(self) -> None:
        amounts = ParsedAmounts()
        params = ParsedInterestParams()
        llm_data: dict[str, Any] = {"fixed_rate_percent": Decimal("10")}
        changed = merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        assert changed is True
        assert params.custom_rate_value == Decimal("10")

    def test_merge_interest_base(self) -> None:
        amounts = ParsedAmounts()
        params = ParsedInterestParams()
        llm_data: dict[str, Any] = {"interest_base_amount": Decimal("200000")}
        changed = merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        assert changed is True
        assert params.base_amount == Decimal("200000")
        assert params.base_mode == "fixed_amount"

    def test_no_change(self) -> None:
        amounts = ParsedAmounts(
            principal=Decimal("100000"),
            litigation_fee=Decimal("5000"),
        )
        params = ParsedInterestParams(
            start_date=date(2020, 1, 1),
            multiplier=Decimal("1"),
        )
        llm_data: dict[str, Any] = {}
        changed = merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        assert changed is False

    def test_principal_label_contains_huo(self) -> None:
        amounts = ParsedAmounts()
        params = ParsedInterestParams()
        llm_data: dict[str, Any] = {
            "principal_amount": Decimal("50000"),
            "principal_label": "货款本金",
        }
        merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        assert amounts.principal_label == "货款本金"

    def test_principal_label_other(self) -> None:
        amounts = ParsedAmounts()
        params = ParsedInterestParams()
        llm_data: dict[str, Any] = {
            "principal_amount": Decimal("50000"),
            "principal_label": "借款本金",
        }
        merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        assert amounts.principal_label == "借款本金"

    def test_merge_preservation_fee(self) -> None:
        amounts = ParsedAmounts(preservation_fee=Decimal("0"))
        params = ParsedInterestParams()
        llm_data: dict[str, Any] = {"preservation_fee": Decimal("3000")}
        changed = merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        assert changed is True
        assert amounts.preservation_fee == Decimal("3000")

    def test_merge_attorney_fee(self) -> None:
        amounts = ParsedAmounts(attorney_fee=Decimal("0"))
        params = ParsedInterestParams()
        llm_data: dict[str, Any] = {"attorney_fee": Decimal("10000")}
        changed = merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        assert changed is True
        assert amounts.attorney_fee == Decimal("10000")

    def test_merge_announcement_fee(self) -> None:
        amounts = ParsedAmounts(announcement_fee=Decimal("0"))
        params = ParsedInterestParams()
        llm_data: dict[str, Any] = {"announcement_fee": Decimal("500")}
        changed = merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        assert changed is True
        assert amounts.announcement_fee == Decimal("500")

    def test_merge_guarantee_fee(self) -> None:
        amounts = ParsedAmounts(guarantee_fee=Decimal("0"))
        params = ParsedInterestParams()
        llm_data: dict[str, Any] = {"guarantee_fee": Decimal("2000")}
        changed = merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        assert changed is True
        assert amounts.guarantee_fee == Decimal("2000")

    def test_fixed_rate_only_when_no_multiplier(self) -> None:
        amounts = ParsedAmounts()
        params = ParsedInterestParams(multiplier=Decimal("1"))
        llm_data: dict[str, Any] = {"fixed_rate_percent": Decimal("10")}
        changed = merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        # Should not override existing multiplier
        assert params.multiplier == Decimal("1")
        assert params.custom_rate_value is None

    def test_lpr_only_when_no_rate(self) -> None:
        amounts = ParsedAmounts()
        params = ParsedInterestParams(custom_rate_value=Decimal("10"))
        llm_data: dict[str, Any] = {"lpr_multiplier": Decimal("1.5")}
        changed = merge_llm_fallback(
            amounts=amounts, params=params, llm_data=llm_data, principal_fallback_to_target=False
        )
        assert params.custom_rate_value == Decimal("10")
        assert params.multiplier is None


# ---------------------------------------------------------------------------
# _extract_json_object
# ---------------------------------------------------------------------------


class TestExtractJsonObject:
    def test_plain_json(self) -> None:
        result = _extract_json_object('{"key": "value"}')
        assert result == {"key": "value"}

    def test_markdown_fenced(self) -> None:
        result = _extract_json_object('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_markdown_plain(self) -> None:
        result = _extract_json_object('```\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_mixed_text(self) -> None:
        result = _extract_json_object('Here is the result: {"key": "value"} end')
        assert result == {"key": "value"}

    def test_empty(self) -> None:
        assert _extract_json_object("") is None

    def test_not_json(self) -> None:
        assert _extract_json_object("not json at all") is None

    def test_json_array(self) -> None:
        # Should return None because it's not a dict
        assert _extract_json_object("[1, 2, 3]") is None

    def test_none_input(self) -> None:
        assert _extract_json_object(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _parse_iso_date
# ---------------------------------------------------------------------------


class TestParseIsoDate:
    def test_valid(self) -> None:
        assert _parse_iso_date("2020-01-15") == date(2020, 1, 15)

    def test_none(self) -> None:
        assert _parse_iso_date(None) is None

    def test_empty(self) -> None:
        assert _parse_iso_date("") is None

    def test_invalid_format(self) -> None:
        assert _parse_iso_date("not-a-date") is None

    def test_whitespace(self) -> None:
        assert _parse_iso_date("  ") is None


# ---------------------------------------------------------------------------
# _parse_bool
# ---------------------------------------------------------------------------


class TestParseBool:
    def test_true_literal(self) -> None:
        assert _parse_bool(True) is True

    def test_false_literal(self) -> None:
        assert _parse_bool(False) is False

    def test_none(self) -> None:
        assert _parse_bool(None) is False

    def test_string_true(self) -> None:
        assert _parse_bool("true") is True

    def test_string_one(self) -> None:
        assert _parse_bool("1") is True

    def test_string_yes(self) -> None:
        assert _parse_bool("yes") is True

    def test_string_chinese(self) -> None:
        assert _parse_bool("是") is True

    def test_string_false(self) -> None:
        assert _parse_bool("false") is False

    def test_string_zero(self) -> None:
        assert _parse_bool("0") is False

    def test_string_no(self) -> None:
        assert _parse_bool("no") is False

    def test_string_chinese_no(self) -> None:
        assert _parse_bool("否") is False

    def test_unknown(self) -> None:
        assert _parse_bool("maybe") is False

    def test_integer(self) -> None:
        assert _parse_bool(42) is False
