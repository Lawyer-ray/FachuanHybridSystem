"""保全措施法律约束校验器."""

from __future__ import annotations

import logging
from typing import ClassVar

from django.utils.translation import gettext_lazy as _

from .models import PreservationMeasure

logger = logging.getLogger(__name__)


class MeasureValidator:
    """保全措施法律约束校验器.

    对提取的保全措施进行法律约束和逻辑一致性校验，
    仅追加 ``pending_note``，不修改其他字段。
    """

    # 法定期限上限（天数, 提示文案）
    DURATION_LIMITS: ClassVar[dict[str, tuple[int, str]]] = {
        "查封": (1095, str(_("不动产查封最长3年"))),
        "冻结": (365, str(_("银行存款冻结最长1年"))),
        "扣押": (730, str(_("动产扣押最长2年"))),
    }

    # ---- 校验提示文案 ----
    _MSG_DATE_INVERTED: str = str(_("到期日期早于起算日期，请人工核实"))
    _MSG_DURATION_EXCEEDED: str = str(_("期限超过法定上限（{limit_desc}），请人工核实"))
    _MSG_PENDING_HAS_END_DATE: str = str(_("轮候状态不应有确定到期日期，请人工核实"))

    # 多条提示之间的分隔符
    _SEP: str = "；"

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    def validate(self, measure: PreservationMeasure) -> PreservationMeasure:
        """校验单个措施，追加校验提示到 ``pending_note``，不修改原始数据."""
        warnings: list[str] = []

        self._check_date_order(measure, warnings)
        self._check_duration_limit(measure, warnings)
        self._check_pending_end_date(measure, warnings)

        if warnings:
            existing = measure.pending_note or ""
            suffix = self._SEP.join(warnings)
            measure.pending_note = f"{existing}{self._SEP}{suffix}" if existing else suffix

        return measure

    def validate_all(self, measures: list[PreservationMeasure]) -> list[PreservationMeasure]:
        """批量校验."""
        return [self.validate(m) for m in measures]

    # ------------------------------------------------------------------
    # private checks
    # ------------------------------------------------------------------

    def _check_date_order(
        self,
        measure: PreservationMeasure,
        warnings: list[str],
    ) -> None:
        """规则 1：end_date < start_date → 追加提示."""
        if measure.start_date is not None and measure.end_date is not None and measure.end_date < measure.start_date:
            warnings.append(self._MSG_DATE_INVERTED)

    def _check_duration_limit(
        self,
        measure: PreservationMeasure,
        warnings: list[str],
    ) -> None:
        """规则 2/3/4：期限超过法定上限 → 追加提示."""
        if measure.start_date is None or measure.end_date is None:
            return

        actual_days = (measure.end_date - measure.start_date).days

        for keyword, (max_days, limit_desc) in self.DURATION_LIMITS.items():
            if keyword in measure.measure_type and actual_days > max_days:
                warnings.append(self._MSG_DURATION_EXCEEDED.format(limit_desc=limit_desc))
                break  # 每个措施只匹配一种类型

    def _check_pending_end_date(
        self,
        measure: PreservationMeasure,
        warnings: list[str],
    ) -> None:
        """规则 5：is_pending=True 且 end_date 不为 None → 追加提示."""
        if measure.is_pending and measure.end_date is not None:
            warnings.append(self._MSG_PENDING_HAS_END_DATE)
