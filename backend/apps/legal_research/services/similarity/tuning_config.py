from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


class _ConfigGetter(Protocol):
    def get_value(self, key: str, default: str = "") -> str: ...


def _get_config_service() -> _ConfigGetter | None:
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_system_config_service()


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

    # ── 语义向量常开模式 ──
    semantic_vector_always_on: bool = False

    # ── 交叉编码器重排序 ──
    reranker_enabled: bool = False
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_top_k: int = 10
    reranker_score_weight: float = 0.4
    reranker_api_base_url: str = "https://api.siliconflow.cn/v1"

    @classmethod
    def load(cls) -> LegalResearchTuningConfig:
        try:
            config_service = _get_config_service()
        except Exception:
            return cls()
        if config_service is None:
            return cls()
        return cls(
            semantic_vector_always_on=cls._get_bool(
                config_service, "LEGAL_RESEARCH_SEMANTIC_VECTOR_ALWAYS_ON", cls.semantic_vector_always_on
            ),
            reranker_enabled=cls._get_bool(config_service, "LEGAL_RESEARCH_RERANKER_ENABLED", cls.reranker_enabled),
            reranker_model=cls._get_text(
                config_service, "LEGAL_RESEARCH_RERANKER_MODEL", cls.reranker_model, max_len=128
            ),
            reranker_top_k=cls._get_int(config_service, "LEGAL_RESEARCH_RERANKER_TOP_K", cls.reranker_top_k, 1, 50),
            reranker_score_weight=cls._get_float(
                config_service, "LEGAL_RESEARCH_RERANKER_SCORE_WEIGHT", cls.reranker_score_weight, 0.0, 1.0
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
