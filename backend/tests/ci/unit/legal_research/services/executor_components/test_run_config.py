"""ExecutorRunConfig 配置快照单测。

这段逻辑原先埋在 `LegalResearchExecutor.run()` 的 650 行方法体内，无法单独验证；
抽成 build_run_config 后可直接断言夹取口径——这些口径直接决定检索召回/精度，
改动它们等于改检索策略，所以值得钉死。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from apps.legal_research.models import LegalResearchSearchMode
from apps.legal_research.services.executor_components.run_config import build_run_config
from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig


def _tuning(**overrides: Any) -> LegalResearchTuningConfig:
    """真实 tuning dataclass（frozen，带默认值），只覆盖本组用例关心的字段。"""
    base: dict[str, Any] = {
        "query_variant_enabled": True,
        "query_variant_max_count": 5,
        "query_variant_model": "  qwen  ",
        "detail_cache_ttl_seconds": 3600,
        "feedback_query_limit": 10,
        "feedback_min_terms": 2,
        "feedback_min_score_floor": 0.5,
        "feedback_score_margin": 0.1,
        "online_tuning_enabled": False,
        "online_min_similarity_delta": 0.0,
    }
    base.update(overrides)
    return LegalResearchTuningConfig(**base)


def _task(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "search_mode": LegalResearchSearchMode.SINGLE,
        "min_similarity_score": 0.9,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _build(tuning: Any, task: Any) -> Any:
    return build_run_config(task=task, tuning=tuning, query_variant_max=8, detail_cache_ttl_default=1800)


def test_single_search_mode_flag() -> None:
    cfg = _build(_tuning(), _task(search_mode=LegalResearchSearchMode.SINGLE))
    assert cfg.single_search_mode is True
    assert cfg.search_mode == LegalResearchSearchMode.SINGLE


def test_expanded_mode_flag_false() -> None:
    cfg = _build(_tuning(), _task(search_mode=LegalResearchSearchMode.EXPANDED))
    assert cfg.single_search_mode is False


def test_search_mode_case_and_whitespace_normalized() -> None:
    cfg = _build(_tuning(), _task(search_mode="  SINGLE  "))
    assert cfg.single_search_mode is True


def test_query_variant_model_stripped() -> None:
    assert _build(_tuning(), _task()).query_variant_model == "qwen"


def test_query_variant_max_count_clamped_to_zero() -> None:
    assert _build(_tuning(query_variant_max_count=-3), _task()).query_variant_max_count == 0


def test_detail_cache_ttl_floor_is_60() -> None:
    assert _build(_tuning(detail_cache_ttl_seconds=5), _task()).detail_cache_ttl_seconds == 60


def test_feedback_clamps() -> None:
    cfg = _build(_tuning(feedback_query_limit=-1, feedback_min_terms=0), _task())
    assert cfg.feedback_query_limit == 0
    assert cfg.feedback_min_terms == 1


@pytest.mark.parametrize(("raw", "expected"), [(-1.0, 0.0), (2.0, 1.0), (0.42, 0.42)])
def test_feedback_min_score_floor_clamped_0_1(raw: float, expected: float) -> None:
    assert _build(_tuning(feedback_min_score_floor=raw), _task()).feedback_min_score_floor == pytest.approx(expected)


@pytest.mark.parametrize(("raw", "expected"), [(0.0, 0.01), (1.0, 0.6), (0.3, 0.3)])
def test_feedback_score_margin_clamped(raw: float, expected: float) -> None:
    assert _build(_tuning(feedback_score_margin=raw), _task()).feedback_score_margin == pytest.approx(expected)


def test_min_similarity_from_task_not_tuning() -> None:
    cfg = _build(_tuning(), _task(min_similarity_score=0.75))
    assert cfg.min_similarity_threshold == pytest.approx(0.75)


def test_config_is_immutable() -> None:
    cfg = _build(_tuning(), _task())
    with pytest.raises(Exception):
        cfg.search_mode = "other"  # type: ignore[misc]
