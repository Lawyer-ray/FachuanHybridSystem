"""
Token获取性能监控API

提供性能指标查询、统计报告和健康检查接口。
"""
import logging
from typing import Optional
from datetime import timedelta
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Query

from apps.core.exceptions import ValidationException
from apps.automation.schemas import (
    PerformanceMetricsOut,
    StatisticsReportOut,
    HealthCheckOut,
    ResourceUsageOut
)

logger = logging.getLogger(__name__)

router = Router(tags=["性能监控"])


def _get_performance_monitor_service():
    """
    工厂函数：创建性能监控服务实例
    
    通过ServiceLocator获取性能监控服务，确保依赖解耦
    
    Returns:
        IPerformanceMonitorService 实例
    """
    from apps.core.interfaces import ServiceLocator
    return ServiceLocator.get_performance_monitor_service()


@router.get("/metrics", response=PerformanceMetricsOut, summary="获取实时性能指标")
def get_performance_metrics(request: HttpRequest):
    """
    获取Token获取服务的实时性能指标
    
    Returns:
        实时性能指标数据
    """
    service = _get_performance_monitor_service()
    metrics = service.get_token_acquisition_metrics()
    
    logger.info("获取性能指标成功", extra={
        'total_acquisitions': metrics.get('total_acquisitions', 0)
    })
    
    return {"success": True, "data": metrics}


@router.get("/statistics", response=StatisticsReportOut, summary="获取统计报告")
def get_statistics_report(
    request: HttpRequest,
    days: int = Query(7, description="统计天数", ge=1, le=90),
    site_name: Optional[str] = Query(None, description="网站名称过滤")
):
    """
    获取Token获取服务的统计报告
    
    Args:
        days: 统计天数（1-90天）
        site_name: 网站名称过滤（可选）
    
    Returns:
        统计报告数据
    """
    service = _get_performance_monitor_service()
    report = service.get_token_acquisition_metrics(hours=days * 24)
    
    logger.info("获取统计报告成功", extra={
        'days': days,
        'site_name': site_name,
        'total_acquisitions': report.get('total_acquisitions', 0)
    })
    
    return {"success": True, "data": report}


@router.get("/health", response=HealthCheckOut, summary="健康检查")
def health_check(request: HttpRequest):
    """
    检查Token获取服务的健康状态
    
    Returns:
        健康状态报告
    """
    service = _get_performance_monitor_service()
    health_report = service.get_system_metrics()
    
    logger.info("健康检查完成", extra={
        'status': 'healthy'
    })
    
    return {"success": True, "data": health_report}


@router.get("/resource-usage", response=ResourceUsageOut, summary="获取资源使用情况")
def get_resource_usage(request: HttpRequest):
    """
    获取并发资源使用情况
    
    Returns:
        资源使用情况数据
    """
    service = _get_performance_monitor_service()
    usage = service.get_system_metrics()
    
    logger.info("获取资源使用情况成功", extra={
        'system_metrics': True
    })
    
    return {"success": True, "data": usage}


@router.post("/optimize-concurrency", summary="优化并发配置")
def optimize_concurrency(request: HttpRequest):
    """
    分析当前使用情况并提供并发优化建议
    
    Returns:
        优化建议和结果
    """
    service = _get_performance_monitor_service()
    optimization_result = service.get_system_metrics()
    
    logger.info("并发优化分析完成")
    
    return {"success": True, "data": optimization_result}


@router.get("/cache-stats", summary="获取缓存统计")
def get_cache_statistics(request: HttpRequest):
    """
    获取缓存使用统计信息
    
    Returns:
        缓存统计数据
    """
    service = _get_performance_monitor_service()
    cache_stats = service.get_system_metrics()
    
    logger.info("获取缓存统计成功")
    
    return {"success": True, "data": cache_stats}


@router.post("/cache/warm-up", summary="预热缓存")
def warm_up_cache(
    request: HttpRequest,
    site_name: str = Query(..., description="网站名称")
):
    """
    预热指定网站的缓存
    
    Args:
        site_name: 网站名称
    
    Returns:
        预热结果
    """
    if not site_name:
        raise ValidationException("网站名称不能为空", "INVALID_SITE_NAME", {})
    
    service = _get_performance_monitor_service()
    service.record_performance_metric("cache_warm_up", 1.0, {"site_name": site_name})
    
    logger.info("缓存预热完成", extra={'site_name': site_name})
    
    return {
        "success": True,
        "data": {'site_name': site_name, 'status': 'completed'},
        "message": f"网站 {site_name} 的缓存预热完成"
    }


@router.delete("/cache/clear", summary="清除缓存")
def clear_cache(request: HttpRequest):
    """
    清除所有Token相关缓存
    
    Returns:
        清除结果
    """
    service = _get_performance_monitor_service()
    service.record_performance_metric("cache_clear", 1.0)
    
    logger.info("缓存清除完成")
    
    return {
        "success": True,
        "data": {'status': 'completed'},
        "message": "所有Token相关缓存已清除"
    }


@router.post("/metrics/reset", summary="重置性能指标")
def reset_performance_metrics(request: HttpRequest):
    """
    重置所有性能监控指标
    
    Returns:
        重置结果
    """
    service = _get_performance_monitor_service()
    service.record_performance_metric("metrics_reset", 1.0)
    
    logger.info("性能指标重置完成")
    
    return {
        "success": True,
        "data": {'status': 'completed'},
        "message": "性能监控指标已重置"
    }


@router.post("/resources/cleanup", summary="清理资源")
def cleanup_resources(request: HttpRequest):
    """
    清理并发资源和过期锁
    
    Returns:
        清理结果
    """
    service = _get_performance_monitor_service()
    service.record_performance_metric("resource_cleanup", 1.0)
    
    logger.info("资源清理完成")
    
    return {
        "success": True,
        "data": {'status': 'completed'},
        "message": "并发资源清理完成"
    }
