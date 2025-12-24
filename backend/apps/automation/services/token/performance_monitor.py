"""
Token获取性能监控服务

提供性能监控、统计报告和告警功能。
"""
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from django.core.cache import cache
from django.utils import timezone
from django.db.models import Count, Avg, Q

from apps.core.cache import CacheKeys, CacheTimeout
from apps.core.exceptions import ValidationException

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    total_acquisitions: int = 0
    successful_acquisitions: int = 0
    failed_acquisitions: int = 0
    success_rate: float = 0.0
    avg_duration: float = 0.0
    avg_login_duration: float = 0.0
    timeout_count: int = 0
    network_error_count: int = 0
    captcha_error_count: int = 0
    credential_error_count: int = 0
    concurrent_acquisitions: int = 0
    cache_hit_rate: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class AlertThresholds:
    """告警阈值配置"""
    min_success_rate: float = 80.0  # 最低成功率（%）
    max_avg_duration: float = 120.0  # 最大平均耗时（秒）
    max_timeout_rate: float = 10.0  # 最大超时率（%）
    max_concurrent_acquisitions: int = 5  # 最大并发获取数
    min_cache_hit_rate: float = 70.0  # 最低缓存命中率（%）


class PerformanceMonitor:
    """
    Token获取性能监控服务
    
    功能：
    1. 实时性能指标收集
    2. 统计报告生成
    3. 性能告警
    4. 缓存性能监控
    """
    
    def __init__(self, alert_thresholds: Optional[AlertThresholds] = None):
        """
        初始化性能监控服务
        
        Args:
            alert_thresholds: 告警阈值配置
        """
        self.alert_thresholds = alert_thresholds or AlertThresholds()
        self._cache_stats = {
            'hits': 0,
            'misses': 0,
            'total_requests': 0
        }
    
    def record_acquisition_start(self, acquisition_id: str, site_name: str, account: str) -> None:
        """
        记录Token获取开始
        
        Args:
            acquisition_id: 获取流程ID
            site_name: 网站名称
            account: 使用账号
        """
        cache_key = f"performance:acquisition:{acquisition_id}"
        cache.set(cache_key, {
            'start_time': time.time(),
            'site_name': site_name,
            'account': account,
            'status': 'running'
        }, timeout=CacheTimeout.LONG)
        
        # 更新并发计数
        self._increment_concurrent_count()
        
        logger.info(f"性能监控：Token获取开始", extra={
            'acquisition_id': acquisition_id,
            'site_name': site_name,
            'account': account
        })
    
    def record_acquisition_end(
        self, 
        acquisition_id: str, 
        success: bool, 
        duration: float,
        login_duration: Optional[float] = None,
        error_type: Optional[str] = None
    ) -> None:
        """
        记录Token获取结束
        
        Args:
            acquisition_id: 获取流程ID
            success: 是否成功
            duration: 总耗时
            login_duration: 登录耗时
            error_type: 错误类型
        """
        cache_key = f"performance:acquisition:{acquisition_id}"
        acquisition_data = cache.get(cache_key)
        
        if acquisition_data:
            acquisition_data.update({
                'end_time': time.time(),
                'success': success,
                'duration': duration,
                'login_duration': login_duration,
                'error_type': error_type,
                'status': 'completed'
            })
            cache.set(cache_key, acquisition_data, timeout=CacheTimeout.LONG)
        
        # 更新统计计数器
        self._update_counters(success, error_type)
        
        # 减少并发计数
        self._decrement_concurrent_count()
        
        logger.info(f"性能监控：Token获取结束", extra={
            'acquisition_id': acquisition_id,
            'success': success,
            'duration': duration,
            'login_duration': login_duration,
            'error_type': error_type
        })
        
        # 检查告警条件
        self._check_alerts(acquisition_id, success, duration, error_type)
    
    def record_cache_access(self, cache_key: str, hit: bool) -> None:
        """
        记录缓存访问
        
        Args:
            cache_key: 缓存键
            hit: 是否命中
        """
        self._cache_stats['total_requests'] += 1
        if hit:
            self._cache_stats['hits'] += 1
        else:
            self._cache_stats['misses'] += 1
        
        # 定期重置统计（避免内存泄漏）
        if self._cache_stats['total_requests'] % 1000 == 0:
            self._reset_cache_stats()
    
    def get_real_time_metrics(self) -> PerformanceMetrics:
        """
        获取实时性能指标
        
        Returns:
            性能指标对象
        """
        # 从缓存获取计数器
        counters = self._get_counters()
        
        # 计算成功率
        total = counters['total']
        success_rate = (counters['success'] / total * 100) if total > 0 else 0.0
        
        # 计算超时率
        timeout_rate = (counters['timeout'] / total * 100) if total > 0 else 0.0
        
        # 计算缓存命中率
        cache_total = self._cache_stats['total_requests']
        cache_hit_rate = (self._cache_stats['hits'] / cache_total * 100) if cache_total > 0 else 0.0
        
        # 获取平均耗时（从数据库查询最近的记录）
        avg_duration, avg_login_duration = self._get_average_durations()
        
        return PerformanceMetrics(
            total_acquisitions=counters['total'],
            successful_acquisitions=counters['success'],
            failed_acquisitions=counters['failed'],
            success_rate=success_rate,
            avg_duration=avg_duration,
            avg_login_duration=avg_login_duration,
            timeout_count=counters['timeout'],
            network_error_count=counters['network_error'],
            captcha_error_count=counters['captcha_error'],
            credential_error_count=counters['credential_error'],
            concurrent_acquisitions=self._get_concurrent_count(),
            cache_hit_rate=cache_hit_rate
        )
    
    def get_statistics_report(
        self, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        site_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成统计报告
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            site_name: 网站名称过滤
            
        Returns:
            统计报告字典
        """
        if not start_date:
            start_date = timezone.now() - timedelta(days=7)  # 默认最近7天
        if not end_date:
            end_date = timezone.now()
        
        # 从数据库查询历史记录
        from apps.automation.models import TokenAcquisitionHistory
        
        queryset = TokenAcquisitionHistory.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date
        )
        
        if site_name:
            queryset = queryset.filter(site_name=site_name)
        
        # 基础统计
        total_count = queryset.count()
        success_count = queryset.filter(status='success').count()
        failed_count = total_count - success_count
        
        # 按状态分组统计
        status_stats = queryset.values('status').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # 按网站分组统计
        site_stats = queryset.values('site_name').annotate(
            count=Count('id'),
            success_count=Count('id', filter=Q(status='success')),
            avg_duration=Avg('total_duration')
        ).order_by('-count')
        
        # 按账号分组统计
        account_stats = queryset.values('account').annotate(
            count=Count('id'),
            success_count=Count('id', filter=Q(status='success')),
            avg_duration=Avg('total_duration')
        ).order_by('-count')
        
        # 时间趋势（按天）
        daily_stats = queryset.extra(
            select={'day': 'date(created_at)'}
        ).values('day').annotate(
            count=Count('id'),
            success_count=Count('id', filter=Q(status='success'))
        ).order_by('day')
        
        # 性能指标
        avg_duration = queryset.aggregate(Avg('total_duration'))['total_duration__avg'] or 0
        avg_login_duration = queryset.aggregate(Avg('login_duration'))['login_duration__avg'] or 0
        
        return {
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days': (end_date - start_date).days
            },
            'summary': {
                'total_acquisitions': total_count,
                'successful_acquisitions': success_count,
                'failed_acquisitions': failed_count,
                'success_rate': (success_count / total_count * 100) if total_count > 0 else 0,
                'avg_duration': avg_duration,
                'avg_login_duration': avg_login_duration
            },
            'status_breakdown': list(status_stats),
            'site_breakdown': list(site_stats),
            'account_breakdown': list(account_stats),
            'daily_trend': list(daily_stats),
            'real_time_metrics': self.get_real_time_metrics().to_dict()
        }
    
    def check_health(self) -> Dict[str, Any]:
        """
        检查系统健康状态
        
        Returns:
            健康状态报告
        """
        metrics = self.get_real_time_metrics()
        alerts = []
        
        # 检查成功率
        if metrics.success_rate < self.alert_thresholds.min_success_rate:
            alerts.append({
                'type': 'low_success_rate',
                'message': f'成功率过低: {metrics.success_rate:.1f}% < {self.alert_thresholds.min_success_rate}%',
                'severity': 'high'
            })
        
        # 检查平均耗时
        if metrics.avg_duration > self.alert_thresholds.max_avg_duration:
            alerts.append({
                'type': 'high_duration',
                'message': f'平均耗时过长: {metrics.avg_duration:.1f}s > {self.alert_thresholds.max_avg_duration}s',
                'severity': 'medium'
            })
        
        # 检查并发数
        if metrics.concurrent_acquisitions > self.alert_thresholds.max_concurrent_acquisitions:
            alerts.append({
                'type': 'high_concurrency',
                'message': f'并发数过高: {metrics.concurrent_acquisitions} > {self.alert_thresholds.max_concurrent_acquisitions}',
                'severity': 'medium'
            })
        
        # 检查缓存命中率
        if metrics.cache_hit_rate < self.alert_thresholds.min_cache_hit_rate:
            alerts.append({
                'type': 'low_cache_hit_rate',
                'message': f'缓存命中率过低: {metrics.cache_hit_rate:.1f}% < {self.alert_thresholds.min_cache_hit_rate}%',
                'severity': 'low'
            })
        
        # 计算超时率
        timeout_rate = (metrics.timeout_count / metrics.total_acquisitions * 100) if metrics.total_acquisitions > 0 else 0
        if timeout_rate > self.alert_thresholds.max_timeout_rate:
            alerts.append({
                'type': 'high_timeout_rate',
                'message': f'超时率过高: {timeout_rate:.1f}% > {self.alert_thresholds.max_timeout_rate}%',
                'severity': 'high'
            })
        
        # 确定整体健康状态
        if any(alert['severity'] == 'high' for alert in alerts):
            health_status = 'unhealthy'
        elif any(alert['severity'] == 'medium' for alert in alerts):
            health_status = 'degraded'
        elif alerts:
            health_status = 'warning'
        else:
            health_status = 'healthy'
        
        return {
            'status': health_status,
            'timestamp': timezone.now().isoformat(),
            'metrics': metrics.to_dict(),
            'alerts': alerts,
            'thresholds': asdict(self.alert_thresholds)
        }
    
    def reset_metrics(self) -> None:
        """重置所有性能指标"""
        self._reset_counters()
        self._reset_cache_stats()
        logger.info("性能监控指标已重置")
    
    def _increment_concurrent_count(self) -> None:
        """增加并发计数"""
        cache.set('performance:concurrent_count', 
                 cache.get('performance:concurrent_count', 0) + 1,
                 timeout=CacheTimeout.LONG)
    
    def _decrement_concurrent_count(self) -> None:
        """减少并发计数"""
        current = cache.get('performance:concurrent_count', 0)
        cache.set('performance:concurrent_count', 
                 max(0, current - 1),
                 timeout=CacheTimeout.LONG)
    
    def _get_concurrent_count(self) -> int:
        """获取当前并发计数"""
        return cache.get('performance:concurrent_count', 0)
    
    def _update_counters(self, success: bool, error_type: Optional[str]) -> None:
        """更新统计计数器"""
        # 总数
        cache.set('performance:counter:total',
                 cache.get('performance:counter:total', 0) + 1,
                 timeout=CacheTimeout.DAY)
        
        # 成功/失败
        if success:
            cache.set('performance:counter:success',
                     cache.get('performance:counter:success', 0) + 1,
                     timeout=CacheTimeout.DAY)
        else:
            cache.set('performance:counter:failed',
                     cache.get('performance:counter:failed', 0) + 1,
                     timeout=CacheTimeout.DAY)
            
            # 错误类型计数
            if error_type:
                counter_key = f'performance:counter:{error_type}'
                cache.set(counter_key,
                         cache.get(counter_key, 0) + 1,
                         timeout=CacheTimeout.DAY)
    
    def _get_counters(self) -> Dict[str, int]:
        """获取所有计数器"""
        return {
            'total': cache.get('performance:counter:total', 0),
            'success': cache.get('performance:counter:success', 0),
            'failed': cache.get('performance:counter:failed', 0),
            'timeout': cache.get('performance:counter:timeout', 0),
            'network_error': cache.get('performance:counter:network_error', 0),
            'captcha_error': cache.get('performance:counter:captcha_error', 0),
            'credential_error': cache.get('performance:counter:credential_error', 0),
        }
    
    def _reset_counters(self) -> None:
        """重置所有计数器"""
        counter_keys = [
            'performance:counter:total',
            'performance:counter:success',
            'performance:counter:failed',
            'performance:counter:timeout',
            'performance:counter:network_error',
            'performance:counter:captcha_error',
            'performance:counter:credential_error',
            'performance:concurrent_count'
        ]
        cache.delete_many(counter_keys)
    
    def _reset_cache_stats(self) -> None:
        """重置缓存统计"""
        self._cache_stats = {
            'hits': 0,
            'misses': 0,
            'total_requests': 0
        }
    
    def _get_average_durations(self) -> tuple[float, float]:
        """
        从数据库获取平均耗时
        
        Returns:
            (平均总耗时, 平均登录耗时)
        """
        try:
            from apps.automation.models import TokenAcquisitionHistory
            
            # 查询最近100条记录的平均值
            recent_records = TokenAcquisitionHistory.objects.filter(
                created_at__gte=timezone.now() - timedelta(hours=24)
            ).aggregate(
                avg_total=Avg('total_duration'),
                avg_login=Avg('login_duration')
            )
            
            return (
                recent_records['avg_total'] or 0.0,
                recent_records['avg_login'] or 0.0
            )
        except Exception as e:
            logger.warning(f"获取平均耗时失败: {e}")
            return 0.0, 0.0
    
    def _check_alerts(
        self, 
        acquisition_id: str, 
        success: bool, 
        duration: float, 
        error_type: Optional[str]
    ) -> None:
        """
        检查告警条件
        
        Args:
            acquisition_id: 获取流程ID
            success: 是否成功
            duration: 耗时
            error_type: 错误类型
        """
        alerts = []
        
        # 检查耗时告警
        if duration > self.alert_thresholds.max_avg_duration:
            alerts.append({
                'type': 'high_duration',
                'message': f'Token获取耗时过长: {duration:.1f}s',
                'acquisition_id': acquisition_id
            })
        
        # 检查失败告警
        if not success and error_type:
            alerts.append({
                'type': f'acquisition_failed_{error_type}',
                'message': f'Token获取失败: {error_type}',
                'acquisition_id': acquisition_id
            })
        
        # 记录告警
        for alert in alerts:
            # 避免message字段冲突，重命名为alert_message
            alert_extra = {k: v for k, v in alert.items() if k != 'message'}
            alert_extra['alert_message'] = alert.get('message', '')
            logger.warning(f"性能告警: {alert['message']}", extra=alert_extra)


# 全局性能监控实例
performance_monitor = PerformanceMonitor()