"""检索执行期配置快照。

`LegalResearchExecutor.run()` 原本在方法体内逐行读取 tuning 配置，混着 20+ 个
局部变量，既难读也无法单测。这里把「读配置 → 归一化 → 夹取取值范围」这一整段
纯计算收拢成不可变快照，run() 只保留执行编排。

所有夹取（clamp）口径与原实现逐字一致，改动这里等于改动检索策略：
- `query_variant_max_count` 下限 0
- `detail_cache_ttl_seconds` 下限 60
- `feedback_query_limit` 下限 0
- `feedback_min_terms` 下限 1
- `feedback_min_score_floor` / `feedback_score_margin` 夹到 [0, 1] / [0.01, 0.6]
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.legal_research.models import LegalResearchSearchMode, LegalResearchTask
from apps.legal_research.services.executor_components.policy_mixin import (
    AdaptiveThresholdPolicy,
    DualReviewPolicy,
    _build_adaptive_threshold_policy,
    _build_dual_review_policy,
    _resolve_effective_min_similarity,
)
from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig


@dataclass(frozen=True)
class ExecutorRunConfig:
    """一次 run() 的检索策略快照（不可变）。"""

    tuning: LegalResearchTuningConfig
    search_mode: str
    single_search_mode: bool
    query_variant_enabled: bool
    query_variant_max_count: int
    query_variant_model: str
    detail_cache_ttl_seconds: int
    feedback_query_limit: int
    feedback_min_terms: int
    feedback_min_score_floor: float
    feedback_score_margin: float
    dual_review_policy: DualReviewPolicy
    min_similarity_threshold: float
    adaptive_threshold_policy: AdaptiveThresholdPolicy


def build_run_config(
    *,
    task: LegalResearchTask,
    tuning: LegalResearchTuningConfig,
    query_variant_max: int,
    detail_cache_ttl_default: int,
) -> ExecutorRunConfig:
    """从任务与 tuning 构造执行期配置快照。

    Args:
        task: 待执行的检索任务。
        tuning: 已加载的 tuning 配置。
        query_variant_max: ``query_variant_max_count`` 的兜底默认值（执行器的类常量）。
        detail_cache_ttl_default: ``detail_cache_ttl_seconds`` 的兜底默认值。
    """
    search_mode = str(
        getattr(task, "search_mode", LegalResearchSearchMode.EXPANDED) or LegalResearchSearchMode.EXPANDED
    )
    min_similarity_threshold = _resolve_effective_min_similarity(
        requested_min_similarity=task.min_similarity_score,
        tuning=tuning,
    )
    return ExecutorRunConfig(
        tuning=tuning,
        search_mode=search_mode,
        single_search_mode=search_mode.strip().lower() == LegalResearchSearchMode.SINGLE,
        query_variant_enabled=bool(getattr(tuning, "query_variant_enabled", True)),
        query_variant_max_count=max(0, int(getattr(tuning, "query_variant_max_count", query_variant_max))),
        query_variant_model=str(getattr(tuning, "query_variant_model", "") or "").strip(),
        detail_cache_ttl_seconds=max(60, int(getattr(tuning, "detail_cache_ttl_seconds", detail_cache_ttl_default))),
        feedback_query_limit=max(0, int(tuning.feedback_query_limit)),
        feedback_min_terms=max(1, int(tuning.feedback_min_terms)),
        feedback_min_score_floor=max(0.0, min(1.0, float(tuning.feedback_min_score_floor))),
        feedback_score_margin=max(0.01, min(0.6, float(tuning.feedback_score_margin))),
        dual_review_policy=_build_dual_review_policy(tuning=tuning),
        min_similarity_threshold=min_similarity_threshold,
        adaptive_threshold_policy=_build_adaptive_threshold_policy(
            baseline_min_similarity=min_similarity_threshold,
            tuning=tuning,
        ),
    )
