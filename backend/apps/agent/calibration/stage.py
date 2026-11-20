"""Stage 0/1/2 门禁：把校准指标翻译成"这套判定能不能放开权限"。

门槛取自 ``docs/analysis/adjudication-2026-11-20/07-calibration.md`` F.3 的 Stage 2 行：
``kappa >= 0.75``、``miss_recall >= 0.90``、``cite_recall >= 0.90``、至少 2 个 judge 家族同向、
``margin`` 越过 tie band。任一不满足退 Stage 1；``kappa`` 不达标一律 Stage 0（本批口径）。

**本批只做这四项门禁**。同一张表里的 ``raw >= 0.92``、``position_consistency >= 0.95``、
``over_false_accept <= 0.10``、单条 rubric 分歧率 <= 15%、人-人一致率上限，都不在本函数里：
没有真实数据时把它们一起写死，等于凭空断言这些口径成立。它们随报告一起补。

## 档位语义（沿用 F.3 的档位名）

* Stage 0：只记录、不展示——连影子门禁都没过；
* Stage 1：影子 / 辅助展示——对应契约 ``Review.stage="shadow"``，只展示不参与任何自动动作；
* Stage 2：可参与自动排序与合并——律师仍可覆盖。

## 边界处理的三条硬规则

1. **无法度量（``None`` / NaN）按最保守处理**。``kappa`` 测不出来 → Stage 0：连"能不能用"
   都判不了，就不许说它能用。NaN 更危险，它在任何比较下都是 ``False``，若只写
   ``if kappa >= FLOOR`` 这种正向条件，NaN 会一路滑到 Stage 1 而没人发现。
2. **阈值含端点，margin 不含**：``kappa == 0.75`` 算达标（"至少 0.75"），
   ``margin == TIE_BAND`` **不算**越过（"严格越过"）。
3. **绝不用 ``==`` 判浮点**。比较一律写成"差够容差"，容差 ``1e-12`` 远小于任何有意义的
   精度差异，只用来吃掉 ``0.7499999999999999`` 这类二进制表示误差。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Stage 2 要求的最小 kappa（F.3 表）。低于它一律 Stage 0。
KAPPA_FLOOR = 0.75
#: Stage 2 要求的两类最小 recall（漏改、引用失效）。
RECALL_FLOOR = 0.90
#: Stage 2 要求的最小同向 judge 家族数：单家族给的结论不算数。
MIN_FAMILIES = 2
#: 平局带。取值沿用 FastChat 的 ``TIE_DELTA = 0.1``（见 07-calibration.md A.4）：
#: margin 落在带内就输出 tie 并转人工，不许用浮点小数决出胜负。
TIE_BAND = 0.10

#: 档位 → 一句话权限说明（报告直接引用）。
STAGE_LABELS: dict[int, str] = {
    0: "Stage 0 · 只记录不展示（门禁未过，需重做 rubric 或补样本）",
    1: "Stage 1 · 影子 / 辅助展示（标注 AI 建议，不参与任何自动动作）",
    2: "Stage 2 · 可参与自动排序与合并（律师仍可覆盖）",
}

#: 判定项的两类数值口径，只影响报告里的显示格式。
RATIO_UNIT = "ratio"
COUNT_UNIT = "count"

#: 阈值比较容差，见模块 docstring 第 3 条。
_THRESHOLD_EPS = 1e-12


@dataclass(frozen=True)
class StageCheck:
    """一项门禁的实测值与判定结果。``met is None`` = 该项无法度量。"""

    #: 参数名（kappa / miss_recall / ...），报告据此映射中文名。
    criterion: str
    #: 判定的方向说明（"至少" / "严格越过"），避免报告自行猜测运算符。
    rule: str
    unit: str
    actual: float | None
    threshold: float
    met: bool | None

    @property
    def gap(self) -> float | None:
        """距门槛还差多少（门槛 − 实测）。实测缺失时是 ``None``；已达标时可能 ≤ 0。"""
        if self.actual is None:
            return None
        return self.threshold - self.actual


@dataclass(frozen=True)
class StageDecision:
    """一次门禁判定的结果。"""

    stage: int
    checks: tuple[StageCheck, ...]

    @property
    def unmet(self) -> tuple[StageCheck, ...]:
        """未达标 / 无法度量的门禁项（报告"未达标差距"节的唯一数据源）。"""
        return tuple(check for check in self.checks if check.met is not True)


def decide_stage(
    kappa: float | None,
    miss_recall: float | None,
    cite_recall: float | None,
    families_agreeing: int | None,
    margin: float | None,
) -> StageDecision:
    """判定档位。

    参数为 ``None`` 表示该指标没测出来（空样本、子类无标注、判定侧没记录），
    与"测出来是 0"严格区分：前者按最保守处理，后者是真实的低分。
    """
    checks = (
        _at_least("kappa", RATIO_UNIT, kappa, KAPPA_FLOOR),
        _at_least("miss_recall", RATIO_UNIT, miss_recall, RECALL_FLOOR),
        _at_least("cite_recall", RATIO_UNIT, cite_recall, RECALL_FLOOR),
        _at_least("families_agreeing", COUNT_UNIT, families_agreeing, MIN_FAMILIES),
        _beyond("margin", RATIO_UNIT, margin, TIE_BAND),
    )
    kappa_met = checks[0].met is True
    if not kappa_met:
        # kappa 不达标或无法度量：不看其余项，直接 Stage 0（本批口径："一律"）。
        return StageDecision(stage=0, checks=checks)
    if all(check.met is True for check in checks):
        return StageDecision(stage=2, checks=checks)
    return StageDecision(stage=1, checks=checks)


def _at_least(criterion: str, unit: str, actual: float | int | None, threshold: float) -> StageCheck:
    """``actual >= threshold``（含端点），容差内视作达标。"""
    value = _finite_or_none(actual)
    if value is None:
        return StageCheck(criterion, "至少", unit, None, threshold, None)
    return StageCheck(criterion, "至少", unit, value, threshold, value >= threshold - _THRESHOLD_EPS)


def _beyond(criterion: str, unit: str, actual: float | None, threshold: float) -> StageCheck:
    """``actual > threshold``（严格），必须真的越过平局带。"""
    value = _finite_or_none(actual)
    if value is None:
        return StageCheck(criterion, "严格越过", unit, None, threshold, None)
    return StageCheck(criterion, "严格越过", unit, value, threshold, value > threshold + _THRESHOLD_EPS)


def _finite_or_none(value: float | int | None) -> float | None:
    """把 ``None`` / NaN / inf 统一成 ``None``（"无法度量"的唯一表示）。"""
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None
