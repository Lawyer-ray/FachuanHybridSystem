# ============================================================
# 法穿案件管理系统 - 资源监控API视图
# ============================================================
# Requirements: 4.1, 4.2, 4.3, 4.4
# 提供资源监控和管理的API接口
# ============================================================

"""Module for resource views."""

import json
import logging
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.core.infrastructure.resource_monitor import get_resource_status, get_resource_usage, resource_monitor

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def resource_status_view(request: HttpRequest) -> JsonResponse:
    """
    获取资源状态API
    Requirements: 4.1, 4.2, 4.3, 4.4 - 资源监控和状态查询
    """
    try:
        status = get_resource_status()
        return JsonResponse(status)
    except Exception as e:
        logger.error(f"Error getting resource status: {e}")
        return JsonResponse({"status": "error", "message": f"Failed to get resource status: {e!s}"}, status=500)


@require_http_methods(["GET"])
def resource_usage_view(request: HttpRequest) -> JsonResponse:
    """
    获取资源使用情况API
    Requirements: 4.1, 4.2 - 资源使用情况查询
    """
    try:
        usage = get_resource_usage()
        if usage:
            return JsonResponse(
                {
                    "cpu_percent": usage.cpu_percent,
                    "memory_percent": usage.memory_percent,
                    "memory_used_mb": usage.memory_used_mb,
                    "memory_total_mb": usage.memory_total_mb,
                    "disk_percent": usage.disk_percent,
                    "disk_used_gb": usage.disk_used_gb,
                    "disk_total_gb": usage.disk_total_gb,
                    "timestamp": usage.timestamp.isoformat(),
                }
            )
        else:
            return JsonResponse({"error": "Resource monitoring not available"}, status=503)
    except Exception as e:
        logger.error(f"Error getting resource usage: {e}")
        return JsonResponse({"error": f"Failed to get resource usage: {e!s}"}, status=500)


@require_http_methods(["GET"])
def resource_recommendations_view(request: HttpRequest) -> JsonResponse:
    """
    获取资源优化建议API
    Requirements: 4.1, 4.2 - 动态资源分配建议
    """
    try:
        recommendations = resource_monitor.get_resource_recommendations()
        return JsonResponse(recommendations)
    except Exception as e:
        logger.error(f"Error getting resource recommendations: {e}")
        return JsonResponse({"error": f"Failed to get resource recommendations: {e!s}"}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class ResourceControlView(View):
    """
    资源控制API视图
    Requirements: 4.3 - 资源保护机制控制
    """

    def get(self, request: HttpRequest) -> JsonResponse:
        """获取资源监控配置"""
        try:
            config = {
                "monitoring_enabled": resource_monitor.monitoring_enabled,
                "auto_restart_enabled": resource_monitor.auto_restart_enabled,
                "restart_cooldown": resource_monitor.restart_cooldown,
                "thresholds": {
                    "memory_warning": resource_monitor.thresholds.memory_warning,
                    "memory_critical": resource_monitor.thresholds.memory_critical,
                    "cpu_warning": resource_monitor.thresholds.cpu_warning,
                    "disk_warning": resource_monitor.thresholds.disk_warning,
                    "disk_critical": resource_monitor.thresholds.disk_critical,
                    "auto_restart_memory": resource_monitor.thresholds.auto_restart_memory,
                },
            }
            return JsonResponse(config)
        except Exception as e:
            logger.error(f"Error getting resource config: {e}")
            return JsonResponse({"error": f"Failed to get resource config: {e!s}"}, status=500)

    def post(self, request: HttpRequest) -> JsonResponse:
        """触发资源保护操作"""
        try:
            data = json.loads(request.body)
            action = data.get("action")

            if action == "check_restart":
                # 检查是否应该重启
                should_restart, reason = resource_monitor.should_trigger_restart()
                return JsonResponse(
                    {
                        "should_restart": should_restart,
                        "reason": reason,
                        "last_restart_time": (
                            resource_monitor._last_restart_time.isoformat()
                            if resource_monitor._last_restart_time
                            else None
                        ),
                    }
                )

            elif action == "record_restart":
                # 记录重启时间
                resource_monitor.record_restart()
                return JsonResponse(
                    {
                        "message": "Restart recorded",
                        "restart_time": (
                            resource_monitor._last_restart_time.isoformat()
                            if resource_monitor._last_restart_time
                            else None
                        ),
                    }
                )

            elif action == "start_monitoring":
                # 启动监控
                interval = data.get("interval", 60)
                resource_monitor.start_monitoring(interval)
                return JsonResponse({"message": f"Resource monitoring started with {interval}s interval"})

            elif action == "stop_monitoring":
                # 停止监控
                resource_monitor.stop_monitoring()
                return JsonResponse({"message": "Resource monitoring stopped"})

            else:
                return JsonResponse({"error": f"Unknown action: {action}"}, status=400)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON data"}, status=400)
        except Exception as e:
            logger.error(f"Error in resource control: {e}")
            return JsonResponse({"error": f"Failed to execute resource control: {e!s}"}, status=500)


@require_http_methods(["GET"])
def resource_health_view(request: HttpRequest) -> JsonResponse:
    """
    资源健康检查API(用于外部监控系统)
    Requirements: 4.3, 4.4 - 资源健康状态检查
    """
    try:
        health = resource_monitor.check_resource_health()

        # 根据状态设置HTTP状态码
        if health["status"] == "critical":
            status_code = 503  # Service Unavailable
        elif health["status"] == "warning":
            status_code = 200  # OK but with warnings
        else:
            status_code = 200  # OK

        return JsonResponse(health, status=status_code)
    except Exception as e:
        logger.error(f"Error in resource health check: {e}")
        return JsonResponse({"status": "error", "message": f"Health check failed: {e!s}"}, status=500)


# 便捷的URL模式定义
resource_urls: list[tuple[Any, ...]] = [
    ("resource/status/", resource_status_view, "resource-status"),
    ("resource/usage/", resource_usage_view, "resource-usage"),
    ("resource/recommendations/", resource_recommendations_view, "resource-recommendations"),
    ("resource/control/", ResourceControlView.as_view(), "resource-control"),
    ("resource/health/", resource_health_view, "resource-health"),
]
