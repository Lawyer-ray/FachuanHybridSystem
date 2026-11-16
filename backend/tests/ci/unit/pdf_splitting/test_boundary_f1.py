"""分段边界 precision/recall/F1 的判据单测（合成金标，不涉及真实卷宗）。

口径锁死：切点 = 某段末页页号；命中 = |pred-gold| <= tolerance 且**一对一**。
过切压 precision、漏切压 recall——这两个方向必须能分开测出来，否则调参不可证伪。
"""

from __future__ import annotations

import pytest

from apps.pdf_splitting.services.split.eval_metrics import (
    BoundaryScores,
    boundaries_from_segments,
    segment_boundary_scores,
)


class TestBoundariesFromSegments:
    def test_contiguous_segments_drop_last_end(self) -> None:
        """N 段连续覆盖 → N-1 个切点，末段末页不算边界。"""
        assert boundaries_from_segments([(1, 10), (11, 20), (21, 30)]) == [10, 20]

    def test_single_segment_has_no_boundary(self) -> None:
        """一份材料整册一段 → 0 个切点（不是 1 个）。"""
        assert boundaries_from_segments([(1, 164)]) == []

    def test_empty_input(self) -> None:
        assert boundaries_from_segments([]) == []

    def test_unsorted_input_is_ordered(self) -> None:
        assert boundaries_from_segments([(21, 30), (1, 10), (11, 20)]) == [10, 20]


class TestExactAlignment:
    def test_perfect_match_scores_one(self) -> None:
        scores = segment_boundary_scores([10, 20, 30], [10, 20, 30])

        assert scores == BoundaryScores(1.0, 1.0, 1.0, 3, 3, 3, 0)

    def test_over_segmentation_lowers_precision_only(self) -> None:
        """过切：多切一刀 → precision 掉，recall 仍满分。

        真实形态（579 包）：同一份房地产买卖合同被切成 p105-106 与 p107-110 两段。
        """
        gold = boundaries_from_segments([(1, 10), (11, 20), (21, 30)])
        pred = boundaries_from_segments([(1, 10), (11, 15), (16, 20), (21, 30)])

        scores = segment_boundary_scores(pred, gold)

        assert scores.matched == 2
        assert scores.predicted == 3 and scores.gold == 2
        assert scores.precision == pytest.approx(2 / 3)
        assert scores.recall == 1.0
        assert scores.f1 == pytest.approx(0.8)

    def test_under_segmentation_lowers_recall_only(self) -> None:
        """漏切：该切的没切 → recall 掉，precision 仍满分。

        真实形态（579 包）：p19「贷款申请核实清单_续」本该并入前段却独立成段，
        反过来也可能是续页合并过头把两份材料并成一段。
        """
        gold = boundaries_from_segments([(1, 10), (11, 20), (21, 30)])
        pred = boundaries_from_segments([(1, 20), (21, 30)])

        scores = segment_boundary_scores(pred, gold)

        assert scores.matched == 1
        assert scores.precision == 1.0
        assert scores.recall == pytest.approx(0.5)
        assert scores.f1 == pytest.approx(2 / 3)

    def test_off_by_one_is_a_miss_at_zero_tolerance(self) -> None:
        """容差 0：差一页就是没切对，不许四舍五入成命中。"""
        scores = segment_boundary_scores([11], [10], tolerance=0)

        assert scores.matched == 0
        assert scores.f1 == 0.0

    def test_disjoint_boundaries_score_zero(self) -> None:
        scores = segment_boundary_scores([5, 6], [50, 60])

        assert scores.matched == 0
        assert scores.precision == 0.0 and scores.recall == 0.0 and scores.f1 == 0.0


class TestTolerance:
    def test_off_by_one_hits_at_tolerance_one(self) -> None:
        scores = segment_boundary_scores([11], [10], tolerance=1)

        assert scores.matched == 1
        assert scores.f1 == 1.0
        assert scores.tolerance == 1

    def test_tolerance_is_inclusive_boundary(self) -> None:
        """|p-g| == tolerance 算命中，== tolerance+1 不算。"""
        assert segment_boundary_scores([12], [10], tolerance=2).matched == 1
        assert segment_boundary_scores([13], [10], tolerance=2).matched == 0

    def test_matching_is_one_to_one(self) -> None:
        """一个金标切点不许被两个预测切点重复认领——否则过切会被容差洗白。"""
        scores = segment_boundary_scores([10, 11], [10], tolerance=1)

        assert scores.matched == 1
        assert scores.precision == pytest.approx(0.5)
        assert scores.recall == 1.0

    def test_one_prediction_cannot_claim_two_gold_cuts(self) -> None:
        """对称方向也要一对一：一个预测切点只认领一个金标切点。"""
        scores = segment_boundary_scores([10], [10, 11], tolerance=1)

        assert scores.matched == 1
        assert scores.precision == 1.0
        assert scores.recall == pytest.approx(0.5)

    def test_exact_matches_are_claimed_before_near_ones(self) -> None:
        """先配 d=0：精确命中优先，剩下的才按容差配。"""
        scores = segment_boundary_scores([10, 11], [10, 12], tolerance=1)

        assert scores.matched == 2
        assert scores.f1 == 1.0

    def test_f1_is_monotone_in_tolerance(self) -> None:
        """放宽容差 F1 单调不减——否则这个度量不能用来做「容差敏感性」分析。"""
        pred = [9, 15, 22, 31]
        gold = [10, 20, 30]

        values = [segment_boundary_scores(pred, gold, tolerance=k).f1 for k in range(6)]

        assert values == sorted(values)

    def test_negative_tolerance_raises(self) -> None:
        """负容差直接报错，不静默夹到 0——那会让调参记录失真。"""
        with pytest.raises(ValueError, match="tolerance"):
            segment_boundary_scores([1], [1], tolerance=-1)


class TestEmptyAndDuplicateInputs:
    def test_both_empty_scores_one(self) -> None:
        """两侧都是单段材料 → 没有可错的边界，满分（与 table_cell_f1 同口径）。"""
        assert segment_boundary_scores([], []) == BoundaryScores(1.0, 1.0, 1.0, 0, 0, 0, 0)

    def test_prediction_empty_scores_zero(self) -> None:
        """一个边界都没切、金标有边界 → 0 分，不许用 1.0 兜底掩盖漏切。"""
        scores = segment_boundary_scores([], [10, 20])

        assert scores.f1 == 0.0
        assert scores.recall == 0.0
        assert scores.gold == 2 and scores.predicted == 0

    def test_gold_empty_scores_zero(self) -> None:
        scores = segment_boundary_scores([10, 20], [])

        assert scores.f1 == 0.0
        assert scores.precision == 0.0
        assert scores.predicted == 2 and scores.gold == 0

    def test_duplicates_are_deduped(self) -> None:
        """同一页重复给切点不该被算成多个边界。"""
        scores = segment_boundary_scores([10, 10, 20, 20], [10, 20])

        assert scores.predicted == 2
        assert scores.f1 == 1.0

    def test_unsorted_input_is_accepted(self) -> None:
        scores = segment_boundary_scores([30, 10, 20], [20, 30, 10])

        assert scores.f1 == 1.0

    def test_iterables_other_than_lists_are_accepted(self) -> None:
        scores = segment_boundary_scores((cut for cut in [10, 20]), {20, 10})

        assert scores.f1 == 1.0
