"""
性能监控模块

提供 API 响应时间监控和数据库查询次数监控
"""
import time
import logging
from typing import Optional, Dict, Any, Callable
from functools import wraps
from contextlib import contextmanager
from django.db import connection, reset_queries
from django.conf import settings

logger = logging.getLogger("apps.core.monitoring")


class PerformanceMonitor:
    """
    性能监控器
    
    监控 API 响应时间和数据库查询次数
    """
    
    # 性能阈值配置
    SLOW_API_THRESHOLD_MS = 1000  # API 响应时间阈值（毫秒）
    SLOW_QUERY_THRESHOLD_MS = 100  # 慢查询阈值（毫秒）
    MAX_QUERY_COUNT = 10  # 最大查询次数阈值
    
    @staticmethod
    def monitor_api(endpoint: str):
        """
        API 性能监控装饰器
        
        监控 API 响应时间和数据库查询次数
        
        Args:
            endpoint: API 端点名称
            
        Usage:
            @monitor_api("create_case")
            def create_case(request, data):
                ...
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # 重置查询计数
                if settings.DEBUG:
                    reset_queries()
                
                # 记录开始时间
                start_time = time.time()
                start_query_count = len(connection.queries) if settings.DEBUG else 0
                
                try:
                    # 执行函数
                    result = func(*args, **kwargs)
                    
                    # 计算性能指标
                    duration_ms = (time.time() - start_time) * 1000
                    query_count = len(connection.queries) - start_query_count if settings.DEBUG else 0
                    
                    # 记录性能日志
                    PerformanceMonitor._log_performance(
                        endpoint=endpoint,
                        duration_ms=duration_ms,
                        query_count=query_count,
                        success=True
                    )
                    
                    # 检查性能问题
                    PerformanceMonitor._check_performance_issues(
                        endpoint=endpoint,
                        duration_ms=duration_ms,
                        query_count=query_count
                    )
                    
                    return result
                    
                except Exception as e:
                    # 记录失败的性能日志
                    duration_ms = (time.time() - start_time) * 1000
                    query_count = len(connection.queries) - start_query_count if settings.DEBUG else 0
                    
                    PerformanceMonitor._log_performance(
                        endpoint=endpoint,
                        duration_ms=duration_ms,
                        query_count=query_count,
                        success=False,
                        error=str(e)
                    )
                    
                    raise
            
            return wrapper
        return decorator
    
    @staticmethod
    @contextmanager
    def monitor_operation(operation_name: str):
        """
        操作性能监控上下文管理器
        
        监控任意操作的性能
        
        Args:
            operation_name: 操作名称
            
        Usage:
            with monitor_operation("fetch_external_data"):
                data = fetch_data()
        """
        # 重置查询计数
        if settings.DEBUG:
            reset_queries()
        
        # 记录开始时间
        start_time = time.time()
        start_query_count = len(connection.queries) if settings.DEBUG else 0
        
        try:
            yield
            
            # 计算性能指标
            duration_ms = (time.time() - start_time) * 1000
            query_count = len(connection.queries) - start_query_count if settings.DEBUG else 0
            
            # 记录性能日志
            PerformanceMonitor._log_performance(
                endpoint=operation_name,
                duration_ms=duration_ms,
                query_count=query_count,
                success=True
            )
            
            # 检查性能问题
            PerformanceMonitor._check_performance_issues(
                endpoint=operation_name,
                duration_ms=duration_ms,
                query_count=query_count
            )
            
        except Exception as e:
            # 记录失败的性能日志
            duration_ms = (time.time() - start_time) * 1000
            query_count = len(connection.queries) - start_query_count if settings.DEBUG else 0
            
            PerformanceMonitor._log_performance(
                endpoint=operation_name,
                duration_ms=duration_ms,
                query_count=query_count,
                success=False,
                error=str(e)
            )
            
            raise
    
    @staticmethod
    def _log_performance(
        endpoint: str,
        duration_ms: float,
        query_count: int,
        success: bool,
        error: Optional[str] = None
    ) -> None:
        """
        记录性能日志
        
        Args:
            endpoint: 端点名称
            duration_ms: 响应时间（毫秒）
            query_count: 查询次数
            success: 是否成功
            error: 错误信息（可选）
        """
        log_data = {
            "endpoint": endpoint,
            "duration_ms": round(duration_ms, 2),
            "query_count": query_count,
            "success": success,
            "metric_type": "performance"
        }
        
        if error:
            log_data["error"] = error
        
        # 根据性能情况选择日志级别
        if not success:
            logger.error(f"API 执行失败: {endpoint}", extra=log_data)
        elif duration_ms > PerformanceMonitor.SLOW_API_THRESHOLD_MS:
            logger.warning(f"慢 API 检测: {endpoint}", extra=log_data)
        else:
            logger.info(f"API 执行完成: {endpoint}", extra=log_data)
    
    @staticmethod
    def _check_performance_issues(
        endpoint: str,
        duration_ms: float,
        query_count: int
    ) -> None:
        """
        检查性能问题
        
        Args:
            endpoint: 端点名称
            duration_ms: 响应时间（毫秒）
            query_count: 查询次数
        """
        issues = []
        
        # 检查响应时间
        if duration_ms > PerformanceMonitor.SLOW_API_THRESHOLD_MS:
            issues.append(
                f"响应时间过长: {duration_ms:.2f}ms "
                f"(阈值: {PerformanceMonitor.SLOW_API_THRESHOLD_MS}ms)"
            )
        
        # 检查查询次数
        if query_count > PerformanceMonitor.MAX_QUERY_COUNT:
            issues.append(
                f"查询次数过多: {query_count} 次 "
                f"(阈值: {PerformanceMonitor.MAX_QUERY_COUNT} 次，可能存在 N+1 查询问题)"
            )
        
        # 记录性能问题
        if issues:
            logger.warning(
                f"性能问题检测: {endpoint}",
                extra={
                    "endpoint": endpoint,
                    "issues": issues,
                    "duration_ms": round(duration_ms, 2),
                    "query_count": query_count
                }
            )
    
    @staticmethod
    def get_query_details() -> list:
        """
        获取查询详情（仅在 DEBUG 模式下可用）
        
        Returns:
            查询详情列表
        """
        if not settings.DEBUG:
            return []
        
        queries = []
        for query in connection.queries:
            queries.append({
                "sql": query["sql"],
                "time": float(query["time"]) * 1000,  # 转换为毫秒
            })
        
        return queries
    
    @staticmethod
    def analyze_queries() -> Dict[str, Any]:
        """
        分析查询性能（仅在 DEBUG 模式下可用）
        
        Returns:
            查询分析结果
        """
        if not settings.DEBUG:
            return {
                "total_queries": 0,
                "total_time_ms": 0,
                "slow_queries": [],
                "message": "查询分析仅在 DEBUG 模式下可用"
            }
        
        queries = connection.queries
        total_time = sum(float(q["time"]) for q in queries)
        
        # 找出慢查询
        slow_queries = [
            {
                "sql": q["sql"],
                "time_ms": float(q["time"]) * 1000
            }
            for q in queries
            if float(q["time"]) * 1000 > PerformanceMonitor.SLOW_QUERY_THRESHOLD_MS
        ]
        
        return {
            "total_queries": len(queries),
            "total_time_ms": round(total_time * 1000, 2),
            "average_time_ms": round(total_time * 1000 / len(queries), 2) if queries else 0,
            "slow_queries": slow_queries,
            "slow_query_count": len(slow_queries)
        }


# 便捷函数
def monitor_api(endpoint: str):
    """
    API 性能监控装饰器（便捷函数）
    
    Args:
        endpoint: API 端点名称
    """
    return PerformanceMonitor.monitor_api(endpoint)


def monitor_operation(operation_name: str):
    """
    操作性能监控上下文管理器（便捷函数）
    
    Args:
        operation_name: 操作名称
    """
    return PerformanceMonitor.monitor_operation(operation_name)
