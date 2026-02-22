"""HealthChecker 类：聚合所有检查方法"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from django.conf import settings

from ._checkers import check_cache, check_database, check_dependencies, check_disk_space
from ._models import ComponentHealth, HealthStatus, SystemHealth, _start_time
from ._resources import check_system_resources

logger = logging.getLogger(__name__)

__all__ = ["HealthChecker"]


class HealthChecker:
    """健康检查器"""

    # NOTE: 使用 staticmethod() 函数调用将独立检查函数绑定为类的静态方法，
    # 这是基础设施层的可接受模式（非 Service 层，不受 @staticmethod 禁令约束）。
    # 这种模式允许检查函数既可独立使用，也可通过 HealthChecker 类统一调用。
    check_database = staticmethod(check_database)
    check_cache = staticmethod(check_cache)
    check_disk_space = staticmethod(check_disk_space)
    check_system_resources = staticmethod(check_system_resources)
    check_dependencies = staticmethod(check_dependencies)

    @classmethod
    def get_system_health(cls, include_details: bool = False) -> SystemHealth:
        """获取系统健康状态"""
        components: list[ComponentHealth] = [
            cls.check_database(),
            cls.check_cache(),
        ]

        if include_details:
            components.extend(
                [
                    cls.check_disk_space(),
                    cls.check_system_resources(),
                    cls.check_dependencies(),
                ]
            )

        statuses = [c.status for c in components]

        if HealthStatus.UNHEALTHY in statuses:
            overall_status = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        system_info: dict[str, Any] = {}
        if include_details:
            try:
                import sys

                system_info.update(
                    {
                        "hostname": os.uname().nodename,
                        "platform": os.uname().sysname,
                        "python_version": sys.version.split()[0],
                        "django_version": getattr(settings, "DJANGO_VERSION", "unknown"),
                        "service_name": os.environ.get("SERVICE_NAME", "backend"),
                        "service_role": os.environ.get("SERVICE_ROLE", "web"),
                        "environment_type": os.environ.get("ENVIRONMENT_TYPE", "production"),
                    }
                )
            except Exception as e:
                logger.exception("操作失败")
                system_info["collection_error"] = str(e)

        version = os.environ.get("APP_VERSION") or str(getattr(settings, "API_VERSION", "1.0.0"))

        return SystemHealth(
            status=overall_status,
            version=version,
            uptime_seconds=time.time() - _start_time,
            components=components,
            system_info=system_info,
        )

    @classmethod
    def liveness_check(cls) -> dict[str, str]:
        """存活检查（Kubernetes liveness probe）"""
        return {"status": "ok", "timestamp": str(time.time())}

    @classmethod
    def readiness_check(cls) -> dict[str, Any]:
        """就绪检查（Kubernetes readiness probe）"""
        db_health = cls.check_database()
        cache_health = cls.check_cache()
        llm_health_value = "unknown"
        llm_error = None
        llm_required = False

        try:
            from apps.core.llm.warmup import get_llm_warmup_state

            llm_state = get_llm_warmup_state()
            llm_ok = bool(llm_state.get("ok"))
            llm_ts = llm_state.get("timestamp")
            llm_error = llm_state.get("error")
            llm_required = bool(getattr(settings, "LITIGATION_USE_AGENT_MODE", False)) or (
                (os.environ.get("DJANGO_LLM_READY_REQUIRED", "") or "").lower().strip() in ("true", "1", "yes")
            )
            if llm_ts is None:
                llm_health_value = "unknown"
            else:
                llm_health_value = "healthy" if llm_ok else "unhealthy"
        except Exception as e:
            logger.exception("操作失败")
            llm_health_value = "unknown"
            llm_error = str(e)

        if db_health.status == HealthStatus.UNHEALTHY:
            return {
                "status": "not_ready",
                "reason": db_health.message,
                "component": "database",
                "timestamp": time.time(),
            }

        if llm_required and llm_health_value == "unhealthy":
            return {
                "status": "not_ready",
                "reason": f"LLM warmup failed: {llm_error or 'unknown'}",
                "component": "llm_config",
                "timestamp": time.time(),
            }

        ready_info: dict[str, Any] = {
            "status": "ready",
            "timestamp": time.time(),
            "components": {
                "database": db_health.status.value,
                "cache": cache_health.status.value,
                "llm_config": llm_health_value,
            },
        }

        warnings: list[str] = []

        if cache_health.status != HealthStatus.HEALTHY:
            warnings.append(f"Cache {cache_health.status.value}: {cache_health.message}")

        if (not llm_required) and llm_health_value == "unhealthy":
            warnings.append(f"LLM warmup failed: {llm_error or 'unknown'}")

        if llm_health_value == "unknown" and llm_required:
            warnings.append("LLM warmup not executed yet")

        if warnings:
            ready_info["warnings"] = warnings

        return ready_info
