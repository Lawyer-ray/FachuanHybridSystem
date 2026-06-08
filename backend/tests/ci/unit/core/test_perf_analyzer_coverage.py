"""Coverage tests for core.config.steering._perf_analyzer."""

from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pytest

from apps.core.config.steering._perf_analyzer import PerformanceAnalyzer


class TestPerformanceAnalyzer:
    def _make_analyzer(self):
        collector = MagicMock()
        thresholds = MagicMock()
        thresholds.load_time_warning_ms = 500
        thresholds.load_time_error_ms = 1000
        thresholds.load_time_critical_ms = 2000
        thresholds.cache_hit_rate_warning = 0.5
        return PerformanceAnalyzer(collector, thresholds), collector

    def _make_history(self, n=20, success=True, cache_hit=False, duration=100, spec="spec1", error_msg=None):
        items = []
        for i in range(n):
            h = MagicMock()
            h.success = success
            h.cache_hit = cache_hit
            h.duration_ms = duration
            h.start_time = i * 1000
            h.spec_path = spec
            h.error_message = error_msg
            h.file_size_bytes = 1024
            items.append(h)
        return items

    def test_analyze_loading_performance_no_data(self):
        analyzer, collector = self._make_analyzer()
        collector.get_recent_loading_history.return_value = []
        result = analyzer.analyze_loading_performance()
        assert "error" in result

    def test_analyze_loading_performance_with_data(self):
        analyzer, collector = self._make_analyzer()
        history = self._make_history(n=20)
        collector.get_recent_loading_history.return_value = history
        result = analyzer.analyze_loading_performance()
        assert result["total_loads"] == 20
        assert result["success_rate"] == 1.0

    def test_analyze_loading_performance_with_filter(self):
        analyzer, collector = self._make_analyzer()
        history = self._make_history(n=10, spec="spec_a") + self._make_history(n=10, spec="spec_b")
        collector.get_recent_loading_history.return_value = history
        result = analyzer.analyze_loading_performance(spec_path="spec_a")
        assert result["total_loads"] == 10

    def test_analyze_loading_performance_caching(self):
        analyzer, collector = self._make_analyzer()
        history = self._make_history(n=10)
        collector.get_recent_loading_history.return_value = history
        result1 = analyzer.analyze_loading_performance()
        result2 = analyzer.analyze_loading_performance()
        assert result1 is result2

    def test_analyze_performance_trend_insufficient(self):
        analyzer, _ = self._make_analyzer()
        history = self._make_history(n=5)
        result = analyzer._analyze_performance_trend(history)
        assert result["trend"] == "insufficient_data"

    def test_analyze_performance_trend_stable(self):
        analyzer, _ = self._make_analyzer()
        history = self._make_history(n=30, duration=100)
        result = analyzer._analyze_performance_trend(history)
        assert result["trend"] == "stable"

    def test_identify_slow_specifications(self):
        analyzer, _ = self._make_analyzer()
        history = self._make_history(n=10, duration=600, spec="slow_spec")
        result = analyzer._identify_slow_specifications(history)
        assert len(result) == 1
        assert result[0]["spec_path"] == "slow_spec"

    def test_identify_slow_specifications_fast(self):
        analyzer, _ = self._make_analyzer()
        history = self._make_history(n=10, duration=10, spec="fast_spec")
        result = analyzer._identify_slow_specifications(history)
        assert len(result) == 0

    def test_analyze_error_patterns_no_errors(self):
        analyzer, _ = self._make_analyzer()
        history = self._make_history(n=10, success=True)
        result = analyzer._analyze_error_patterns(history)
        assert result["total_errors"] == 0

    def test_analyze_error_patterns_with_errors(self):
        analyzer, _ = self._make_analyzer()
        history = self._make_history(n=5, success=False, error_msg="timeout")
        result = analyzer._analyze_error_patterns(history)
        assert result["total_errors"] == 5
        assert "timeout" in result["error_frequency"]

    def test_generate_recommendations_low_cache(self):
        analyzer, _ = self._make_analyzer()
        history = self._make_history(n=100, cache_hit=False, duration=10)
        recs = analyzer._generate_recommendations(history)
        assert len(recs) > 0

    def test_generate_recommendations_high_error(self):
        analyzer, _ = self._make_analyzer()
        history = []
        for i in range(20):
            history.extend(self._make_history(n=1, success=(i > 15), duration=10))
        recs = analyzer._generate_recommendations(history)
        assert any("错误率" in r for r in recs)

    def test_get_severity_level_normal(self):
        analyzer, _ = self._make_analyzer()
        assert analyzer._get_severity_level(100) == "normal"

    def test_get_severity_level_warning(self):
        analyzer, _ = self._make_analyzer()
        assert analyzer._get_severity_level(600) == "warning"

    def test_get_severity_level_error(self):
        analyzer, _ = self._make_analyzer()
        assert analyzer._get_severity_level(1500) == "error"

    def test_get_severity_level_critical(self):
        analyzer, _ = self._make_analyzer()
        assert analyzer._get_severity_level(3000) == "critical"
