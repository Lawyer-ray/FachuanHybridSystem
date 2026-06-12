"""自动化性能监控 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def health_check() -> dict[str, Any]:
    """系统健康检查。"""
    return client.get("/automation/performance/health")  # type: ignore[return-value]


def get_performance_metrics() -> dict[str, Any]:
    """获取实时 Token 获取性能指标。"""
    return client.get("/automation/performance/metrics")  # type: ignore[return-value]


def get_statistics_report(days: int = 7, site_name: str | None = None) -> dict[str, Any]:
    """获取统计报告，可按天数和站点筛选。"""
    params: dict[str, Any] = {"days": days}
    if site_name is not None:
        params["site_name"] = site_name
    return client.get("/automation/performance/statistics", params=params)  # type: ignore[return-value]


def get_resource_usage() -> dict[str, Any]:
    """获取并发资源使用信息。"""
    return client.get("/automation/performance/resource-usage")  # type: ignore[return-value]


def get_cache_statistics() -> dict[str, Any]:
    """获取缓存使用统计。"""
    return client.get("/automation/performance/cache-stats")  # type: ignore[return-value]


def optimize_concurrency() -> dict[str, Any]:
    """分析当前使用情况并提供并发优化建议。"""
    return client.post("/automation/performance/optimize-concurrency", json={})  # type: ignore[return-value]


def warm_up_cache(site_name: str) -> dict[str, Any]:
    """预热指定站点的缓存。"""
    return client.post("/automation/performance/cache/warm-up", params={"site_name": site_name}, json={})  # type: ignore[return-value]


def clear_cache() -> None:
    """清除所有 Token 相关缓存。"""
    client.delete("/automation/performance/cache/clear")


def reset_performance_metrics() -> dict[str, Any]:
    """重置所有性能监控指标。"""
    return client.post("/automation/performance/metrics/reset", json={})  # type: ignore[return-value]


def cleanup_resources() -> dict[str, Any]:
    """清理并发资源和过期锁。"""
    return client.post("/automation/performance/resources/cleanup", json={})  # type: ignore[return-value]
