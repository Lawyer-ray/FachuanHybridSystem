"""OCR 容错：数字夹缝里的空白是识别噪声，不是内容。

基线数字件写 `998,702.06`，OCR 常把它读成 `998 702.06`。归一化后两者的金额必须
能对齐——否则每一份扫描回传件都会凭空多出一条「金额不一致」的红线，而律师核对
三份之后就不再看红线了。

逗号（千分位）的口径**不在这里动**：它仍由 `domain.compare._canonical_amount`
统一去掉，本模块只删「数字 + 空白 + 数字」里的空白。
"""

from __future__ import annotations

import pytest

from apps.doc_verify.domain.normalize import normalize_text


class TestDigitGapFromOcr:
    def test_space_between_digits_is_removed(self) -> None:
        assert normalize_text("合计998 702.06元") == "合计998702.06元"

    def test_ideographic_space_between_digits_is_removed(self) -> None:
        # 全角空格先由 PUNCT_MAP 折成半角，再按同一个口径删掉
        assert normalize_text("合计998　702.06元") == "合计998702.06元"

    def test_ocr_spacing_normalizes_the_same_way_as_the_comma_base_line(self) -> None:
        """两侧归一化后只差千分位逗号——那是金额口径的事，不是「改了字」。"""
        assert normalize_text("合计998 702.06元") == "合计998702.06元"
        assert normalize_text("合计998,702.06元") == "合计998,702.06元"

    def test_thousands_separator_is_not_rewritten(self) -> None:
        assert normalize_text("998,702.06") == "998,702.06"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("998702.06 元", "998702.06 元"),  # 数字与单位之间的空格不是识别噪声
            ("共 5 件，第 3 项", "共 5 件,第 3 项"),  # 汉字与数字之间的空格是排版
            ("原告 张三 被告 李四", "原告 张三 被告 李四"),  # 汉字之间的空格同样不许删
        ],
    )
    def test_only_digit_to_digit_gaps_are_removed(self, raw: str, expected: str) -> None:
        assert normalize_text(raw) == expected

    def test_line_break_between_digits_is_not_glued(self) -> None:
        """换行是段落边界：整篇上删「数字间空白」会把两行正文粘成一行。"""
        assert normalize_text("金额 100\n200 元") == "金额 100\n200 元"
