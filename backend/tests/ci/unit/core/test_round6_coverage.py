"""Targeted coverage tests for core module — Round 6.

Targets: health checker, resource checkers
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _checker_class.py — HealthChecker
# ---------------------------------------------------------------------------


class TestHealthChecker:
    """Tests for HealthChecker methods — patching on the class level."""

    def test_get_system_health_healthy(self):
        from apps.core.infrastructure.health._models import ComponentHealth, HealthStatus
        from apps.core.infrastructure.health._checker_class import HealthChecker

        healthy = ComponentHealth(name="x", status=HealthStatus.HEALTHY, message="ok")
        with patch.object(HealthChecker, "check_database", return_value=healthy):
            with patch.object(HealthChecker, "check_cache", return_value=healthy):
                result = HealthChecker.get_system_health()
        assert result.status == HealthStatus.HEALTHY

    def test_get_system_health_degraded(self):
        from apps.core.infrastructure.health._models import ComponentHealth, HealthStatus
        from apps.core.infrastructure.health._checker_class import HealthChecker

        healthy = ComponentHealth(name="db", status=HealthStatus.HEALTHY, message="ok")
        degraded = ComponentHealth(name="cache", status=HealthStatus.DEGRADED, message="slow")
        with patch.object(HealthChecker, "check_database", return_value=healthy):
            with patch.object(HealthChecker, "check_cache", return_value=degraded):
                result = HealthChecker.get_system_health()
        assert result.status == HealthStatus.DEGRADED

    def test_get_system_health_unhealthy(self):
        from apps.core.infrastructure.health._models import ComponentHealth, HealthStatus
        from apps.core.infrastructure.health._checker_class import HealthChecker

        unhealthy = ComponentHealth(name="db", status=HealthStatus.UNHEALTHY, message="down")
        healthy = ComponentHealth(name="cache", status=HealthStatus.HEALTHY, message="ok")
        with patch.object(HealthChecker, "check_database", return_value=unhealthy):
            with patch.object(HealthChecker, "check_cache", return_value=healthy):
                result = HealthChecker.get_system_health()
        assert result.status == HealthStatus.UNHEALTHY

    def test_get_system_health_with_details(self):
        from apps.core.infrastructure.health._models import ComponentHealth, HealthStatus
        from apps.core.infrastructure.health._checker_class import HealthChecker

        healthy = ComponentHealth(name="x", status=HealthStatus.HEALTHY, message="ok")
        with patch.object(HealthChecker, "check_database", return_value=healthy):
            with patch.object(HealthChecker, "check_cache", return_value=healthy):
                with patch.object(HealthChecker, "check_disk_space", return_value=healthy):
                    with patch.object(HealthChecker, "check_system_resources", return_value=healthy):
                        with patch.object(HealthChecker, "check_dependencies", return_value=healthy):
                            result = HealthChecker.get_system_health(include_details=True)
        assert result.status == HealthStatus.HEALTHY
        assert len(result.components) == 5
        assert "python_version" in result.system_info

    def test_liveness_check(self):
        from apps.core.infrastructure.health._checker_class import HealthChecker

        result = HealthChecker.liveness_check()
        assert result["status"] == "ok"
        assert "timestamp" in result

    def test_readiness_check_db_unhealthy(self):
        from apps.core.infrastructure.health._models import ComponentHealth, HealthStatus
        from apps.core.infrastructure.health._checker_class import HealthChecker

        unhealthy = ComponentHealth(name="db", status=HealthStatus.UNHEALTHY, message="down")
        healthy = ComponentHealth(name="cache", status=HealthStatus.HEALTHY, message="ok")
        with patch.object(HealthChecker, "check_database", return_value=unhealthy):
            with patch.object(HealthChecker, "check_cache", return_value=healthy):
                result = HealthChecker.readiness_check()
        assert result["status"] == "not_ready"
        assert result["component"] == "database"

    def test_readiness_check_ready(self):
        from apps.core.infrastructure.health._models import ComponentHealth, HealthStatus
        from apps.core.infrastructure.health._checker_class import HealthChecker

        healthy = ComponentHealth(name="x", status=HealthStatus.HEALTHY, message="ok")
        with patch.object(HealthChecker, "check_database", return_value=healthy):
            with patch.object(HealthChecker, "check_cache", return_value=healthy):
                with patch(
                    "apps.core.llm.warmup.get_llm_warmup_state",
                    return_value={"ok": True, "timestamp": "t", "error": None},
                ):
                    result = HealthChecker.readiness_check()
        assert result["status"] == "ready"

    def test_readiness_check_cache_degraded(self):
        from apps.core.infrastructure.health._models import ComponentHealth, HealthStatus
        from apps.core.infrastructure.health._checker_class import HealthChecker

        healthy = ComponentHealth(name="db", status=HealthStatus.HEALTHY, message="ok")
        degraded = ComponentHealth(name="cache", status=HealthStatus.DEGRADED, message="slow")
        with patch.object(HealthChecker, "check_database", return_value=healthy):
            with patch.object(HealthChecker, "check_cache", return_value=degraded):
                with patch(
                    "apps.core.llm.warmup.get_llm_warmup_state",
                    return_value={"ok": True, "timestamp": "t", "error": None},
                ):
                    result = HealthChecker.readiness_check()
        assert result["status"] == "ready"
        assert "warnings" in result

    def test_readiness_check_llm_warmup_exception(self):
        from apps.core.infrastructure.health._models import ComponentHealth, HealthStatus
        from apps.core.infrastructure.health._checker_class import HealthChecker

        healthy = ComponentHealth(name="x", status=HealthStatus.HEALTHY, message="ok")
        with patch.object(HealthChecker, "check_database", return_value=healthy):
            with patch.object(HealthChecker, "check_cache", return_value=healthy):
                with patch(
                    "apps.core.llm.warmup.get_llm_warmup_state",
                    side_effect=ImportError("no module"),
                ):
                    result = HealthChecker.readiness_check()
        assert result["status"] == "ready"
        assert result["components"]["llm_config"] == "unknown"

    @patch.dict("os.environ", {"DJANGO_LLM_READY_REQUIRED": "true"})
    def test_readiness_check_llm_required_unhealthy(self):
        from apps.core.infrastructure.health._models import ComponentHealth, HealthStatus
        from apps.core.infrastructure.health._checker_class import HealthChecker

        healthy = ComponentHealth(name="x", status=HealthStatus.HEALTHY, message="ok")
        with patch.object(HealthChecker, "check_database", return_value=healthy):
            with patch.object(HealthChecker, "check_cache", return_value=healthy):
                with patch(
                    "apps.core.llm.warmup.get_llm_warmup_state",
                    return_value={"ok": False, "timestamp": "t", "error": "fail"},
                ):
                    result = HealthChecker.readiness_check()
        assert result["status"] == "not_ready"
        assert result["component"] == "llm_config"

    @patch.dict("os.environ", {"DJANGO_LLM_READY_REQUIRED": "true"})
    def test_readiness_check_llm_required_unknown(self):
        from apps.core.infrastructure.health._models import ComponentHealth, HealthStatus
        from apps.core.infrastructure.health._checker_class import HealthChecker

        healthy = ComponentHealth(name="x", status=HealthStatus.HEALTHY, message="ok")
        with patch.object(HealthChecker, "check_database", return_value=healthy):
            with patch.object(HealthChecker, "check_cache", return_value=healthy):
                with patch(
                    "apps.core.llm.warmup.get_llm_warmup_state",
                    return_value={"ok": False, "timestamp": None, "error": None},
                ):
                    result = HealthChecker.readiness_check()
        assert result["status"] == "ready"
        assert "warnings" in result
        assert any("LLM warmup not executed" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# health _checkers — standalone functions
# ---------------------------------------------------------------------------


class TestHealthCheckers:
    """Tests for standalone health check functions."""

    def test_check_disk_space(self):
        from apps.core.infrastructure.health._checkers import check_disk_space

        result = check_disk_space()
        assert result.status.value in ("healthy", "degraded", "unhealthy")
        assert "disk" in result.name.lower()

    def test_check_system_resources(self):
        from apps.core.infrastructure.health._resources import check_system_resources

        result = check_system_resources()
        assert result.status.value in ("healthy", "degraded", "unhealthy")
