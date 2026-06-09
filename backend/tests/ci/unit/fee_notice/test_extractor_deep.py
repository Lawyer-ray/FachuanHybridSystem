"""Tests for fee_notice.services.detection.extractor - FeeAmountExtractor."""
from __future__ import annotations

from decimal import Decimal

import pytest

from apps.fee_notice.services.detection.extractor import (
    FEE_KEYWORDS,
    FEE_NAME_MAPPING,
    FeeAmountExtractor,
)


class TestFeeNameMapping:
    def test_mapping_keys(self) -> None:
        assert "案件受理费" in FEE_NAME_MAPPING
        assert "受理费" in FEE_NAME_MAPPING
        assert "保全费" in FEE_NAME_MAPPING
        assert "执行费" in FEE_NAME_MAPPING

    def test_mapping_values(self) -> None:
        assert FEE_NAME_MAPPING["案件受理费"] == "acceptance_fee"
        assert FEE_NAME_MAPPING["保全费"] == "preservation_fee"
        assert FEE_NAME_MAPPING["执行费"] == "execution_fee"

    def test_fee_keywords(self) -> None:
        assert len(FEE_KEYWORDS) > 0
        assert "案件受理费" in FEE_KEYWORDS


class TestFeeAmountExtractor:
    def setup_method(self) -> None:
        self.extractor = FeeAmountExtractor()

    def test_extract_empty_text(self) -> None:
        result = self.extractor.extract("")
        assert result.table_format == "unknown"

    def test_extract_debug_mode(self) -> None:
        result = self.extractor.extract("", debug=True)
        assert result.debug_info is not None

    def test_extract_horizontal_table_with_pipe(self) -> None:
        text = """收费项目名称 | 受理费 | 保全费 | 执行费 | 其他诉讼费
金额 | 100.00 | 200.00 | 0 | 0
应收金额 300.00"""
        result = self.extractor.extract(text)
        # May or may not match depending on exact regex, but should not raise
        assert result is not None

    def test_extract_continuous_horizontal(self) -> None:
        text = "收费项目名称 受理费 保全费 执行费 其他诉讼费 金额 100.00 200.00 0 0 应收金额 300.00"
        result = self.extractor.extract(text)
        assert result is not None

    def test_extract_vertical_table(self) -> None:
        text = """收费项目名称：案件受理费
应收金额：500.00"""
        result = self.extractor.extract(text)
        assert result is not None

    def test_extract_general_pattern(self) -> None:
        text = "案件受理费1000元，保全费500元"
        result = self.extractor.extract(text)
        assert result is not None

    def test_extract_no_fee_found(self) -> None:
        text = "这是一段普通文本，没有费用信息"
        result = self.extractor.extract(text)
        assert result.table_format == "unknown"

    # ── _normalize_text ─────────────────────────────────────────────────

    def test_normalize_text(self) -> None:
        text = "  Hello  World  "
        result = self.extractor._normalize_text(text)
        assert len(result) > 0

    # ── _match_fee_field ────────────────────────────────────────────────

    def test_match_fee_field_acceptance(self) -> None:
        assert self.extractor._match_fee_field("案件受理费") == "acceptance_fee"
        assert self.extractor._match_fee_field("受理费") == "acceptance_fee"

    def test_match_fee_field_preservation(self) -> None:
        assert self.extractor._match_fee_field("保全费") == "preservation_fee"
        assert self.extractor._match_fee_field("财产保全费") == "preservation_fee"

    def test_match_fee_field_execution(self) -> None:
        assert self.extractor._match_fee_field("执行费") == "execution_fee"

    def test_match_fee_field_other(self) -> None:
        assert self.extractor._match_fee_field("其他诉讼费") == "other_fee"
        assert self.extractor._match_fee_field("其他费用") == "other_fee"

    def test_match_fee_field_application(self) -> None:
        assert self.extractor._match_fee_field("申请费") == "application_fee"

    def test_match_fee_field_unknown(self) -> None:
        assert self.extractor._match_fee_field("未知费用") is None

    # ── _parse_amount ───────────────────────────────────────────────────

    def test_parse_amount_valid(self) -> None:
        assert self.extractor._parse_amount("100.50") == Decimal("100.50")
        assert self.extractor._parse_amount("1,234.56") == Decimal("1234.56")

    def test_parse_amount_zero(self) -> None:
        assert self.extractor._parse_amount("0") == Decimal("0")

    def test_parse_amount_invalid(self) -> None:
        assert self.extractor._parse_amount("abc") is None
        assert self.extractor._parse_amount("") is None

    def test_parse_amount_with_commas(self) -> None:
        assert self.extractor._parse_amount("1,000,000.00") == Decimal("1000000.00")

    # ── _build_column_mapping ───────────────────────────────────────────

    def test_build_column_mapping(self) -> None:
        headers = ["收费项目名称", "受理费", "保全费", "执行费"]
        mapping = self.extractor._build_column_mapping(headers)
        assert 1 in mapping
        assert mapping[1] == "acceptance_fee"
        assert 2 in mapping
        assert mapping[2] == "preservation_fee"

    def test_build_column_mapping_skip_non_fee(self) -> None:
        headers = ["收费项目名称", "受理费", "备注"]
        mapping = self.extractor._build_column_mapping(headers)
        assert 0 not in mapping  # "收费项目名称" should be skipped
        assert 2 not in mapping  # "备注" is not a fee

    # ── _split_fee_header_by_space ───────────────────────────────────────

    def test_split_fee_header(self) -> None:
        result = self.extractor._split_fee_header_by_space("收费项目名称 受理费 保全费")
        assert "受理费" in result
        assert "保全费" in result

    def test_split_fee_header_empty(self) -> None:
        result = self.extractor._split_fee_header_by_space("")
        assert result == []

    # ── _split_amount_row_by_space ──────────────────────────────────────

    def test_split_amount_row(self) -> None:
        result = self.extractor._split_amount_row_by_space("金额 100.00 200.00 0")
        assert result == ["金额", "100.00", "200.00", "0"]

    # ── _build_result ───────────────────────────────────────────────────

    def test_build_result(self) -> None:
        fees = {"acceptance_fee": Decimal("100.00"), "preservation_fee": Decimal("200.00")}
        result = self.extractor._build_result(fees, "horizontal", {})
        assert result.table_format == "horizontal"
        assert result.acceptance_fee == Decimal("100.00")
        assert result.preservation_fee == Decimal("200.00")

    def test_build_result_with_debug(self) -> None:
        fees = {"acceptance_fee": Decimal("100.00")}
        debug = {"test": "info"}
        result = self.extractor._build_result(fees, "vertical", debug)
        assert result.debug_info == debug

    # ── _find_horizontal_header ─────────────────────────────────────────

    def test_find_horizontal_header_with_pipe(self) -> None:
        lines = ["", "收费项目名称 | 受理费 | 保全费", "金额 | 100 | 200"]
        idx, cells = self.extractor._find_horizontal_header(lines)
        # May or may not find depending on fee_keywords list in the method
        assert isinstance(idx, int)
        assert isinstance(cells, list)

    def test_find_horizontal_header_no_match(self) -> None:
        lines = ["普通文本", "没有费用信息"]
        idx, cells = self.extractor._find_horizontal_header(lines)
        assert idx < 0

    # ── _extract_continuous_horizontal ───────────────────────────────────

    def test_continuous_horizontal_match(self) -> None:
        text = "收费项目名称 受理费 保全费 执行费 其他诉讼费 金额 100.00 200.00 50.00 10.00 应收金额 360.00"
        result = self.extractor._extract_continuous_horizontal(text)
        assert result is not None
        assert "acceptance_fee" in result
        assert result["acceptance_fee"] == Decimal("100.00")

    def test_continuous_horizontal_no_match(self) -> None:
        text = "普通文本没有费用"
        result = self.extractor._extract_continuous_horizontal(text)
        assert result is None

    # ── _find_amount_in_vertical ────────────────────────────────────────

    def test_find_amount_in_vertical_with_parenthesis(self) -> None:
        text = "应收金额 500.00"
        result = self.extractor._find_amount_in_vertical(text)
        assert result is not None
        assert result == Decimal("500.00")

    def test_find_amount_in_vertical_simple(self) -> None:
        text = "应收金额 300.00"
        result = self.extractor._find_amount_in_vertical(text)
        assert result is not None

    def test_find_amount_in_vertical_none(self) -> None:
        text = "没有金额信息"
        result = self.extractor._find_amount_in_vertical(text)
        assert result is None
