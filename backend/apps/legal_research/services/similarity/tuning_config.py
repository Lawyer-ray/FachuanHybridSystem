from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class _ConfigGetter(Protocol):
    def get_value(self, key: str, default: str = "") -> str: ...


@dataclass(frozen=True)
class LegalResearchTuningConfig:
    recall_weight_keyword: float = 0.18
    recall_weight_summary: float = 0.22
    recall_weight_bm25: float = 0.22
    recall_weight_vector: float = 0.18
    recall_weight_passage: float = 0.16
    recall_weight_metadata: float = 0.04

    passage_top_k: int = 5
    passage_max_chars: int = 18000
    passage_preview_max_chars: int = 1600

    feedback_query_limit: int = 3
    feedback_min_terms: int = 3
    feedback_min_score_floor: float = 0.62
    feedback_score_margin: float = 0.22

    query_variant_enabled: bool = True
    query_variant_max_count: int = 2
    query_variant_model: str = ""

    detail_cache_ttl_seconds: int = 21600
    similarity_cache_ttl_seconds: int = 86400
    similarity_local_cache_max_size: int = 1024

    semantic_vector_enabled: bool = True
    semantic_vector_model: str = ""
    semantic_vector_cache_ttl_seconds: int = 86400
    semantic_vector_local_cache_max_size: int = 2048

    weike_session_restrict_cooldown_seconds: int = 180
    weike_search_api_degrade_streak_threshold: int = 2
    weike_search_api_degrade_cooldown_seconds: int = 180

    dual_review_enabled: bool = True
    dual_review_model: str = "Qwen/Qwen2.5-14B-Instruct"
    dual_review_primary_weight: float = 0.62
    dual_review_secondary_weight: float = 0.38
    dual_review_trigger_floor: float = 0.60
    dual_review_gap_tolerance: float = 0.18
    dual_review_required_min: float = 0.55

    # ── 速度与准确率优化 V26.28 ──
    title_prefilter_enabled: bool = True
    title_prefilter_min_overlap: float = 0.15
    coarse_recall_hard_floor: float = 0.20
    llm_scoring_concurrency: int = 5
    element_extraction_enabled: bool = True
    element_extraction_model: str = ""
    element_extraction_timeout_seconds: int = 20

    online_tuning_enabled: bool = True
    online_min_similarity_delta: float = 0.0
    adaptive_threshold_enabled: bool = True
    adaptive_threshold_floor: float = 0.76
    adaptive_threshold_step: float = 0.025
    adaptive_threshold_scan_interval: int = 30

    @classmethod
    def load(cls) -> LegalResearchTuningConfig:
        return cls()

    @property
    def normalized_recall_weights(self) -> tuple[float, float, float, float, float, float]:
        raw = [
            max(0.0, self.recall_weight_keyword),
            max(0.0, self.recall_weight_summary),
            max(0.0, self.recall_weight_bm25),
            max(0.0, self.recall_weight_vector),
            max(0.0, self.recall_weight_passage),
            max(0.0, self.recall_weight_metadata),
        ]
        total = sum(raw)
        if total <= 0:
            defaults = [0.18, 0.22, 0.22, 0.18, 0.16, 0.04]
            total = sum(defaults)
            return tuple(v / total for v in defaults)  # type: ignore[return-value]
        return tuple(v / total for v in raw)  # type: ignore[return-value]

    @staticmethod
    def _get_int(config_service: _ConfigGetter, key: str, default: int, min_value: int, max_value: int) -> int:
        raw = str(config_service.get_value(key, str(default)) or "").strip()
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        return max(min_value, min(max_value, value))

    @staticmethod
    def _get_float(
        config_service: _ConfigGetter, key: str, default: float, min_value: float, max_value: float
    ) -> float:
        raw = str(config_service.get_value(key, str(default)) or "").strip()
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return default
        return max(min_value, min(max_value, value))

    @staticmethod
    def _get_bool(config_service: _ConfigGetter, key: str, default: bool) -> bool:
        raw = str(config_service.get_value(key, "True" if default else "False") or "").strip().lower()
        if raw in {"1", "true", "yes", "on", "y"}:
            return True
        if raw in {"0", "false", "no", "off", "n"}:
            return False
        return default

    @staticmethod
    def _get_text(config_service: _ConfigGetter, key: str, default: str, *, max_len: int) -> str:
        value = str(config_service.get_value(key, default) or "").strip()
        if not value:
            return default
        return value[:max_len]
