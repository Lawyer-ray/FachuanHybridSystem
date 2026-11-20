"""rubric 结算口径：正分进分母、负分只在分子扣、判不了不进 valid。

口径不是"看起来公平"，而是三条会直接影响多栏对比的硬约束：

1. 分母只装正分项——负分项若进分母，"什么都没做"会因未被扣分而得分虚高；
2. 分母保持全量正分，不因判不了而缩小——缩分母会让少数易判条目代表整份回答；
3. ``valid == 0`` 时分数是 ``None`` 而不是 0——"判不了"与"得了 0 分"必须分开。
"""

from __future__ import annotations

import pytest

from apps.agent.services.adjudication.contracts import CriteriaVerdict
from apps.agent.services.review.rubric import (
    DEFAULT_RUBRIC_ID,
    LaneScore,
    RubricItem,
    UnknownRubricError,
    aggregate_scores,
    length_adjusted_score,
    load_rubric,
    settle,
)


def _verdict(rubric_id: str, met: bool | None, lane: str = "pi") -> CriteriaVerdict:
    return CriteriaVerdict(rubric_id=rubric_id, lane=lane, criteria_met=met)


def _items() -> list[RubricItem]:
    return [
        RubricItem(id="positive_a", criterion="加分项 A", points=2),
        RubricItem(id="positive_b", criterion="加分项 B", points=2),
        RubricItem(id="negative", criterion="不该发生的事", points=-1),
    ]


class TestLoadRubric:
    def test_default_rubric_has_three_polarities_and_no_zero_points(self) -> None:
        items = load_rubric(DEFAULT_RUBRIC_ID)

        assert len(items) == 7
        assert any(item.points > 0 for item in items)
        assert any(item.points < 0 for item in items)
        assert all(item.points != 0 for item in items)
        assert {tag for item in items for tag in item.tags} == {"miss", "over", "cite"}

    def test_returns_copy(self) -> None:
        first = load_rubric(DEFAULT_RUBRIC_ID)
        first.pop()

        assert len(load_rubric(DEFAULT_RUBRIC_ID)) == 7

    def test_unknown_rubric_raises(self) -> None:
        with pytest.raises(UnknownRubricError):
            load_rubric("no-such-rubric")


class TestSettle:
    def test_positive_points_enter_denominator_negative_only_numerator(self) -> None:
        # a 满足(+2)、b 不满足(0)、负分项发生(-1) → 1/4，而不是 (2-1)/(2+2-1)。
        result = settle(
            _items(), [_verdict("positive_a", True), _verdict("positive_b", False), _verdict("negative", True)]
        )

        assert isinstance(result, LaneScore)
        assert result.total_positive == 4
        assert result.achieved == 1
        assert result.score == pytest.approx(0.25)
        assert result.valid == 3

    def test_negative_item_not_happening_does_not_add_points(self) -> None:
        result = settle(_items(), [_verdict("positive_a", True), _verdict("negative", False)])

        assert result.achieved == 2
        assert result.score == pytest.approx(0.5)

    def test_unscored_does_not_enter_valid_and_denominator_stays_full(self) -> None:
        result = settle(
            _items(), [_verdict("positive_a", None), _verdict("positive_b", True), _verdict("negative", None)]
        )

        assert result.valid == 1
        assert result.unscored == 2
        # 分母仍是 4（全量正分），不是只看已判的正分项 2。
        assert result.score == pytest.approx(0.5)

    def test_all_unscored_returns_none_not_zero(self) -> None:
        result = settle(_items(), [_verdict("positive_a", None), _verdict("positive_b", None)])

        assert result.valid == 0
        assert result.score is None

    def test_missing_verdict_counts_as_unscored(self) -> None:
        result = settle(_items(), [_verdict("positive_a", True)])

        assert result.valid == 1
        assert result.unscored == 2

    def test_matches_by_rubric_id_not_position(self) -> None:
        # 顺序打乱：票仍然落回各自的条目，不会把 positive_a 的 true 记给 negative。
        result = settle(_items(), [_verdict("negative", False), _verdict("positive_a", True)])

        assert result.achieved == 2
        assert result.yes == 2  # positive_a 满足 + negative 未发生
        assert result.score == pytest.approx(0.5)

    def test_yes_counts_favorable_votes_not_raw_met(self) -> None:
        # 负分项"发生"= 对回答不利，不能计入 yes，否则多数门槛会被算反。
        result = settle(_items(), [_verdict("positive_a", False), _verdict("negative", True)])

        assert result.valid == 2
        assert result.yes == 0

    def test_single_lane_score_may_be_negative(self) -> None:
        items = [
            RubricItem(id="positive", criterion="加分", points=1),
            RubricItem(id="negative", criterion="扣分", points=-2),
        ]
        result = settle(items, [_verdict("positive", False), _verdict("negative", True)])

        assert result.score == pytest.approx(-2.0)

    def test_no_positive_items_returns_none(self) -> None:
        items = [RubricItem(id="negative", criterion="扣分", points=-1)]
        result = settle(items, [_verdict("negative", False)])

        assert result.total_positive == 0
        assert result.score is None


class TestLengthAdjustment:
    def test_formula(self) -> None:
        adjusted = length_adjusted_score(1.0, "x" * 1500, center=500, penalty_per_500_chars=0.1)

        assert adjusted == pytest.approx(0.8)

    def test_null_score_stays_null(self) -> None:
        assert length_adjusted_score(None, "answer", center=500, penalty_per_500_chars=0.1) is None

    def test_does_not_clip(self) -> None:
        adjusted = length_adjusted_score(1.2, "x" * 1000, center=0, penalty_per_500_chars=0.0)

        assert adjusted == pytest.approx(1.2)

    @pytest.mark.parametrize(("center", "penalty"), [(-1, 0.1), (500, -0.1)])
    def test_rejects_negative_parameters(self, center: int, penalty: float) -> None:
        with pytest.raises(ValueError):
            length_adjusted_score(1.0, "answer", center=center, penalty_per_500_chars=penalty)


class TestAggregate:
    def test_mean_of_non_none_then_clip(self) -> None:
        assert aggregate_scores([1.4, 0.2, None, -0.5]) == pytest.approx((1.4 + 0.2 - 0.5) / 3)

    def test_clips_to_unit_interval(self) -> None:
        assert aggregate_scores([1.4, 1.4]) == 1.0
        assert aggregate_scores([-2.0, -1.0]) == 0.0

    def test_empty_is_none(self) -> None:
        assert aggregate_scores([]) is None
        assert aggregate_scores([None, None]) is None
