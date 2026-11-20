"""评审级汇总：逐条判定 → ``LaneReview`` → ``Review``（纯计算，无 I/O）。

为什么单独一层：``rubric.settle`` 只回答"这一栏多少分"，而合同契约要求的是
"每栏一行摘要 + 一句话导航 + 全量逐条判定"。把这层放在 jury 里会让并发编排
和文案拼接纠缠在一起，也没法脱离事件循环单测。
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

from ..adjudication.contracts import CriteriaVerdict, LaneReview, Review
from .rubric import RubricItem, settle


def majority_passed(valid: int, yes: int) -> bool:
    """严格多数：``yes * 2 > valid``。

    平票（``yes * 2 == valid``）不算通过——多答裁决宁可不给结论，也不能把
    "一半一半"展示成"通过"。``valid == 0`` 同样为 ``False``，且调用方应据此
    把分数展示为 null。
    """
    return valid > 0 and yes * 2 > valid


def build_lane_review(lane: str, items: Sequence[RubricItem], verdicts: Sequence[CriteriaVerdict]) -> LaneReview:
    """把一栏的逐条判定结算成契约里的 ``LaneReview``。"""
    lane_verdicts = [verdict for verdict in verdicts if verdict.lane == lane]
    settled = settle(items, lane_verdicts)
    if settled.valid == 0:
        one_line = f"无有效判定（{settled.unscored} 条判不了）"
    else:
        one_line = f"{settled.valid} 条已判，{settled.yes} 条通过"
        if settled.unscored:
            one_line += f"，{settled.unscored} 条判不了"
    return LaneReview(
        lane=lane,
        valid=settled.valid,
        yes=settled.yes,
        # None = 一条有效票都没有；**不是 0 分**。
        score=settled.score,
        one_line=one_line[:40],
    )


def build_headline(lanes: Sequence[LaneReview]) -> str:
    """一句话导航（不是法律结论）。"""
    parts: list[str] = []
    for lane in lanes:
        if lane.valid == 0:
            parts.append(f"{lane.lane} 栏无有效判定")
        elif majority_passed(lane.valid, lane.yes):
            parts.append(f"{lane.lane} 栏多数通过")
        else:
            parts.append(f"{lane.lane} 栏多数未通过")
    return "；".join(parts)


def build_review(
    *,
    session_id: str,
    turn: int,
    items: Sequence[RubricItem],
    verdicts: Sequence[CriteriaVerdict],
    lanes: Sequence[str],
    tokens: Mapping[str, int],
    review_id: str | None = None,
) -> Review:
    """汇总成完整 ``Review``。

    ``stage`` 本批只有 ``shadow``：结果只展示，不触发任何自动动作。
    """
    lane_reviews = [build_lane_review(lane, items, verdicts) for lane in lanes]
    return Review(
        review_id=review_id or uuid.uuid4().hex,
        session_id=session_id,
        turn=turn,
        stage="shadow",
        lanes=lane_reviews,
        verdicts=list(verdicts),
        headline=build_headline(lane_reviews),
        unverified=[],
        tokens=dict(tokens),
    )
