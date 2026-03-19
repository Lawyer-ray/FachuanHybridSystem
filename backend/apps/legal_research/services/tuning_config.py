from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from apps.core.interfaces import ServiceLocator


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

    online_tuning_enabled: bool = True
    online_min_similarity_delta: float = 0.0
    adaptive_threshold_enabled: bool = True
    adaptive_threshold_floor: float = 0.76
    adaptive_threshold_step: float = 0.025
    adaptive_threshold_scan_interval: int = 30

    @classmethod
    def load(cls) -> LegalResearchTuningConfig:
        try:
            config_service = ServiceLocator.get_system_config_service()
        except Exception:
            return cls()

        return cls(
            recall_weight_keyword=cls._get_float(
                config_service, "LEGAL_RESEARCH_RECALL_WEIGHT_KEYWORD", 0.18, 0.0, 3.0
            ),
            recall_weight_summary=cls._get_float(
                config_service, "LEGAL_RESEARCH_RECALL_WEIGHT_SUMMARY", 0.22, 0.0, 3.0
            ),
            recall_weight_bm25=cls._get_float(config_service, "LEGAL_RESEARCH_RECALL_WEIGHT_BM25", 0.22, 0.0, 3.0),
            recall_weight_vector=cls._get_float(config_service, "LEGAL_RESEARCH_RECALL_WEIGHT_VECTOR", 0.18, 0.0, 3.0),
            recall_weight_passage=cls._get_float(
                config_service, "LEGAL_RESEARCH_RECALL_WEIGHT_PASSAGE", 0.16, 0.0, 3.0
            ),
            recall_weight_metadata=cls._get_float(
                config_service, "LEGAL_RESEARCH_RECALL_WEIGHT_METADATA", 0.04, 0.0, 3.0
            ),
            passage_top_k=cls._get_int(config_service, "LEGAL_RESEARCH_PASSAGE_TOP_K", 5, 1, 10),
            passage_max_chars=cls._get_int(config_service, "LEGAL_RESEARCH_PASSAGE_MAX_CHARS", 18000, 3000, 40000),
            passage_preview_max_chars=cls._get_int(
                config_service,
                "LEGAL_RESEARCH_PASSAGE_PREVIEW_MAX_CHARS",
                1600,
                400,
                6000,
            ),
            feedback_query_limit=cls._get_int(config_service, "LEGAL_RESEARCH_FEEDBACK_QUERY_LIMIT", 3, 0, 8),
            feedback_min_terms=cls._get_int(config_service, "LEGAL_RESEARCH_FEEDBACK_MIN_TERMS", 3, 1, 12),
            feedback_min_score_floor=cls._get_float(
                config_service,
                "LEGAL_RESEARCH_FEEDBACK_MIN_SCORE_FLOOR",
                0.62,
                0.0,
                1.0,
            ),
            feedback_score_margin=cls._get_float(
                config_service, "LEGAL_RESEARCH_FEEDBACK_SCORE_MARGIN", 0.22, 0.01, 0.6
            ),
            query_variant_enabled=cls._get_bool(config_service, "LEGAL_RESEARCH_QUERY_VARIANT_ENABLED", True),
            query_variant_max_count=cls._get_int(
                config_service,
                "LEGAL_RESEARCH_QUERY_VARIANT_MAX_COUNT",
                2,
                0,
                8,
            ),
            query_variant_model=cls._get_text(
                config_service,
                "LEGAL_RESEARCH_QUERY_VARIANT_MODEL",
                "",
                max_len=128,
            ),
            detail_cache_ttl_seconds=cls._get_int(
                config_service,
                "LEGAL_RESEARCH_DETAIL_CACHE_TTL_SECONDS",
                21600,
                60,
                604800,
            ),
            similarity_cache_ttl_seconds=cls._get_int(
                config_service,
                "LEGAL_RESEARCH_SIMILARITY_CACHE_TTL_SECONDS",
                86400,
                60,
                604800,
            ),
            similarity_local_cache_max_size=cls._get_int(
                config_service,
                "LEGAL_RESEARCH_SIMILARITY_LOCAL_CACHE_MAX_SIZE",
                1024,
                32,
                10000,
            ),
            semantic_vector_enabled=cls._get_bool(config_service, "LEGAL_RESEARCH_SEMANTIC_VECTOR_ENABLED", True),
            semantic_vector_model=cls._get_text(
                config_service,
                "LEGAL_RESEARCH_SEMANTIC_VECTOR_MODEL",
                "",
                max_len=128,
            ),
            semantic_vector_cache_ttl_seconds=cls._get_int(
                config_service,
                "LEGAL_RESEARCH_SEMANTIC_VECTOR_CACHE_TTL_SECONDS",
                86400,
                60,
                604800,
            ),
            semantic_vector_local_cache_max_size=cls._get_int(
                config_service,
                "LEGAL_RESEARCH_SEMANTIC_VECTOR_LOCAL_CACHE_MAX_SIZE",
                2048,
                64,
                20000,
            ),
            weike_session_restrict_cooldown_seconds=cls._get_int(
                config_service,
                "LEGAL_RESEARCH_WEIKE_SESSION_RESTRICT_COOLDOWN_SECONDS",
                180,
                30,
                1800,
            ),
            weike_search_api_degrade_streak_threshold=cls._get_int(
                config_service,
                "LEGAL_RESEARCH_WEIKE_SEARCH_API_DEGRADE_STREAK_THRESHOLD",
                2,
                1,
                10,
            ),
            weike_search_api_degrade_cooldown_seconds=cls._get_int(
                config_service,
                "LEGAL_RESEARCH_WEIKE_SEARCH_API_DEGRADE_COOLDOWN_SECONDS",
                180,
                30,
                3600,
            ),
            dual_review_enabled=cls._get_bool(config_service, "LEGAL_RESEARCH_DUAL_REVIEW_ENABLED", True),
            dual_review_model=cls._get_text(
                config_service,
                "LEGAL_RESEARCH_DUAL_REVIEW_MODEL",
                "Qwen/Qwen2.5-14B-Instruct",
                max_len=128,
            ),
            dual_review_primary_weight=cls._get_float(
                config_service,
                "LEGAL_RESEARCH_DUAL_REVIEW_PRIMARY_WEIGHT",
                0.62,
                0.0,
                1.0,
            ),
            dual_review_secondary_weight=cls._get_float(
                config_service,
                "LEGAL_RESEARCH_DUAL_REVIEW_SECONDARY_WEIGHT",
                0.38,
                0.0,
                1.0,
            ),
            dual_review_trigger_floor=cls._get_float(
                config_service,
                "LEGAL_RESEARCH_DUAL_REVIEW_TRIGGER_FLOOR",
                0.60,
                0.0,
                1.0,
            ),
            dual_review_gap_tolerance=cls._get_float(
                config_service,
                "LEGAL_RESEARCH_DUAL_REVIEW_GAP_TOLERANCE",
                0.18,
                0.01,
                0.6,
            ),
            dual_review_required_min=cls._get_float(
                config_service,
                "LEGAL_RESEARCH_DUAL_REVIEW_REQUIRED_MIN",
                0.55,
                0.0,
                1.0,
            ),
            online_tuning_enabled=cls._get_bool(config_service, "LEGAL_RESEARCH_ONLINE_TUNING_ENABLED", True),
            online_min_similarity_delta=cls._get_float(
                config_service,
                "LEGAL_RESEARCH_ONLINE_MIN_SIMILARITY_DELTA",
                0.0,
                -0.25,
                0.25,
            ),
            adaptive_threshold_enabled=cls._get_bool(
                config_service,
                "LEGAL_RESEARCH_ADAPTIVE_THRESHOLD_ENABLED",
                True,
            ),
            adaptive_threshold_floor=cls._get_float(
                config_service,
                "LEGAL_RESEARCH_ADAPTIVE_THRESHOLD_FLOOR",
                0.76,
                0.4,
                0.99,
            ),
            adaptive_threshold_step=cls._get_float(
                config_service,
                "LEGAL_RESEARCH_ADAPTIVE_THRESHOLD_STEP",
                0.025,
                0.005,
                0.2,
            ),
            adaptive_threshold_scan_interval=cls._get_int(
                config_service,
                "LEGAL_RESEARCH_ADAPTIVE_THRESHOLD_SCAN_INTERVAL",
                30,
                10,
                800,
            ),
        )

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
