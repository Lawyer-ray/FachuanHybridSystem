"""扫描件归档命名 / 版本对齐 / 副本识别（纯函数，无 DB）。

用例取自一次真实归档（40 页扫描件，案件名与当事人已脱敏），
文件名里的序号/版本即当时人工判断的结论，这里固化成断言防回退。
"""

from __future__ import annotations

import pytest

from apps.cases.services.material.scan_archive_naming import (
    SAME_PAGE_MAX_DISTANCE,
    SINGLE_PAGE_MAX_DISTANCE,
    build_archive_name,
    documents_match,
    fallback_subdir,
    group_copies,
    infer_target_name,
    page_aware_max_distance,
    pages_match,
    parse_document_name,
    resolve_subdir,
    signature_distance,
)

CASE = "张某诉某公司买卖合同纠纷一案"
LITIGATION_SUBDIRS = [
    "1-起诉状",
    "2-当事人身份证明",
    "3-委托材料",
    "4-证据目录",
    "5-证据材料",
    "6-送达地址确认书",
    "7-退费账户确认书",
    "8-保全申请书及保函",
    "9-其他立案材料",
]


class TestParseDocumentName:
    def test_parses_real_archive_name(self):
        parsed = parse_document_name(f"1-传统起诉状（{CASE}）V4_20261106.pdf")
        assert parsed is not None
        assert (parsed.ordinal, parsed.doc_type, parsed.version, parsed.date, parsed.ext) == (
            1,
            "传统起诉状",
            4,
            "20261106",
            "pdf",
        )
        assert parsed.case_name == CASE

    def test_parses_halfwidth_parens(self):
        parsed = parse_document_name(f"2-要素式起诉状({CASE})V3_20260924.docx")
        assert parsed is not None
        assert (parsed.ordinal, parsed.doc_type, parsed.version) == (2, "要素式起诉状", 3)

    @pytest.mark.parametrize(
        "filename",
        [
            "证据材料.pdf",  # 无序号
            "扫描件001.pdf",  # 无文书名/版本
            f"1-传统起诉状（{CASE}）V4.pdf",  # 无日期
            f"1-传统起诉状（{CASE}）20261106.pdf",  # 无版本
            "",
        ],
    )
    def test_rejects_non_conforming_names(self, filename):
        assert parse_document_name(filename) is None


class TestInferTargetName:
    def test_scan_follows_existing_draft_version_not_bumped(self):
        """同目录已有 V4 草稿 → 签章扫描件仍是 V4，不是 V5。"""
        existing = [
            f"1-传统起诉状（{CASE}）V4_20261106.docx",
            f"1-传统起诉状（{CASE}）V4_20261106.pdf",
            f"2-要素式起诉状（{CASE}）V4_20261106.docx",
        ]
        traditional = infer_target_name(existing, doc_type="传统起诉状", case_name=CASE)
        assert (traditional.ordinal, traditional.version, traditional.matched_existing) == (1, 4, True)

        element = infer_target_name(existing, doc_type="要素式起诉状", case_name=CASE)
        assert (element.ordinal, element.version, element.matched_existing) == (2, 4, True)

    def test_takes_max_version_among_existing(self):
        existing = [
            f"3-证据清单（{CASE}）V2_20261103.docx",
            f"3-证据清单（{CASE}）V3_20261106.docx",
        ]
        target = infer_target_name(existing, doc_type="证据清单", case_name=CASE)
        assert (target.ordinal, target.version) == (3, 3)

    def test_new_document_gets_next_ordinal_and_v1(self):
        existing = [
            f"1-传统起诉状（{CASE}）V4_20261106.docx",
            f"2-要素式起诉状（{CASE}）V4_20261106.docx",
        ]
        target = infer_target_name(existing, doc_type="财产保全申请书", case_name=CASE)
        assert (target.ordinal, target.version, target.matched_existing) == (3, 1, False)

    def test_empty_folder_starts_at_1(self):
        target = infer_target_name([], doc_type="起诉状", case_name=CASE)
        assert (target.ordinal, target.version) == (1, 1)

    def test_ignores_unparseable_names(self):
        existing = ["扫描件001.pdf", "notes.txt", f"7-送达地址确认书（{CASE}）V1_20261105.docx"]
        target = infer_target_name(existing, doc_type="送达地址确认书", case_name=CASE)
        assert (target.ordinal, target.version) == (7, 1)

    def test_doc_type_match_beats_case_name(self):
        """文件名里的案件名与当前案名不一致（历史改名）时，仍按文书名对齐。"""
        existing = ["1-传统起诉状（旧案名）V2_20260101.docx"]
        target = infer_target_name(existing, doc_type="传统起诉状", case_name=CASE)
        assert (target.ordinal, target.version) == (1, 2)


class TestBuildArchiveName:
    def test_round_trip_with_real_name(self):
        name = build_archive_name(
            ordinal=1, doc_type="传统起诉状", case_name=CASE, version=4, date="20261106", ext="pdf"
        )
        assert name == f"1-传统起诉状（{CASE}）V4_20261106.pdf"
        assert parse_document_name(name) is not None

    @pytest.mark.parametrize("kwargs", [{"ordinal": 0}, {"version": 0}, {"date": "2026-11-06"}, {"date": "2026"}])
    def test_rejects_invalid_inputs(self, kwargs):
        params = {"ordinal": 1, "doc_type": "起诉状", "case_name": CASE, "version": 1, "date": "20261106"}
        params.update(kwargs)
        with pytest.raises(ValueError):
            build_archive_name(**params)


class TestResolveSubdir:
    @pytest.mark.parametrize(
        "material_type,expected",
        [
            ("complaint", "1-起诉状"),
            ("起诉状", "1-起诉状"),
            ("party_identity", "2-当事人身份证明"),
            ("authorization_materials", "3-委托材料"),
            ("evidence_list", "4-证据目录"),
            ("delivery_address_confirmation", "6-送达地址确认书"),
            ("refund_account_confirmation", "7-退费账户确认书"),
            ("preservation_materials", "8-保全申请书及保函"),
        ],
    )
    def test_maps_segment_type_to_existing_subdir(self, material_type, expected):
        assert resolve_subdir(LITIGATION_SUBDIRS, material_type) == expected

    def test_matches_subdir_without_exact_node_name(self):
        """换模板后节点名变成「1-起诉状和反诉答辩状」，仍应命中。"""
        assert resolve_subdir(["1-起诉状和反诉答辩状"], "complaint") == "1-起诉状和反诉答辩状"

    def test_unknown_type_returns_none(self):
        assert resolve_subdir(LITIGATION_SUBDIRS, "unrecognized") is None

    def test_empty_subdirs_returns_none(self):
        assert resolve_subdir([], "complaint") is None

    def test_fallback_prefers_other_filing_materials(self):
        assert fallback_subdir(LITIGATION_SUBDIRS) == "9-其他立案材料"
        assert fallback_subdir(["2-庭审准备", "6-其他材料"]) == "6-其他材料"
        assert fallback_subdir(["1-起诉状"]) is None


# ── 副本识别 ────────────────────────────────────────────────────────────────


def _page(base: float, *, noise: float = 0.0, size: int = 8) -> list[float]:
    """构造一页的灰度指纹：`base` 决定内容，`noise` 模拟扫描噪点。"""
    return [base + (noise if i % 2 == 0 else -noise) for i in range(size)]


class TestPageMatching:
    def test_identical_pages_match(self):
        assert pages_match(_page(0.5), _page(0.5))

    def test_small_noise_still_matches(self):
        """三份打印件的签章位置与噪点不同，平均差约 0.02–0.05。"""
        noisy = _page(0.5, noise=SAME_PAGE_MAX_DISTANCE * 0.8)
        assert pages_match(_page(0.5), noisy)

    def test_different_pages_do_not_match(self):
        assert not pages_match(_page(0.5), _page(0.9))

    def test_length_mismatch_is_treated_as_different(self):
        assert signature_distance([0.1] * 8, [0.1] * 4) == 1.0
        assert not pages_match([0.1] * 8, [0.1] * 4)

    def test_empty_signatures_do_not_match(self):
        assert not pages_match([], [])


class TestDocumentsMatch:
    def test_same_length_and_similar_pages_match(self):
        a = [_page(0.3), _page(0.7)]
        b = [_page(0.3, noise=0.02), _page(0.7, noise=0.02)]
        assert documents_match(a, b)

    def test_page_count_must_be_equal(self):
        assert not documents_match([_page(0.3)], [_page(0.3), _page(0.7)])

    def test_one_differing_page_breaks_the_match(self):
        a = [_page(0.3), _page(0.7)]
        b = [_page(0.3), _page(0.9)]
        assert not documents_match(a, b)


class TestGroupCopies:
    def test_three_copies_group_together_and_primary_is_first(self):
        """一案三份：三份起诉状（每份 2 页）应归为一组，第一份是正本。"""
        docs = {
            "seg-1": [_page(0.3), _page(0.7)],
            "seg-2": [_page(0.3, noise=0.02), _page(0.7, noise=0.02)],
            "seg-3": [_page(0.3, noise=0.025), _page(0.7, noise=0.025)],
            "seg-4": [_page(0.4), _page(0.8)],  # 另一份文书
        }
        assert group_copies(docs) == [["seg-1", "seg-2", "seg-3"]]

    def test_no_duplicates_returns_empty(self):
        docs = {"a": [_page(0.3)], "b": [_page(0.4)]}
        assert group_copies(docs) == []

    def test_same_content_different_length_is_not_a_copy(self):
        """同类型不同份数（1 页 vs 2 页）不能判成副本。"""
        docs = {"a": [_page(0.3)], "b": [_page(0.3), _page(0.3)]}
        assert group_copies(docs) == []

    def test_grouping_is_stable_across_insertion_order(self):
        docs = {
            "x": [_page(0.5)],
            "y": [_page(0.5, noise=0.01)],
            "z": [_page(0.6)],
        }
        assert group_copies(docs) == [["x", "y"]]


class TestPageAwareThreshold:
    """单页文书阈值更严：单页只有一次证据，误判代价全压在这一页上。"""

    def test_threshold_depends_on_page_count(self):
        assert page_aware_max_distance(0) == SINGLE_PAGE_MAX_DISTANCE
        assert page_aware_max_distance(1) == SINGLE_PAGE_MAX_DISTANCE
        assert page_aware_max_distance(2) == SAME_PAGE_MAX_DISTANCE
        assert SINGLE_PAGE_MAX_DISTANCE < SAME_PAGE_MAX_DISTANCE

    def test_single_page_pair_in_the_gap_is_not_grouped(self):
        """实测有一对不同单页文书距离 0.027，落在多页阈值内但超过单页阈值。"""
        docs = {
            "a": [_page(0.5)],
            "b": [_page(0.5, noise=0.027)],
        }
        assert group_copies(docs) == []

    def test_multi_page_pair_in_the_gap_is_grouped(self):
        docs = {
            "a": [_page(0.3), _page(0.7)],
            "b": [_page(0.3, noise=0.027), _page(0.7, noise=0.027)],
        }
        assert group_copies(docs) == [["a", "b"]]

    def test_explicit_max_distance_overrides_page_heuristic(self):
        docs = {"a": [_page(0.5)], "b": [_page(0.5, noise=0.027)]}
        assert group_copies(docs, max_distance=SAME_PAGE_MAX_DISTANCE) == [["a", "b"]]
