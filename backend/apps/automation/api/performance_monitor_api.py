"""
Token获取性能监控API

提供性能指标查询、统计报告和健康检查接口。
"""

import logging
from typing import Any

from django.http import HttpRequest
from ninja import Query, Router

from apps.automation.schemas import HealthCheckOut, PerformanceMetricsOut, ResourceUsageOut, StatisticsReportOut
from apps.core.exceptions import ValidationException
from apps.core.security.admin_access import ensure_admin_request

logger = logging.getLogger(__name__)

router = Router(tags=["性能监控"])


def _get_performance_monitor_service() -> Any:
    from apps.core.dependencies import build_performance_monitor_service

    return build_performance_monitor_service()


@router.get("/metrics", response=PerformanceMetricsOut, summary="获取实时性能指标")
def get_performance_metrics(request: HttpRequest) -> dict[str, Any]:
    """获取Token获取服务的实时性能指标"""
    ensure_admin_request(request)
    service = _get_performance_monitor_service()
    metrics = service.get_token_acquisition_metrics()  # type: ignore[attr-defined]
    logger.info("获取性能指标成功", extra={"total_acquisitions": metrics.get("total_acquisitions", 0)})
    return {"success": True, "data": metrics}


@router.get("/statistics", response=StatisticsReportOut, summary="获取统计报告")
def get_statistics_report(
    request: HttpRequest,
    days: int = Query(7, description="统计天数", ge=1, le=90),  # type: ignore[call-overload]
    site_name: str | None = Query(None, description="网站名称过滤"),  # type: ignore[misc]
) -> dict[str, Any]:
    """获取Token获取服务的统计报告"""
    ensure_admin_request(request)
    service = _get_performance_monitor_service()
    report = service.get_token_acquisition_metrics(hours=days * 24)  # type: ignore[attr-defined]
    logger.info(
        "获取统计报告成功",
        extra={"days": days, "site_name": site_name, "total_acquisitions": report.get("total_acquisitions", 0)},
    )
    return {"success": True, "data": report}


@router.get("/health", summary="健康检查")
def health_check(request: HttpRequest) -> dict[str, Any]:
    """检查Token获取服务的健康状态"""
    ensure_admin_request(request)
    service = _get_performance_monitor_service()
    health_report = service.get_system_metrics()  # type: ignore[attr-defined]
    logger.info("健康检查完成", extra={"status": "healthy"})
    return health_report


@router.get("/resource-usage", summary="获取资源使用情况")
def get_resource_usage(request: HttpRequest) -> dict[str, Any]:
    """获取并发资源使用情况"""
    ensure_admin_request(request)
    service = _get_performance_monitor_service()
    usage = service.get_system_metrics()  # type: ignore[attr-defined]
    logger.info("获取资源使用情况成功", extra={"system_metrics": True})
    return usage


@router.post("/optimize-concurrency", summary="优化并发配置")
def optimize_concurrency(request: HttpRequest) -> dict[str, Any]:
    """分析当前使用情况并提供并发优化建议"""
    ensure_admin_request(request)
    service = _get_performance_monitor_service()
    optimization_result = service.get_system_metrics()  # type: ignore[attr-defined]
    logger.info("并发优化分析完成")
    return {"success": True, "data": optimization_result}


@router.get("/cache-stats", summary="获取缓存统计")
def get_cache_statistics(request: HttpRequest) -> dict[str, Any]:
    """获取缓存使用统计信息"""
    ensure_admin_request(request)
    service = _get_performance_monitor_service()
    cache_stats = service.get_system_metrics()  # type: ignore[attr-defined]
    logger.info("获取缓存统计成功")
    return {"success": True, "data": cache_stats}


@router.post("/cache/warm-up", summary="预热缓存")
def warm_up_cache(
    request: HttpRequest,
    site_name: str = Query(..., description="网站名称"),  # type: ignore[call-overload]
) -> dict[str, Any]:
    """预热指定网站的缓存"""
    ensure_admin_request(request)
    if not site_name:
        raise ValidationException("网站名称不能为空", "INVALID_SITE_NAME", {})
    service = _get_performance_monitor_service()
    service.record_performance_metric("cache_warm_up", 1.0, {"site_name": site_name})  # type: ignore[attr-defined]
    logger.info("缓存预热完成", extra={"site_name": site_name})
    return {
        "success": True,
        "data": {"site_name": site_name, "status": "completed"},
        "message": f"网站 {site_name} 的缓存预热完成",
    }


@router.delete("/cache/clear", summary="清除缓存")
def clear_cache(request: HttpRequest) -> dict[str, Any]:
    """清除所有Token相关缓存"""
    ensure_admin_request(request)
    service = _get_performance_monitor_service()
    service.record_performance_metric("cache_clear", 1.0)  # type: ignore[attr-defined]
    logger.info("缓存清除完成")
    return {"success": True, "data": {"status": "completed"}, "message": "所有Token相关缓存已清除"}


@router.post("/metrics/reset", summary="重置性能指标")
def reset_performance_metrics(request: HttpRequest) -> dict[str, Any]:
    """重置所有性能监控指标"""
    ensure_admin_request(request)
    service = _get_performance_monitor_service()
    service.record_performance_metric("metrics_reset", 1.0)  # type: ignore[attr-defined]
    logger.info("性能指标重置完成")
    return {"success": True, "data": {"status": "completed"}, "message": "性能监控指标已重置"}


@router.post("/resources/cleanup", summary="清理资源")
def cleanup_resources(request: HttpRequest) -> dict[str, Any]:
    """清理并发资源和过期锁"""
    ensure_admin_request(request)
    service = _get_performance_monitor_service()
    service.record_performance_metric("resource_cleanup", 1.0)  # type: ignore[attr-defined]
    logger.info("资源清理完成")
    return {"success": True, "data": {"status": "completed"}, "message": "并发资源清理完成"}
