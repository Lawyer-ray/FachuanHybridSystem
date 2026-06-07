"""交费通知提取器测试。"""

from decimal import Decimal

import pytest

from apps.fee_notice.services.detection.extractor import FeeAmountExtractor, FEE_NAME_MAPPING


class TestFeeAmountExtractor:
    """FeeAmountExtractor 可测试逻辑。"""

    def _make_extractor(self):
        return FeeAmountExtractor()

    # ── _normalize_text ──

    def test_normalize_text_unifies_newlines(self):
        ext = self._make_extractor()
        result = ext._normalize_text("line1\r\nline2\rline3")
        assert "\r" not in result

    def test_normalize_text_unifies_table_borders(self):
        ext = self._make_extractor()
        result = ext._normalize_text("col1│col2┃col3")
        assert "│" not in result
        assert "┃" not in result

    def test_normalize_text_compresses_spaces(self):
        ext = self._make_extractor()
        result = ext._normalize_text("hello     world")
        assert "  " not in result

    # ── _match_fee_field ──

    def test_match_fee_field_acceptance(self):
        ext = self._make_extractor()
        assert ext._match_fee_field("案件受理费") == "acceptance_fee"

    def test_match_fee_field_acceptance_short(self):
        ext = self._make_extractor()
        assert ext._match_fee_field("受理费") == "acceptance_fee"

    def test_match_fee_field_application(self):
        ext = self._make_extractor()
        assert ext._match_fee_field("申请费") == "application_fee"

    def test_match_fee_field_preservation(self):
        ext = self._make_extractor()
        assert ext._match_fee_field("保全费") == "preservation_fee"

    def test_match_fee_field_preservation_full(self):
        ext = self._make_extractor()
        assert ext._match_fee_field("财产保全费") == "preservation_fee"

    def test_match_fee_field_execution(self):
        ext = self._make_extractor()
        assert ext._match_fee_field("执行费") == "execution_fee"

    def test_match_fee_field_other(self):
        ext = self._make_extractor()
        assert ext._match_fee_field("其他诉讼费") == "other_fee"

    def test_match_fee_field_other_short(self):
        ext = self._make_extractor()
        assert ext._match_fee_field("其他费用") == "other_fee"

    def test_match_fee_field_unknown(self):
        ext = self._make_extractor()
        assert ext._match_fee_field("未知费用") is None

    # ── _parse_amount ──

    def test_parse_amount_normal(self):
        ext = self._make_extractor()
        assert ext._parse_amount("1234.56") == Decimal("1234.56")

    def test_parse_amount_with_comma(self):
        ext = self._make_extractor()
        assert ext._parse_amount("1,234.56") == Decimal("1234.56")

    def test_parse_amount_with_unit(self):
        ext = self._make_extractor()
        assert ext._parse_amount("1234元") == Decimal("1234")

    def test_parse_amount_with_yuan_sign(self):
        ext = self._make_extractor()
        assert ext._parse_amount("￥1234") == Decimal("1234")

    def test_parse_amount_with_paren(self):
        ext = self._make_extractor()
        result = ext._parse_amount("1234(壹仟贰佰叁拾肆元)")
        assert result == Decimal("1234")

    def test_parse_amount_negative(self):
        ext = self._make_extractor()
        # The method strips "-" and extracts digits, so -100 becomes 100
        result = ext._parse_amount("-100")
        assert result is not None  # strips the negative sign

    def test_parse_amount_empty(self):
        ext = self._make_extractor()
        assert ext._parse_amount("") is None

    def test_parse_amount_none_input(self):
        ext = self._make_extractor()
        assert ext._parse_amount(None) is None

    def test_parse_amount_zero(self):
        ext = self._make_extractor()
        assert ext._parse_amount("0") == Decimal("0")

    def test_parse_amount_with_spaces(self):
        ext = self._make_extractor()
        assert ext._parse_amount(" 1234 ") == Decimal("1234")

    # ── _split_amount_row_by_space ──

    def test_split_amount_row_by_space(self):
        ext = self._make_extractor()
        result = ext._split_amount_row_by_space("金额 0 252.93 0 0")
        assert result == ["金额", "0", "252.93", "0", "0"]

    # ── _split_fee_header_by_space ──

    def test_split_fee_header_by_space(self):
        ext = self._make_extractor()
        result = ext._split_fee_header_by_space("收费项目名称 受理费 保全费 执行费 其他诉讼费")
        assert "受理费" in result
        assert "保全费" in result
        assert "执行费" in result
        assert "其他诉讼费" in result

    # ── _parse_table_row ──

    def test_parse_table_row_pipe(self):
        ext = self._make_extractor()
        result = ext._parse_table_row("col1 | col2 | col3")
        assert len(result) == 3

    def test_parse_table_row_tab(self):
        ext = self._make_extractor()
        result = ext._parse_table_row("col1\tcol2\tcol3")
        assert len(result) == 3

    # ── _extract_continuous_horizontal ──

    def test_extract_continuous_horizontal_match(self):
        ext = self._make_extractor()
        text = "收费项目名称 受理费 保全费 执行费 其他诉讼费 金额 100.00 252.93 0 0 应收金额 352.93"
        result = ext._extract_continuous_horizontal(text)
        assert result is not None
        assert result["acceptance_fee"] == Decimal("100.00")
        assert result["preservation_fee"] == Decimal("252.93")
        assert result["execution_fee"] == Decimal("0")
        assert result["other_fee"] == Decimal("0")

    def test_extract_continuous_horizontal_no_match(self):
        ext = self._make_extractor()
        text = "没有费用信息的文本"
        result = ext._extract_continuous_horizontal(text)
        assert result is None

    # ── _determine_fee_type ──

    def test_determine_fee_type_acceptance(self):
        ext = self._make_extractor()
        assert ext._determine_fee_type("案件受理费 100元") == "acceptance_fee"

    def test_determine_fee_type_preservation(self):
        ext = self._make_extractor()
        assert ext._determine_fee_type("保全费 200元") == "preservation_fee"

    def test_determine_fee_type_execution(self):
        ext = self._make_extractor()
        assert ext._determine_fee_type("执行费 300元") == "execution_fee"

    def test_determine_fee_type_unknown(self):
        ext = self._make_extractor()
        assert ext._determine_fee_type("随机文字") is None

    # ── _extract_named_fees ──

    def test_extract_named_fees_multiple(self):
        ext = self._make_extractor()
        text = "案件受理费100元\n保全费200元"
        result = {}
        ext._extract_named_fees(text, result)
        assert "acceptance_fee" in result
        assert "preservation_fee" in result

    def test_extract_named_fees_with_colon(self):
        ext = self._make_extractor()
        text = "受理费: 100"
        result = {}
        ext._extract_named_fees(text, result)
        assert "acceptance_fee" in result

    # ── _find_amount_in_vertical ──

    def test_find_amount_in_vertical_payable(self):
        ext = self._make_extractor()
        text = "应收金额 1234.56 (壹仟贰佰叁拾肆元伍角陆分)"
        result = ext._find_amount_in_vertical(text)
        assert result == Decimal("1234.56")

    def test_find_amount_in_vertical_total(self):
        ext = self._make_extractor()
        text = "总金额 5678.00"
        result = ext._find_amount_in_vertical(text)
        assert result == Decimal("5678.00")

    def test_find_amount_in_vertical_none(self):
        ext = self._make_extractor()
        text = "没有金额信息"
        result = ext._find_amount_in_vertical(text)
        assert result is None

    # ── extract (主方法) ──

    def test_extract_horizontal_table(self):
        ext = self._make_extractor()
        text = "收费项目名称 受理费 保全费 执行费 其他诉讼费\n金额 100 200 0 0\n应收金额 300"
        result = ext.extract(text)
        assert result.table_format in ("horizontal", "general")

    def test_extract_general_pattern(self):
        ext = self._make_extractor()
        text = "案件受理费100元\n保全费200元"
        result = ext.extract(text)
        assert result.table_format in ("general", "vertical", "horizontal")

    def test_extract_debug_mode(self):
        ext = self._make_extractor()
        text = "案件受理费100元"
        result = ext.extract(text, debug=True)
        assert result.debug_info is not None

    def test_extract_unknown_format(self):
        ext = self._make_extractor()
        text = "完全没有费用信息的文本"
        result = ext.extract(text)
        assert result.table_format == "unknown"
