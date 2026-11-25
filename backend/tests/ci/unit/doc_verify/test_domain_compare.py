"""`domain/compare.py` 的单测：五级断言的判定顺序，以及「不许瞎报」的每一条约束。

这里的错法只有两种，两种都很贵：
- **假红**（律师被叫去看一条其实没变的金额）——多了几次就没人再看报告；
- **假绿**（改了字却给出「核对通过」）——那是把一份没核对过的文书放进卷宗。

所以每个用例都同时钉住「该报的报了」与「不该报的没报」，而不是只看有没有 findings。
"""

from __future__ import annotations

import pytest

from apps.cases.services.material.scan_archive_naming import SAME_PAGE_MAX_DISTANCE as ARCHIVE_SAME_PAGE_MAX_DISTANCE
from apps.cases.services.material.scan_archive_naming import signature_distance
from apps.doc_verify.domain.compare import SAME_PAGE_MAX_DISTANCE, compare_documents, page_distance
from apps.doc_verify.domain.contracts import Baseline, Inbound, Report
from apps.doc_verify.domain.normalize import PAGE_SEPARATOR
from apps.doc_verify.domain.states import (
    STATE_CHANGED,
    STATE_IDENTICAL,
    STATE_NO_DIFFERENCE_DETECTED,
    STATE_UNVERIFIABLE,
    STATE_VERIFIED_CLEAN,
    derive_state,
)

#: 三页指纹：B 与 A 只差 0.01（同一页的正常抖动），C 与 A 差得远（整页换了）。
PAGE_A = (0.10, 0.20, 0.30)
PAGE_B = (0.11, 0.21, 0.31)
PAGE_C = (0.50, 0.60, 0.70)

#: 一份带金额、日期、案号、诉请三项的起诉状正文。
CONTRACT_TEXT = "\n".join(
    [
        "民事起诉状",
        "诉讼请求:",
        "1. 请求判令被告偿还借款本金998702.06元",
        "2. 请求判令被告支付利息",
        "3. 请求判令被告承担本案诉讼费",
        "事实与理由:",
        "原告与被告于2026年11月25日签订借款合同，案号（2026）粤0604民初1234号。",  # privacy-allow 虚构样例
    ]
)


def _baseline(
    *, text: str = "", page_count: int = 1, signatures: tuple[tuple[float, ...], ...] = (), sha: str = "sha-baseline"
) -> Baseline:
    return Baseline(
        doc_type="起诉状", version="V1", sha256=sha, page_count=page_count, page_signatures=signatures, text=text
    )


def _inbound(
    *, text: str = "", page_count: int = 1, signatures: tuple[tuple[float, ...], ...] = (), sha: str = "sha-inbound"
) -> Inbound:
    return Inbound(sha256=sha, page_count=page_count, page_signatures=signatures, text=text)


def _codes(report: Report) -> list[str]:
    return [finding.code for finding in report.findings]


class TestShortCircuit:
    def test_same_sha_returns_no_findings_at_all(self) -> None:
        # 字节相同：页数、指纹、正文全都对不上也不许算——数字件原样回传是最常见的路径
        baseline = _baseline(sha="same", page_count=9, signatures=(PAGE_A,), text="完全不同的基线正文")
        inbound = _inbound(sha="same", page_count=1, signatures=(PAGE_C,), text="另一份内容998670.21元")
        report = compare_documents(baseline, inbound)
        assert report.findings == []
        assert report.coverage["bytes_identical"] is True
        assert derive_state(report) == STATE_IDENTICAL

    def test_empty_sha_is_not_byte_identical(self) -> None:
        # 两侧都没算 sha（都是空串）不是「相同」的证据，该走的断言一条不许跳
        report = compare_documents(_baseline(sha=""), _inbound(sha=""))
        assert report.coverage.get("bytes_identical") is False
        assert derive_state(report) == STATE_NO_DIFFERENCE_DETECTED


class TestPackageAndPageLevel:
    def test_page_count_mismatch_is_red(self) -> None:
        report = compare_documents(_baseline(page_count=3), _inbound(page_count=2))
        assert _codes(report) == ["PAGE_COUNT_MISMATCH"]
        finding = report.findings[0]
        assert finding.severity == "red"
        assert (finding.expected, finding.actual) == ("3", "2")
        assert derive_state(report) == STATE_CHANGED

    def test_changed_page_is_reported_with_page_number(self) -> None:
        report = compare_documents(
            _baseline(page_count=3, signatures=(PAGE_A, PAGE_A, PAGE_A)),
            _inbound(page_count=3, signatures=(PAGE_A, PAGE_B, PAGE_C)),
        )
        assert _codes(report) == ["PAGE_CHANGED"]
        # PAGE_B 只差 0.01（签章/噪点级别的抖动），不许报；C 换了整页，第 3 页
        assert report.findings[0].page == 3
        assert report.findings[0].severity == "yellow"

    def test_distance_exactly_at_threshold_is_tolerated(self) -> None:
        baseline = _baseline(page_count=1, signatures=((0.0, 0.0, 0.0),))
        inbound = _inbound(page_count=1, signatures=((0.03, 0.03, 0.03),))
        assert compare_documents(baseline, inbound).findings == []

    def test_pages_without_fingerprints_on_both_sides_are_skipped(self) -> None:
        report = compare_documents(_baseline(page_count=2), _inbound(page_count=2))
        assert report.findings == []


class TestFieldLevel:
    def test_amount_change_from_998702_to_998670_is_red(self) -> None:
        inbound_text = CONTRACT_TEXT.replace("998702.06", "998670.21")
        report = compare_documents(_baseline(text=CONTRACT_TEXT), _inbound(text=inbound_text))
        assert "AMOUNT_MISMATCH" in _codes(report)
        finding = next(f for f in report.findings if f.code == "AMOUNT_MISMATCH")
        assert finding.severity == "red"
        assert "998702.06元" in finding.expected
        assert "998670.21元" in finding.actual
        assert derive_state(report) == STATE_CHANGED

    def test_thousands_separator_is_not_a_difference(self) -> None:
        inbound_text = CONTRACT_TEXT.replace("998702.06", "998,702.06")
        report = compare_documents(_baseline(text=CONTRACT_TEXT), _inbound(text=inbound_text))
        assert "AMOUNT_MISMATCH" not in _codes(report)

    def test_date_change_is_red(self) -> None:
        inbound_text = CONTRACT_TEXT.replace("2026年11月25日", "2026年11月26日")
        report = compare_documents(_baseline(text=CONTRACT_TEXT), _inbound(text=inbound_text))
        finding = next(f for f in report.findings if f.code == "DATE_MISMATCH")
        assert finding.severity == "red"
        assert (finding.expected, finding.actual) == ("2026年11月25日", "2026年11月26日")

    def test_zero_padded_date_is_not_a_difference(self) -> None:
        inbound_text = CONTRACT_TEXT.replace("2026年11月25日", "2026年11月05日")
        report = compare_documents(_baseline(text=CONTRACT_TEXT), _inbound(text=inbound_text))
        # 05 与 25 差的是日，不是格式；这条只保证「补零不敏感」不会被当成同一天
        assert next(f for f in report.findings if f.code == "DATE_MISMATCH").expected == "2026年11月25日"

    def test_case_number_full_width_parens_are_not_a_difference(self) -> None:
        inbound_text = CONTRACT_TEXT.replace("（2026）", "(2026)")
        report = compare_documents(_baseline(text=CONTRACT_TEXT), _inbound(text=inbound_text))
        assert report.findings == []
        assert derive_state(report) == STATE_VERIFIED_CLEAN

    def test_claim_item_count_change_is_red(self) -> None:
        inbound_text = CONTRACT_TEXT.replace("2. 请求判令被告支付利息\n", "")
        report = compare_documents(_baseline(text=CONTRACT_TEXT), _inbound(text=inbound_text))
        finding = next(f for f in report.findings if f.code == "CLAIM_COUNT_MISMATCH")
        assert (finding.expected, finding.actual) == ("3", "2")

    def test_amount_deleted_entirely_is_still_red(self) -> None:
        # 整笔金额被删掉是最坏的方向，不能因为「回传侧一处都没有」就当字段缺失跳过
        inbound_text = CONTRACT_TEXT.replace("本金998702.06元", "本金")
        report = compare_documents(_baseline(text=CONTRACT_TEXT), _inbound(text=inbound_text))
        assert "AMOUNT_MISMATCH" in _codes(report)

    def test_field_checks_cover_all_four_kinds(self) -> None:
        report = compare_documents(_baseline(text=CONTRACT_TEXT), _inbound(text=CONTRACT_TEXT))
        assert report.coverage["fields_checked"] == 4
        assert report.coverage["fields_skipped"] == 0

    def test_field_checks_are_skipped_when_one_side_has_no_text(self) -> None:
        report = compare_documents(_baseline(text=CONTRACT_TEXT), _inbound(text=""))
        assert report.coverage["fields_checked"] == 0
        assert report.coverage["fields_skipped"] == 4
        assert report.findings == []


class TestParagraphLevel:
    def test_deleted_sentence_is_yellow(self) -> None:
        baseline_text = "第一段：原告与被告系朋友关系。\n第二段：被告因资金周转向原告借款。\n第三段：借款至今未还。"
        inbound_text = "第一段：原告与被告系朋友关系。\n第三段：借款至今未还。"
        report = compare_documents(_baseline(text=baseline_text), _inbound(text=inbound_text))
        assert _codes(report) == ["PARAGRAPH_MISSING"]
        assert report.findings[0].severity == "yellow"
        assert report.findings[0].expected.startswith("第二段")
        assert derive_state(report) == STATE_CHANGED

    def test_rewritten_sentence_reports_both_sides_clipped(self) -> None:
        baseline_text = "总述：本案争议焦点如下。\n原告张三与被告李四系朋友关系，被告因资金周转向原告借款，双方口头约定了还款时间与利息计算方式。"
        inbound_text = "总述：本案争议焦点如下。\n原告王五与被告赵六系同事关系，被告因购房需要向原告借款，双方书面约定了还款时间与利息计算方式。"
        report = compare_documents(_baseline(text=baseline_text), _inbound(text=inbound_text))
        finding = next(f for f in report.findings if f.code == "PARAGRAPH_CHANGED")
        assert finding.expected.startswith("原告张三")
        assert finding.actual.startswith("原告王五")
        assert len(finding.expected) <= 121
        assert len(finding.actual) <= 121

    def test_whitespace_only_difference_is_not_reported(self) -> None:
        # OCR 在汉字与数字之间插空格是排版，不是改字；这类黄条一多，报告就没人看了
        baseline_text = "合计 998702.06 元，其中本金 900000 元。"
        inbound_text = "合计998702.06元，其中本金900000元。"
        report = compare_documents(_baseline(text=baseline_text), _inbound(text=inbound_text))
        assert report.findings == []

    def test_added_sentence_is_yellow(self) -> None:
        baseline_text = "第一段：原告与被告系朋友关系。"
        inbound_text = "第一段：原告与被告系朋友关系。\n第二段：被告另出具了还款承诺书。"
        report = compare_documents(_baseline(text=baseline_text), _inbound(text=inbound_text))
        assert _codes(report) == ["PARAGRAPH_ADDED"]


class TestCoverage:
    def test_tier_zero_scan_reports_no_gray_but_counts_pages(self) -> None:
        # 扫描回传件在免费层没有文本层：这是已知盲区，用状态与覆盖度表达，不逐页报 gray
        baseline = _baseline(text=CONTRACT_TEXT, page_count=1, signatures=(PAGE_A,))
        inbound = _inbound(text="", page_count=1, signatures=(PAGE_A,))
        report = compare_documents(baseline, inbound, tier=0)
        assert report.findings == []
        assert report.coverage["text_compared"] is False
        assert report.coverage["pages_no_text"] == 1
        assert derive_state(report) == STATE_NO_DIFFERENCE_DETECTED

    def test_tier_one_scan_reports_gray_per_page(self) -> None:
        baseline = _baseline(text="", page_count=2, signatures=(PAGE_A, PAGE_A))
        inbound = _inbound(text="", page_count=2, signatures=(PAGE_A, PAGE_A))
        report = compare_documents(baseline, inbound, tier=1)
        assert _codes(report) == ["PAGE_NO_TEXT", "PAGE_NO_TEXT"]
        assert [finding.page for finding in report.findings] == [1, 2]
        assert {finding.severity for finding in report.findings} == {"gray"}
        assert report.coverage["pages_no_text"] == 2
        assert derive_state(report) == STATE_UNVERIFIABLE

    def test_mixed_document_only_compares_pages_with_text_on_both_sides(self) -> None:
        # 回传件第 2 页没有文本层：基线那一页的句子不许被报成「少了一句」
        baseline_text = PAGE_SEPARATOR.join(["第一页：借款本金998702.06元。", "第二页：保证金条款另有约定。"])
        inbound_text = "第一页：借款本金998702.06元。"
        report = compare_documents(
            _baseline(text=baseline_text, page_count=2, signatures=(PAGE_A, PAGE_A)),
            _inbound(text=inbound_text, page_count=2, signatures=(PAGE_A, PAGE_A)),
            tier=0,
        )
        assert report.findings == []
        assert report.coverage["pages_with_text"] == 1
        assert report.coverage["pages_no_text"] == 1
        assert derive_state(report) == STATE_NO_DIFFERENCE_DETECTED

    def test_digital_inbound_clean_at_tier_zero_is_verified_clean(self) -> None:
        # 免费层也能逐字比数字件：比完干净就是真的干净
        report = compare_documents(
            _baseline(text=CONTRACT_TEXT, page_count=1, signatures=(PAGE_A,)),
            _inbound(text=CONTRACT_TEXT, page_count=1, signatures=(PAGE_A,)),
            tier=0,
        )
        assert report.findings == []
        assert report.coverage["text_compared"] is True
        assert report.coverage["pages_no_text"] == 0
        assert derive_state(report) == STATE_VERIFIED_CLEAN


class TestPageDistanceMatchesArchiveNaming:
    def test_threshold_matches_scan_archive_naming(self) -> None:
        assert SAME_PAGE_MAX_DISTANCE == ARCHIVE_SAME_PAGE_MAX_DISTANCE

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ((0.10, 0.20, 0.30), (0.10, 0.20, 0.30)),
            ((0.10, 0.20, 0.30), (0.14, 0.26, 0.36)),
            ((0.0, 0.0, 0.0, 0.0), (0.03, 0.03, 0.03, 0.03)),
            ((), (0.10,)),
            ((0.10,), ()),
            ((0.10, 0.20), (0.10, 0.20, 0.30)),
            ((0.0, 1.0), (1.0, 0.0)),
        ],
    )
    def test_same_result_as_signature_distance(self, left: tuple[float, ...], right: tuple[float, ...]) -> None:
        assert page_distance(left, right) == signature_distance(left, right)
