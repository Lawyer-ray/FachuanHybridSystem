"""`clause_split`：四级降级每一级都要有用例，且行级绝不伪装成条款级。

这一组钉死的是 B4 的地基：后面所有"第 X 条有三种改法"都以 ``clause_key`` 为准。
切分错位的代价不是"少一条提示"，而是把两份无关的 patch 对齐成一条根本不存在的
"条款冲突"——律师会花时间裁决一个幻觉。所以除了每级各一个用例外，还专门锁：

- 四级全不命中 → ``granularity="line"``、``aligned=False``；
- 只有一个条款标记（切出来是一整块）也要继续降级；
- 每个 span 的 ``text`` 必须与 ``source[start:end]`` 逐字相等；
- 重复的"第三条"要加后缀，不能让两份无关 patch 撞到同一 key。
"""

from __future__ import annotations

from apps.contract_review.services.alignment.clause_split import ClauseSplit, split_clauses


def _assert_spans_exact(text: str, split: ClauseSplit) -> None:
    for span in split.spans:
        assert text[span.start : span.end] == span.text
    for previous, current in zip(split.spans, split.spans[1:], strict=False):
        assert previous.end <= current.start


class TestHeadingLevel:
    def test_chapter_headings_win_over_clause_numbers(self) -> None:
        text = "\n".join(
            [
                "第一章 总则",
                "第一条 定义",
                "本合同所称设备指……",
                "第二章 付款",
                "第二条 付款方式",
                "甲方应于三十日内付款。",
            ]
        )

        split = split_clauses(text)

        assert split.aligned is True
        assert split.granularity == "heading"
        assert split.keys == ("第一章", "第二章")
        assert split.spans[0].text.startswith("第一章 总则")
        assert split.spans[1].text.startswith("第二章 付款")
        _assert_spans_exact(text, split)

    def test_preamble_is_kept_with_heading_level(self) -> None:
        text = "买卖合同\n第一章 总则\n第一条 定义\n本合同所称设备指……\n第二章 付款\n第二条 付款方式\n甲方应于三十日内付款。"

        split = split_clauses(text)

        assert split.granularity == "heading"
        assert split.keys == ("前言", "第一章", "第二章")
        assert split.spans[0].text == "买卖合同\n"
        _assert_spans_exact(text, split)


class TestClauseNumberLevel:
    def test_article_numbers_split_when_no_headings(self) -> None:
        text = "\n".join(
            [
                "第一条 合同标的",
                "甲方向乙方采购设备十台。",
                "第二条 付款方式",
                "甲方应于收到发票后三十日内支付货款。",
                "第三条 争议解决",
                "提交乙方所在地仲裁委员会仲裁。",
            ]
        )

        split = split_clauses(text)

        assert split.aligned is True
        assert split.granularity == "clause_number"
        assert split.keys == ("第一条", "第二条", "第三条")
        _assert_spans_exact(text, split)

    def test_chinese_ordinal_and_decimal_numbering(self) -> None:
        text = "\n".join(
            [
                "一、合同标的",
                "甲方向乙方采购设备十台。",
                "1.1 付款方式",
                "甲方应于三十日内付款。",
                "（三）争议解决",
                "提交仲裁。",
            ]
        )

        split = split_clauses(text)

        assert split.granularity == "clause_number"
        assert split.keys == ("一", "1.1", "（三）")
        _assert_spans_exact(text, split)

    def test_single_clause_marker_degrades_instead_of_claiming_clause_level(self) -> None:
        text = "第一条 合同标的\n甲方向乙方采购设备十台。"

        split = split_clauses(text)

        assert split.granularity == "line"
        assert split.aligned is False
        assert split.keys == ("L1", "L2")

    def test_duplicate_clause_numbers_get_unique_suffixes(self) -> None:
        text = "\n".join(
            [
                "第一条 定义",
                "本合同所称设备指……",
                "第二条 付款",
                "甲方应于三十日内付款。",
                "第一条 定义（附件）",
                "附件中的设备范围同上。",
            ]
        )

        split = split_clauses(text)

        assert split.granularity == "clause_number"
        assert split.keys == ("第一条", "第二条", "第一条#2")
        _assert_spans_exact(text, split)


class TestParagraphLevel:
    def test_blank_line_paragraphs(self) -> None:
        text = "甲方应于三十日内付款。\n\n乙方应于十日内交货。\n\n争议提交仲裁。"

        split = split_clauses(text)

        assert split.aligned is True
        assert split.granularity == "paragraph"
        assert split.keys == ("P1", "P2", "P3")
        assert [span.text for span in split.spans] == [
            "甲方应于三十日内付款。\n",
            "乙方应于十日内交货。\n",
            "争议提交仲裁。",
        ]
        _assert_spans_exact(text, split)


class TestSentenceLevel:
    def test_sentences_when_no_blank_lines(self) -> None:
        text = "甲方应于三十日内付款。乙方应于十日内交货。争议提交仲裁。"

        split = split_clauses(text)

        assert split.aligned is True
        assert split.granularity == "sentence"
        assert split.keys == ("S1", "S2", "S3")
        assert [span.text for span in split.spans] == [
            "甲方应于三十日内付款。",
            "乙方应于十日内交货。",
            "争议提交仲裁。",
        ]
        _assert_spans_exact(text, split)


class TestLineFallback:
    def test_no_level_matches_returns_line_with_aligned_false(self) -> None:
        text = "甲方应于三十日内付款\n乙方应于十日内交货\n争议提交仲裁"

        split = split_clauses(text)

        assert split.aligned is False
        assert split.granularity == "line"
        assert split.keys == ("L1", "L2", "L3")
        _assert_spans_exact(text, split)

    def test_empty_text_is_line_level_not_clause_level(self) -> None:
        split = split_clauses("")

        assert split.spans == ()
        assert split.aligned is False
        assert split.granularity == "line"

    def test_whitespace_only_text_is_line_level(self) -> None:
        split = split_clauses("  \n\t\n")

        assert split.spans == ()
        assert split.aligned is False
        assert split.granularity == "line"
