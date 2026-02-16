"""
中间件模块

提供性能监控中间件
"""
import time
import logging
from django.db import connection, reset_queries
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("apps.core.middleware")


class PerformanceMonitoringMiddleware(MiddlewareMixin):
    """
    性能监控中间件
    
    自动监控所有 API 请求的响应时间和数据库查询次数
    """
    
    # 性能阈值配置
    SLOW_API_THRESHOLD_MS = 1000  # API 响应时间阈值（毫秒）
    MAX_QUERY_COUNT = 10  # 最大查询次数阈值
    
    def process_request(self, request):
        """请求开始时执行"""
        # 记录开始时间
        request._performance_start_time = time.time()
        
        # 重置查询计数（仅在 DEBUG 模式下）
        if settings.DEBUG:
            reset_queries()
            request._performance_start_query_count = 0
        
        return None
    
    def process_response(self, request, response):
        """响应返回时执行"""
        # 计算响应时间
        if hasattr(request, '_performance_start_time'):
            duration_ms = (time.time() - request._performance_start_time) * 1000
            
            # 计算查询次数
            query_count = 0
            if settings.DEBUG:
                query_count = len(connection.queries)
            
            # 记录性能日志
            self._log_performance(
                request=request,
                response=response,
                duration_ms=duration_ms,
                query_count=query_count
            )
            
            # 检查性能问题
            self._check_performance_issues(
                request=request,
                duration_ms=duration_ms,
                query_count=query_count
            )
            
            # 添加性能头（可选，用于调试）
            if settings.DEBUG:
                response['X-Response-Time'] = f"{duration_ms:.2f}ms"
                response['X-Query-Count'] = str(query_count)
        
        return response
    
    def _log_performance(self, request, response, duration_ms: float, query_count: int):
        """
        记录性能日志
        
        Args:
            request: Django 请求对象
            response: Django 响应对象
            duration_ms: 响应时间（毫秒）
            query_count: 查询次数
        """
        log_data = {
            "method": request.method,
            "path": request.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "query_count": query_count,
            "metric_type": "api_performance"
        }
        
        # 添加用户信息（如果已认证）
        if hasattr(request, 'auth') and request.auth:
            log_data["user_id"] = getattr(request.auth, 'id', None)
        
        # 根据性能情况选择日志级别
        if response.status_code >= 500:
            logger.error(f"API 错误: {request.method} {request.path}", extra=log_data)
        elif duration_ms > self.SLOW_API_THRESHOLD_MS:
            logger.warning(f"慢 API: {request.method} {request.path}", extra=log_data)
        elif response.status_code >= 400:
            logger.info(f"API 客户端错误: {request.method} {request.path}", extra=log_data)
        else:
            logger.info(f"API 请求: {request.method} {request.path}", extra=log_data)
    
    def _check_performance_issues(self, request, duration_ms: float, query_count: int):
        """
        检查性能问题
        
        Args:
            request: Django 请求对象
            duration_ms: 响应时间（毫秒）
            query_count: 查询次数
        """
        issues = []
        
        # 检查响应时间
        if duration_ms > self.SLOW_API_THRESHOLD_MS:
            issues.append(
                f"响应时间过长: {duration_ms:.2f}ms "
                f"(阈值: {self.SLOW_API_THRESHOLD_MS}ms)"
            )
        
        # 检查查询次数
        if query_count > self.MAX_QUERY_COUNT:
            issues.append(
                f"查询次数过多: {query_count} 次 "
                f"(阈值: {self.MAX_QUERY_COUNT} 次，可能存在 N+1 查询问题)"
            )
        
        # 记录性能问题
        if issues:
            logger.warning(
                f"性能问题: {request.method} {request.path}",
                extra={
                    "method": request.method,
                    "path": request.path,
                    "issues": issues,
                    "duration_ms": round(duration_ms, 2),
                    "query_count": query_count
                }
            )
            
            # 在 DEBUG 模式下，记录查询详情
            if settings.DEBUG and query_count > 0:
                self._log_query_details()
    
    def _log_query_details(self):
        """记录查询详情（仅在 DEBUG 模式下）"""
        if not settings.DEBUG:
            return
        
        queries = connection.queries
        if not queries:
            return
        
        # 统计查询信息
        total_time = sum(float(q["time"]) for q in queries)
        
        # 找出慢查询
        slow_queries = [
            {
                "sql": q["sql"][:200],  # 截断长 SQL
                "time_ms": float(q["time"]) * 1000
            }
            for q in queries
            if float(q["time"]) * 1000 > 100  # 慢查询阈值 100ms
        ]
        
        logger.debug(
            "查询详情",
            extra={
                "total_queries": len(queries),
                "total_time_ms": round(total_time * 1000, 2),
                "slow_queries": slow_queries
            }
        )
