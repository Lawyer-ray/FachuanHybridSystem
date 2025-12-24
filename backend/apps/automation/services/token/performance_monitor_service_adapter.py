"""
性能监控服务适配器

提供性能监控服务的统一接口实现
"""
import logging
import psutil
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from django.utils import timezone
from django.db.models import Count, Avg, Q

from apps.core.interfaces import IPerformanceMonitorService

logger = logging.getLogger("apps.automation")


class PerformanceMonitorServiceAdapter(IPerformanceMonitorService):
    """
    性能监控服务适配器
    
    实现 IPerformanceMonitorService 接口，提供系统和业务性能监控功能
    """
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """
        获取系统性能指标
        
        Returns:
            系统性能指标字典，包含CPU、内存、磁盘等信息
        """
        try:
            from apps.automation.utils.logging import AutomationLogger
            AutomationLogger.log_performance_metrics_collection_start("system")
            
            # CPU 使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            # 内存使用情况
            memory = psutil.virtual_memory()
            
            # 磁盘使用情况
            disk = psutil.disk_usage('/')
            
            # 网络IO统计
            network = psutil.net_io_counters()
            
            # 进程数量
            process_count = len(psutil.pids())
            
            # 系统负载（仅在Unix系统上可用）
            load_avg = None
            try:
                load_avg = psutil.getloadavg()
            except AttributeError:
                # Windows系统不支持getloadavg
                pass
            
            metrics = {
                "timestamp": timezone.now().isoformat(),
                "cpu": {
                    "usage_percent": cpu_percent,
                    "count": cpu_count,
                    "load_average": load_avg
                },
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "used": memory.used,
                    "usage_percent": memory.percent
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "usage_percent": (disk.used / disk.total) * 100
                },
                "network": {
                    "bytes_sent": network.bytes_sent,
                    "bytes_recv": network.bytes_recv,
                    "packets_sent": network.packets_sent,
                    "packets_recv": network.packets_recv
                },
                "processes": {
                    "count": process_count
                }
            }
            
            AutomationLogger.log_performance_metrics_collection_success(
                metric_type="system",
                metrics_count=len(metrics),
                collection_time=0.1,  # Approximate time for system metrics
                cpu_usage=cpu_percent,
                memory_usage=memory.percent
            )
            
            return metrics
            
        except Exception as e:
            logger.error(
                f"获取系统性能指标失败: {e}",
                extra={
                    "action": "get_system_metrics_failed",
                    "error": str(e)
                },
                exc_info=True
            )
            
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.system_metrics_failed(str(e))
    
    def get_token_acquisition_metrics(
        self,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        获取Token获取性能指标
        
        Args:
            hours: 统计最近多少小时的数据
            
        Returns:
            Token获取性能指标字典
        """
        try:
            logger.debug(
                "开始获取Token获取性能指标",
                extra={
                    "action": "get_token_acquisition_metrics_start",
                    "hours": hours
                }
            )
            
            # 计算时间范围
            end_time = timezone.now()
            start_time = end_time - timedelta(hours=hours)
            
            # 尝试导入TokenAcquisitionHistory模型
            try:
                from apps.automation.models import TokenAcquisitionHistory
                
                # 查询指定时间范围内的Token获取记录
                queryset = TokenAcquisitionHistory.objects.filter(
                    created_at__gte=start_time,
                    created_at__lte=end_time
                )
                
                # 统计总数
                total_attempts = queryset.count()
                
                # 统计成功和失败数量
                successful_attempts = queryset.filter(success=True).count()
                failed_attempts = queryset.filter(success=False).count()
                
                # 计算成功率
                success_rate = (successful_attempts / total_attempts * 100) if total_attempts > 0 else 0
                
                # 计算平均获取时间
                avg_duration = queryset.filter(
                    success=True,
                    total_duration__isnull=False
                ).aggregate(avg_duration=Avg('total_duration'))['avg_duration'] or 0
                
                # 按站点统计
                site_stats = {}
                for record in queryset.values('site_name').annotate(
                    count=Count('id'),
                    success_count=Count('id', filter=Q(success=True))
                ):
                    site_name = record['site_name']
                    site_stats[site_name] = {
                        "total_attempts": record['count'],
                        "successful_attempts": record['success_count'],
                        "success_rate": (record['success_count'] / record['count'] * 100) if record['count'] > 0 else 0
                    }
                
                metrics = {
                    "timestamp": timezone.now().isoformat(),
                    "time_range": {
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat(),
                        "hours": hours
                    },
                    "overall": {
                        "total_attempts": total_attempts,
                        "successful_attempts": successful_attempts,
                        "failed_attempts": failed_attempts,
                        "success_rate": round(success_rate, 2),
                        "average_duration": round(avg_duration, 2) if avg_duration else 0
                    },
                    "by_site": site_stats
                }
                
            except ImportError:
                # 如果模型不存在，返回空统计
                metrics = {
                    "timestamp": timezone.now().isoformat(),
                    "time_range": {
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat(),
                        "hours": hours
                    },
                    "overall": {
                        "total_attempts": 0,
                        "successful_attempts": 0,
                        "failed_attempts": 0,
                        "success_rate": 0,
                        "average_duration": 0
                    },
                    "by_site": {},
                    "note": "TokenAcquisitionHistory模型不可用"
                }
            
            logger.debug(
                "Token获取性能指标获取成功",
                extra={
                    "action": "get_token_acquisition_metrics_success",
                    "total_attempts": metrics["overall"]["total_attempts"],
                    "success_rate": metrics["overall"]["success_rate"]
                }
            )
            
            return metrics
            
        except Exception as e:
            logger.error(
                f"获取Token获取性能指标失败: {e}",
                extra={
                    "action": "get_token_acquisition_metrics_failed",
                    "hours": hours,
                    "error": str(e)
                },
                exc_info=True
            )
            
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.token_acquisition_metrics_failed(str(e))
    
    def get_api_performance_metrics(
        self,
        api_name: Optional[str] = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        获取API性能指标
        
        Args:
            api_name: API名称（可选，为空时返回所有API）
            hours: 统计最近多少小时的数据
            
        Returns:
            API性能指标字典
        """
        try:
            logger.debug(
                "开始获取API性能指标",
                extra={
                    "action": "get_api_performance_metrics_start",
                    "api_name": api_name,
                    "hours": hours
                }
            )
            
            # 计算时间范围
            end_time = timezone.now()
            start_time = end_time - timedelta(hours=hours)
            
            # 这里应该从日志或监控系统中获取API性能数据
            # 由于没有具体的API监控表，这里提供一个基础实现
            
            metrics = {
                "timestamp": timezone.now().isoformat(),
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "hours": hours
                },
                "api_name": api_name,
                "metrics": {
                    "total_requests": 0,
                    "successful_requests": 0,
                    "failed_requests": 0,
                    "success_rate": 0,
                    "average_response_time": 0,
                    "min_response_time": 0,
                    "max_response_time": 0
                },
                "note": "API性能监控需要集成具体的监控系统"
            }
            
            logger.debug(
                "API性能指标获取完成",
                extra={
                    "action": "get_api_performance_metrics_success",
                    "api_name": api_name
                }
            )
            
            return metrics
            
        except Exception as e:
            logger.error(
                f"获取API性能指标失败: {e}",
                extra={
                    "action": "get_api_performance_metrics_failed",
                    "api_name": api_name,
                    "hours": hours,
                    "error": str(e)
                },
                exc_info=True
            )
            
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.api_performance_metrics_failed(str(e))
    
    def record_performance_metric(
        self,
        metric_name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None
    ) -> None:
        """
        记录性能指标
        
        Args:
            metric_name: 指标名称
            value: 指标值
            tags: 标签字典（可选）
        """
        try:
            logger.info(
                "记录性能指标",
                extra={
                    "action": "record_performance_metric",
                    "metric_name": metric_name,
                    "value": value,
                    "tags": tags or {}
                }
            )
            
            # 这里应该将指标记录到监控系统中
            # 可以是数据库、时序数据库（如InfluxDB）、或监控服务（如Prometheus）
            
            # 目前只记录到日志中
            logger.info(
                f"性能指标记录: {metric_name} = {value}",
                extra={
                    "metric_name": metric_name,
                    "metric_value": value,
                    "metric_tags": tags or {},
                    "timestamp": timezone.now().isoformat()
                }
            )
            
        except Exception as e:
            logger.error(
                f"记录性能指标失败: {e}",
                extra={
                    "action": "record_performance_metric_failed",
                    "metric_name": metric_name,
                    "value": value,
                    "error": str(e)
                },
                exc_info=True
            )
            
            # 性能指标记录失败不应该影响主要业务流程，所以这里只记录日志
            pass
    
    # 内部方法版本，供其他模块调用
    def get_system_metrics_internal(self) -> Dict[str, Any]:
        """获取系统性能指标（内部接口，无权限检查）"""
        return self.get_system_metrics()
    
    def get_token_acquisition_metrics_internal(
        self,
        hours: int = 24
    ) -> Dict[str, Any]:
        """获取Token获取性能指标（内部接口，无权限检查）"""
        return self.get_token_acquisition_metrics(hours)
    
    def get_api_performance_metrics_internal(
        self,
        api_name: Optional[str] = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """获取API性能指标（内部接口，无权限检查）"""
        return self.get_api_performance_metrics(api_name, hours)
    
    def record_performance_metric_internal(
        self,
        metric_name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None
    ) -> None:
        """记录性能指标（内部接口，无权限检查）"""
        self.record_performance_metric(metric_name, value, tags)