"""`domain/normalize.py` 的单测：宽度、标记、空白、页码/页眉页脚、分页与分段。

重点不在「函数能跑」，在两件事：
1. 归一化口径与 `dual_engine._normalize` 同构（标点表逐项一致），否则同一份文书
   在两个模块里会得出两套「算不算差异」的结论；
2. 该删的（页码行、跨页重复的页眉页脚）删干净，不该删的（正文里重复出现的行、
   没有分页符时的重复行）一个字都不许动。
"""

from __future__ import annotations

import pytest

from apps.doc_verify.domain.normalize import (
    PAGE_SEPARATOR,
    PUNCT_MAP,
    normalize_text,
    similarity,
    split_pages,
    split_paragraphs,
)
from apps.pdf_splitting.services.split.dual_engine import _PUNCT_MAP


class TestPunctMap:
    def test_same_table_as_dual_engine(self) -> None:
        # 口径漂移是本模块最贵的错：一处标点折算不同，整卷都变成「有差异」
        assert dict(PUNCT_MAP) == dict(_PUNCT_MAP)


class TestNormalizeText:
    def test_full_width_punctuation_folds_to_half_width(self) -> None:
        raw = "（2026）粤0604民初1234号，合计998702.06元。"  # privacy-allow 虚构样例
        expected = "(2026)粤0604民初1234号,合计998702.06元."  # privacy-allow 虚构样例
        assert normalize_text(raw) == expected

    def test_markdown_marks_are_stripped(self) -> None:
        assert normalize_text("## 第一条\n**标的额**：12万元\n| 项目 | 金额 |") == "第一条\n标的额:12万元\n项目 金额"

    def test_list_bullet_is_stripped_but_numbering_is_kept(self) -> None:
        # `1.` 是诉请项编号（要靠它数项数），`-` 才是列表符号
        assert normalize_text("- 请求判令被告还款\n1. 请求判令被告还款") == "请求判令被告还款\n1. 请求判令被告还款"

    def test_latex_and_html_wrappers_keep_inner_text(self) -> None:
        assert normalize_text(r"<td>\underline{\text{佛山市}}</td>") == "佛山市"

    def test_horizontal_whitespace_is_compressed_newline_is_kept(self) -> None:
        assert normalize_text("甲方：  张三\t\t（身份证）\n乙方：李四") == "甲方: 张三 (身份证)\n乙方:李四"

    @pytest.mark.parametrize(
        "line",
        ["第 3 页 共 5 页", "- 3 -", "3/12", "Page 3 of 12", "共 5 页 第 3 页"],
    )
    def test_page_number_lines_are_dropped(self, line: str) -> None:
        assert normalize_text(f"{line}\n正文第一行") == "正文第一行"

    def test_empty_and_decorative_lines_are_dropped(self) -> None:
        assert normalize_text("\n\n---\n___\n正文\n\n") == "正文"

    def test_repeated_page_header_and_footer_are_dropped(self) -> None:
        text = PAGE_SEPARATOR.join(
            [
                "某某律师事务所\n致：张三\n正文甲\n正文乙\n第 1 页",
                "某某律师事务所\n致：张三\n正文丙\n正文丁\n第 2 页",
            ]
        )
        assert normalize_text(text) == "正文甲\n正文乙\n正文丙\n正文丁"

    def test_repeated_line_inside_single_page_is_kept(self) -> None:
        # 没有分页符时「重复」没有统计意义，硬删会把表格里的重复行当页眉删掉
        text = "当事人：张三\n当事人：张三\n正文"
        assert normalize_text(text) == "当事人:张三\n当事人:张三\n正文"

    def test_empty_input(self) -> None:
        assert normalize_text("") == ""


class TestSplitPages:
    def test_form_feed_splits_pages(self) -> None:
        assert split_pages("甲页\f乙页") == ["甲页", "乙页"]

    def test_without_separator_is_one_page(self) -> None:
        assert split_pages("整篇正文") == ["整篇正文"]

    def test_empty_text_is_zero_pages(self) -> None:
        assert split_pages("   \n ") == []

    def test_trailing_separator_is_not_an_extra_page(self) -> None:
        # pdfminer 逐页输出时每页后面都带一个换页符，末页后面必然多一个
        assert split_pages("甲页\f乙页\f") == ["甲页", "乙页"]

    def test_interior_empty_page_keeps_its_position(self) -> None:
        # 第 2 页没有文本层：保留空串，否则第 3 页会被当成第 2 页报出来
        assert split_pages("甲页\f\f丙页") == ["甲页", "", "丙页"]


class TestSplitParagraphs:
    def test_blank_lines_are_dropped(self) -> None:
        assert split_paragraphs("第一句\n\n\n第二句") == ["第一句", "第二句"]

    def test_normalization_applies_before_splitting(self) -> None:
        assert split_paragraphs("## 第一条\n\n**第二条**") == ["第一条", "第二条"]

    def test_empty_text_has_no_paragraphs(self) -> None:
        assert split_paragraphs("") == []


class TestSimilarity:
    def test_identical_text_is_one(self) -> None:
        assert similarity("请求判令被告偿还借款", "请求判令被告偿还借款") == 1.0

    def test_one_char_change_is_high_but_below_one(self) -> None:
        score = similarity("请求判令被告偿还借款998702.06元", "请求判令被告偿还借款998670.21元")
        assert 0.8 < score < 1.0

    def test_unrelated_text_is_low(self) -> None:
        assert similarity("请求判令被告偿还借款", "本页为送达地址确认书") < 0.3

    def test_two_empty_strings_are_identical(self) -> None:
        assert similarity("", "") == 1.0

    def test_one_empty_string_is_zero(self) -> None:
        assert similarity("正文", "") == 0.0
        assert similarity("", "正文") == 0.0
