"""阈值策略：自适应阈值衰减、双重审查配置、重试退避参数。"""

from __future__ import annotations

from dataclasses import dataclass

from apps.legal_research.services.tuning_config import LegalResearchTuningConfig


@dataclass(frozen=True)
class DualReviewPolicy:
    enabled: bool
    review_model: str
    primary_weight: float
    secondary_weight: float
    trigger_floor: float
    gap_tolerance: float
    required_min: float


@dataclass(frozen=True)
class AdaptiveThresholdPolicy:
    enabled: bool
    floor: float
    step: float
    scan_interval: int


class ExecutorPolicyMixin:
    CANDIDATE_BATCH_SIZE = 100
    PAGE_SIZE_HINT = 20
    MAX_PAGE_WINDOW = 2000
    SEARCH_RETRY_ATTEMPTS = 3
    DETAIL_RETRY_ATTEMPTS = 3
    DOWNLOAD_RETRY_ATTEMPTS = 3
    RETRY_BACKOFF_SECONDS = 0.8
    RETRY_BACKOFF_MAX_SECONDS = 6.0
    DETAIL_FAILURE_BACKFILL_MULTIPLIER = 2

    @staticmethod
    def _resolve_effective_min_similarity(
        *,
        requested_min_similarity: float,
        tuning: LegalResearchTuningConfig,
    ) -> float:
        baseline = max(0.0, min(1.0, float(requested_min_similarity)))
        if not tuning.online_tuning_enabled:
            return baseline
        adjusted = baseline + float(tuning.online_min_similarity_delta)
        return max(0.4, min(0.99, adjusted))

    @staticmethod
    def _build_dual_review_policy(*, tuning: LegalResearchTuningConfig) -> DualReviewPolicy:
        review_model = str(tuning.dual_review_model or "").strip()
        enabled = bool(tuning.dual_review_enabled and review_model)
        primary_weight = max(0.0, min(1.0, float(tuning.dual_review_primary_weight)))
        secondary_weight = max(0.0, min(1.0, float(tuning.dual_review_secondary_weight)))
        if primary_weight + secondary_weight <= 0:
            primary_weight = 0.62
            secondary_weight = 0.38
        return DualReviewPolicy(
            enabled=enabled,
            review_model=review_model,
            primary_weight=primary_weight,
            secondary_weight=secondary_weight,
            trigger_floor=max(0.0, min(1.0, float(tuning.dual_review_trigger_floor))),
            gap_tolerance=max(0.01, min(0.6, float(tuning.dual_review_gap_tolerance))),
            required_min=max(0.0, min(1.0, float(tuning.dual_review_required_min))),
        )

    @staticmethod
    def _build_adaptive_threshold_policy(
        *,
        baseline_min_similarity: float,
        tuning: LegalResearchTuningConfig,
    ) -> AdaptiveThresholdPolicy:
        baseline = max(0.4, min(0.99, float(baseline_min_similarity)))
        configured_floor = max(0.4, min(0.99, float(tuning.adaptive_threshold_floor)))
        floor = min(baseline, configured_floor)
        step = max(0.005, min(0.2, float(tuning.adaptive_threshold_step)))
        scan_interval = max(10, int(tuning.adaptive_threshold_scan_interval))
        enabled = bool(tuning.adaptive_threshold_enabled and floor < baseline)
        return AdaptiveThresholdPolicy(enabled=enabled, floor=floor, step=step, scan_interval=scan_interval)

    @staticmethod
    def _maybe_decay_min_similarity_threshold(
        *,
        current_threshold: float,
        scanned: int,
        matched: int,
        checkpoint_scanned: int,
        checkpoint_matched: int,
        policy: AdaptiveThresholdPolicy,
    ) -> tuple[float, int, int, bool]:
        if not policy.enabled:
            return current_threshold, checkpoint_scanned, checkpoint_matched, False
        if current_threshold <= policy.floor + 1e-6:
            return current_threshold, scanned, matched, False
        if matched > checkpoint_matched:
            return current_threshold, scanned, matched, False
        if scanned - checkpoint_scanned < policy.scan_interval:
            return current_threshold, checkpoint_scanned, checkpoint_matched, False

        lowered = max(policy.floor, current_threshold - policy.step)
        if lowered >= current_threshold:
            return current_threshold, scanned, matched, False
        return lowered, scanned, matched, True

    @staticmethod
    def _build_adaptive_threshold_suffix(*, baseline: float, lowered_to: float) -> str:
        baseline_value = max(0.0, min(1.0, float(baseline)))
        lowered_value = max(0.0, min(1.0, float(lowered_to)))
        if lowered_value >= baseline_value - 1e-6:
            return ""
        return f"（自适应阈值 {baseline_value:.2f}→{lowered_value:.2f}）"
