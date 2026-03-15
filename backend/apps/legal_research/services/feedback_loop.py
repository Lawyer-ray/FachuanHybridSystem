from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from django.utils import timezone

from apps.core.interfaces import ServiceLocator
from apps.legal_research.models import LegalResearchResult, LegalResearchTask
from apps.legal_research.services.tuning_config import LegalResearchTuningConfig

logger = logging.getLogger(__name__)


class _WritableConfigService(Protocol):
    def get_value(self, key: str, default: str = "") -> str: ...

    def set_value(
        self,
        key: str,
        value: str,
        category: str = "general",
        description: str = "",
        is_secret: bool = False,
    ) -> object: ...


class LegalResearchFeedbackType:
    HIT_TRUE = "hit_true"
    HIT_FALSE = "hit_false"
    MISSED_CASE = "missed_case"


@dataclass(frozen=True)
class _FloatTuningKey:
    key: str
    default: float
    min_value: float
    max_value: float
    description: str


class LegalResearchFeedbackLoopService:
    CATEGORY = "ai"

    KEY_ONLINE_ENABLED = "LEGAL_RESEARCH_ONLINE_TUNING_ENABLED"
    KEY_MIN_SIMILARITY_DELTA = _FloatTuningKey(
        key="LEGAL_RESEARCH_ONLINE_MIN_SIMILARITY_DELTA",
        default=0.0,
        min_value=-0.25,
        max_value=0.25,
        description="案例检索在线微调：执行阈值增量",
    )
    KEY_FEEDBACK_MARGIN = _FloatTuningKey(
        key="LEGAL_RESEARCH_FEEDBACK_SCORE_MARGIN",
        default=0.22,
        min_value=0.01,
        max_value=0.6,
        description="案例检索伪相关反馈：阈值回退边际",
    )
    KEY_FEEDBACK_FLOOR = _FloatTuningKey(
        key="LEGAL_RESEARCH_FEEDBACK_MIN_SCORE_FLOOR",
        default=0.62,
        min_value=0.0,
        max_value=1.0,
        description="案例检索伪相关反馈：最低分数下限",
    )

    KEY_WEIGHT_KEYWORD = _FloatTuningKey(
        key="LEGAL_RESEARCH_RECALL_WEIGHT_KEYWORD",
        default=0.18,
        min_value=0.0,
        max_value=3.0,
        description="案例检索宽召回权重：关键词重合",
    )
    KEY_WEIGHT_SUMMARY = _FloatTuningKey(
        key="LEGAL_RESEARCH_RECALL_WEIGHT_SUMMARY",
        default=0.22,
        min_value=0.0,
        max_value=3.0,
        description="案例检索宽召回权重：案情摘要重合",
    )
    KEY_WEIGHT_BM25 = _FloatTuningKey(
        key="LEGAL_RESEARCH_RECALL_WEIGHT_BM25",
        default=0.22,
        min_value=0.0,
        max_value=3.0,
        description="案例检索宽召回权重：BM25代理分",
    )
    KEY_WEIGHT_VECTOR = _FloatTuningKey(
        key="LEGAL_RESEARCH_RECALL_WEIGHT_VECTOR",
        default=0.18,
        min_value=0.0,
        max_value=3.0,
        description="案例检索宽召回权重：向量相似分",
    )
    KEY_WEIGHT_PASSAGE = _FloatTuningKey(
        key="LEGAL_RESEARCH_RECALL_WEIGHT_PASSAGE",
        default=0.16,
        min_value=0.0,
        max_value=3.0,
        description="案例检索宽召回权重：段落对齐分",
    )
    KEY_WEIGHT_METADATA = _FloatTuningKey(
        key="LEGAL_RESEARCH_RECALL_WEIGHT_METADATA",
        default=0.04,
        min_value=0.0,
        max_value=3.0,
        description="案例检索宽召回权重：元信息提示分",
    )

    KEY_COUNTER_POSITIVE = "LEGAL_RESEARCH_FEEDBACK_POSITIVE_COUNT"
    KEY_COUNTER_NEGATIVE = "LEGAL_RESEARCH_FEEDBACK_NEGATIVE_COUNT"
    KEY_COUNTER_MISSED = "LEGAL_RESEARCH_FEEDBACK_MISSED_COUNT"

    def __init__(self, *, config_service: _WritableConfigService | None = None) -> None:
        self._config = config_service or ServiceLocator.get_system_config_service()
        self._defaults = LegalResearchTuningConfig()

    def record_result_feedback(
        self,
        *,
        result: LegalResearchResult,
        is_relevant: bool,
        operator: str = "",
    ) -> None:
        label = "relevant" if is_relevant else "false_positive"
        metadata = dict(result.metadata or {})
        metadata["human_feedback"] = label
        metadata["feedback_at"] = timezone.now().isoformat()
        if operator:
            metadata["feedback_by"] = operator
        result.metadata = metadata
        result.save(update_fields=["metadata", "updated_at"])

        feedback_type = LegalResearchFeedbackType.HIT_TRUE if is_relevant else LegalResearchFeedbackType.HIT_FALSE
        self.apply_feedback(feedback_type=feedback_type)

    def record_task_missed_feedback(self, *, task: LegalResearchTask, operator: str = "", note: str = "") -> None:
        self.apply_feedback(feedback_type=LegalResearchFeedbackType.MISSED_CASE)
        suffix = "已记录漏命中反馈，并自动微调检索参数"
        if operator:
            suffix += f"（操作人:{operator}）"
        if note:
            suffix += f" {note[:80]}"
        task.message = suffix[:250]
        task.save(update_fields=["message", "updated_at"])

    def apply_feedback(self, *, feedback_type: str) -> None:
        if not self._get_bool(self.KEY_ONLINE_ENABLED, default=True):
            return

        if feedback_type == LegalResearchFeedbackType.HIT_FALSE:
            self._increment_counter(self.KEY_COUNTER_NEGATIVE)
            self._adjust_thresholds(min_similarity_delta=+0.015, margin_delta=-0.01, floor_delta=+0.005)
            self._adjust_weights(
                keyword_delta=-0.012,
                summary_delta=+0.003,
                bm25_delta=-0.003,
                vector_delta=+0.007,
                passage_delta=+0.01,
                metadata_delta=-0.005,
            )
            return

        if feedback_type == LegalResearchFeedbackType.MISSED_CASE:
            self._increment_counter(self.KEY_COUNTER_MISSED)
            self._adjust_thresholds(min_similarity_delta=-0.015, margin_delta=+0.01, floor_delta=-0.005)
            self._adjust_weights(
                keyword_delta=+0.004,
                summary_delta=+0.008,
                bm25_delta=+0.01,
                vector_delta=-0.004,
                passage_delta=-0.008,
                metadata_delta=0.0,
            )
            return

        if feedback_type == LegalResearchFeedbackType.HIT_TRUE:
            self._increment_counter(self.KEY_COUNTER_POSITIVE)
            self._relax_towards_defaults()
            return

        logger.warning("未知反馈类型，忽略在线微调", extra={"feedback_type": feedback_type})

    def _relax_towards_defaults(self) -> None:
        self._decay_to_target(self.KEY_MIN_SIMILARITY_DELTA, target=0.0, rate=0.10)
        self._decay_to_target(self.KEY_FEEDBACK_MARGIN, target=self._defaults.feedback_score_margin, rate=0.08)
        self._decay_to_target(self.KEY_FEEDBACK_FLOOR, target=self._defaults.feedback_min_score_floor, rate=0.08)

        self._decay_to_target(self.KEY_WEIGHT_KEYWORD, target=self._defaults.recall_weight_keyword, rate=0.08)
        self._decay_to_target(self.KEY_WEIGHT_SUMMARY, target=self._defaults.recall_weight_summary, rate=0.08)
        self._decay_to_target(self.KEY_WEIGHT_BM25, target=self._defaults.recall_weight_bm25, rate=0.08)
        self._decay_to_target(self.KEY_WEIGHT_VECTOR, target=self._defaults.recall_weight_vector, rate=0.08)
        self._decay_to_target(self.KEY_WEIGHT_PASSAGE, target=self._defaults.recall_weight_passage, rate=0.08)
        self._decay_to_target(self.KEY_WEIGHT_METADATA, target=self._defaults.recall_weight_metadata, rate=0.08)

    def _adjust_thresholds(self, *, min_similarity_delta: float, margin_delta: float, floor_delta: float) -> None:
        self._bump_value(self.KEY_MIN_SIMILARITY_DELTA, min_similarity_delta)
        self._bump_value(self.KEY_FEEDBACK_MARGIN, margin_delta)
        self._bump_value(self.KEY_FEEDBACK_FLOOR, floor_delta)

    def _adjust_weights(
        self,
        *,
        keyword_delta: float,
        summary_delta: float,
        bm25_delta: float,
        vector_delta: float,
        passage_delta: float,
        metadata_delta: float,
    ) -> None:
        self._bump_value(self.KEY_WEIGHT_KEYWORD, keyword_delta)
        self._bump_value(self.KEY_WEIGHT_SUMMARY, summary_delta)
        self._bump_value(self.KEY_WEIGHT_BM25, bm25_delta)
        self._bump_value(self.KEY_WEIGHT_VECTOR, vector_delta)
        self._bump_value(self.KEY_WEIGHT_PASSAGE, passage_delta)
        self._bump_value(self.KEY_WEIGHT_METADATA, metadata_delta)

    def _decay_to_target(self, tuning_key: _FloatTuningKey, *, target: float, rate: float) -> None:
        current = self._get_float(tuning_key)
        moved = current + (target - current) * max(0.0, min(1.0, rate))
        self._set_float(tuning_key, moved)

    def _bump_value(self, tuning_key: _FloatTuningKey, delta: float) -> None:
        current = self._get_float(tuning_key)
        self._set_float(tuning_key, current + delta)

    def _get_float(self, tuning_key: _FloatTuningKey) -> float:
        raw = str(self._config.get_value(tuning_key.key, str(tuning_key.default)) or "").strip()
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = tuning_key.default
        return max(tuning_key.min_value, min(tuning_key.max_value, value))

    def _set_float(self, tuning_key: _FloatTuningKey, value: float) -> None:
        clamped = max(tuning_key.min_value, min(tuning_key.max_value, value))
        self._config.set_value(
            tuning_key.key,
            f"{clamped:.4f}",
            category=self.CATEGORY,
            description=tuning_key.description,
            is_secret=False,
        )

    def _get_bool(self, key: str, *, default: bool) -> bool:
        raw = str(self._config.get_value(key, "True" if default else "False") or "").strip().lower()
        if raw in {"1", "true", "yes", "on", "y"}:
            return True
        if raw in {"0", "false", "no", "off", "n"}:
            return False
        return default

    def _increment_counter(self, key: str) -> None:
        raw = str(self._config.get_value(key, "0") or "").strip()
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 0
        self._config.set_value(
            key,
            str(max(0, value + 1)),
            category=self.CATEGORY,
            description="案例检索在线反馈计数",
            is_secret=False,
        )
