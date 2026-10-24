"""自动化性能监控 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def health_check() -> dict[str, Any]:
    """自动化系统健康检查（各依赖服务可用性）。"""
    return client.get("/automation/performance/health")  # type: ignore[return-value]


def get_performance_metrics() -> dict[str, Any]:
    """获取实时 Token 获取性能指标（成功率/耗时）。"""
    return client.get("/automation/performance/metrics")  # type: ignore[return-value]


def get_statistics_report(days: int = 7, site_name: str | None = None) -> dict[str, Any]:
    """获取自动化统计报告,可按天数和站点筛选。"""
    params: dict[str, Any] = {"days": days}
    if site_name is not None:
        params["site_name"] = site_name
    return client.get("/automation/performance/statistics", params=params)  # type: ignore[return-value]


def get_resource_usage() -> dict[str, Any]:
    """获取并发资源（浏览器实例等）占用信息。"""
    return client.get("/automation/performance/resource-usage")  # type: ignore[return-value]


def get_cache_statistics() -> dict[str, Any]:
    """获取 Token/会话缓存命中率统计。"""
    return client.get("/automation/performance/cache-stats")  # type: ignore[return-value]


def optimize_concurrency() -> dict[str, Any]:
    """分析当前使用情况并给出并发优化建议（只建议,不改动）。"""
    return client.post("/automation/performance/optimize-concurrency", json={})  # type: ignore[return-value]


def warm_up_cache(site_name: str) -> dict[str, Any]:
    """预热指定站点的登录缓存（提前完成认证,减少首次访问延迟）。"""
    return client.post("/automation/performance/cache/warm-up", params={"site_name": site_name}, json={})  # type: ignore[return-value]


def clear_cache() -> None:
    """清除所有 Token 相关缓存——之后各站点需重新登录;影响面大,慎用。"""
    client.delete("/automation/performance/cache/clear")


def reset_performance_metrics() -> dict[str, Any]:
    """重置全部性能监控指标归零（历史数据不可找回）。"""
    return client.post("/automation/performance/metrics/reset", json={})  # type: ignore[return-value]


def cleanup_resources() -> dict[str, Any]:
    """清理闲置并发资源和过期锁——卡死任务后恢复用。"""
    return client.post("/automation/performance/resources/cleanup", json={})  # type: ignore[return-value]
