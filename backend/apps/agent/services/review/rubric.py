"""rubric 定义与结算口径。

## 结算公式（口径来源：HealthBench ``calculate_score``）

```
denom = Σ points_i            （仅 points_i > 0）
num   = Σ points_i * met_i    （met∈{1,0}，只在已判定的条目上累加）
score = num / denom           （valid == 0 或 denom == 0 时为 None）
```

两处刻意的选择：

1. **负分不进分母，只在分子扣**。负分项描述"不该发生的事"：发生了就扣分，
   不发生也不该给回答加分——把它放进分母会让"什么都没做"的回答得分虚高。
2. **分母保持全量正分，不因判不了而缩小**。缩分母等于用"少数容易判的条目"
   代表整份回答，会系统性抬高分数；判不了时保留完整分母得到的是保守下界，
   配合 ``LaneScore.unscored`` / ``valid`` 一起展示，而不是假装判过。

这里的 ``total_positive`` 是**分数公式**的分母。jury 多数门槛用的是
``LaneScore.valid``（true+false 的条数）——失败票同样不进那个分母。两者
名字都叫"分母"，但不是同一个量，改任何一边都要先看清是哪一边。

``score`` 允许为负（某条负分项被判定发生）；**裁剪只发生在聚合层**
（``aggregate_scores``），单栏分数保留真实值，否则跨栏比较会失真。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from ..adjudication.contracts import CriteriaVerdict

#: 内置 rubric 的稳定 id（库表单还没进本批范围，先只提供内置表）。
DEFAULT_RUBRIC_ID = "contract_answer_v1"


@dataclass(frozen=True)
class RubricItem:
    """一条判定标准。

    ``points`` 的正负承载极性：正=加分项，负=扣分项。**显式禁止 0**——0 分项
    既不在分子也不在分母，只会让"这一条到底算什么"变成歧义。
    """

    id: str
    criterion: str
    points: float
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("RubricItem.id 不能为空")
        if not self.criterion.strip():
            raise ValueError(f"RubricItem({self.id}) 的 criterion 不能为空")
        if self.points == 0:
            raise ValueError(f"RubricItem({self.id}) 的 points 不能为 0")


class UnknownRubricError(LookupError):
    """请求的 rubric 不在内置表里。"""


#: 合同问答的首版内置 rubric：3 条"必须改" + 2 条"不得越界" + 2 条"引注"。
#: 口径见 ``docs/analysis/adjudication-2026-11-20/07-calibration.md`` 的 7 条/份。
_BUILTIN_RUBRICS: dict[str, tuple[RubricItem, ...]] = {
    DEFAULT_RUBRIC_ID: (
        RubricItem(
            id="miss_risk_identified",
            criterion="回答是否指出合同中必须修改的具体风险点，而不是只给泛泛的审查建议。",
            points=2,
            tags=("miss",),
        ),
        RubricItem(
            id="miss_clause_located",
            criterion="回答是否定位到具体条款号或引用原文片段，使律师能直接找到该风险点。",
            points=2,
            tags=("miss",),
        ),
        RubricItem(
            id="miss_consequence",
            criterion="回答是否说明不修改该风险点可能导致的法律后果或商业风险。",
            points=2,
            tags=("miss",),
        ),
        RubricItem(
            id="over_scope",
            criterion="回答是否改写了未被要求修改的条款，或引入了与本次审查无关的改动。",
            points=-1,
            tags=("over",),
        ),
        RubricItem(
            id="over_absolute",
            criterion="回答是否把不确定的法律判断说成绝对结论，或对案件结果作出承诺。",
            points=-2,
            tags=("over",),
        ),
        RubricItem(
            id="cite_authority",
            criterion="回答是否引用具体法律、司法解释条文或案号，并标明出处。",
            points=2,
            tags=("cite",),
        ),
        RubricItem(
            id="cite_verifiable",
            criterion="回答所引法条、案号是否能与给定材料或可核验的公开法源对应，而不是编造。",
            points=2,
            tags=("cite",),
        ),
    ),
}


def load_rubric(rubric_id: str) -> list[RubricItem]:
    """按 id 取内置 rubric（返回副本，调用方无法改到内置表）。"""
    try:
        return list(_BUILTIN_RUBRICS[rubric_id])
    except KeyError as exc:
        raise UnknownRubricError(rubric_id) from exc


def available_rubric_ids() -> list[str]:
    """内置 rubric 的 id 清单（``GET /agent/review/options`` 用）。

    排序返回：前端按它渲染下拉，顺序必须稳定——字典插入顺序会在新增一条 rubric
    之后默默改变下拉项的位置。
    """
    return sorted(_BUILTIN_RUBRICS)


@dataclass(frozen=True)
class LaneScore:
    """一栏的结算结果。

    ``yes`` 是**对回答有利**的票数：正分项判定满足，或负分项判定未发生。
    它不等于 ``criteria_met is True`` 的条数——负分项里"满足"是坏事，
    直接拿去和 ``valid`` 比大小会把多数门槛算反。
    """

    score: float | None
    achieved: float
    total_positive: float
    valid: int
    yes: int
    unscored: int


def settle(items: Sequence[RubricItem], verdicts: Sequence[CriteriaVerdict]) -> LaneScore:
    """按 rubric 条目结算一栏的分数。

    按 ``rubric_id`` 回填而不是按位置 ``zip``：判定是并发产生的，完成顺序
    与 rubric 顺序无关，按位置配对会把 A 条的票记到 B 条上。
    """
    by_id: dict[str, CriteriaVerdict] = {}
    for verdict in verdicts:
        by_id.setdefault(verdict.rubric_id, verdict)

    total_positive = sum(item.points for item in items if item.points > 0)
    achieved = 0.0
    valid = 0
    yes = 0
    unscored = 0

    for item in items:
        verdict = by_id.get(item.id)
        if verdict is None or verdict.criteria_met is None:
            # 判不了 / 没判：不进 valid，也不在分子里假装答错。
            unscored += 1
            continue
        valid += 1
        if verdict.criteria_met:
            achieved += item.points
        # 正分项"满足"与负分项"未发生"都是对回答有利的一票。
        if verdict.criteria_met == (item.points > 0):
            yes += 1

    score = achieved / total_positive if valid > 0 and total_positive > 0 else None
    return LaneScore(
        score=score,
        achieved=achieved,
        total_positive=total_positive,
        valid=valid,
        yes=yes,
        unscored=unscored,
    )


def length_adjusted_score(
    score: float | None,
    answer: str,
    *,
    center: int,
    penalty_per_500_chars: float,
) -> float | None:
    """长度调整分数（并列指标，不替换主分）。

    ``center`` 与 ``penalty_per_500_chars`` 必须成对且非负；默认不启用
    （由调用方显式传参）。结果**不裁剪**——裁剪只在聚合层做。
    """
    if center < 0:
        raise ValueError("center 不能为负")
    if penalty_per_500_chars < 0:
        raise ValueError("penalty_per_500_chars 不能为负")
    if score is None:
        return None
    return score - penalty_per_500_chars * ((len(answer) - center) / 500)


def aggregate_scores(scores: Iterable[float | None]) -> float | None:
    """跨响应/跨栏聚合：对非 None 取均值，再裁剪到 ``[0, 1]``。

    空集返回 ``None``（没有可聚合的分数），不返回 0——0 是"确实得了 0 分"，
    两者在展示层必须能分开。
    """
    usable = [score for score in scores if score is not None]
    if not usable:
        return None
    return max(0.0, min(1.0, sum(usable) / len(usable)))
