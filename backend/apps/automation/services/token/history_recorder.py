"""
Token获取历史记录服务

负责将Token获取过程记录到数据库，用于统计分析。
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from django.utils import timezone
from asgiref.sync import sync_to_async

from apps.automation.models import TokenAcquisitionHistory, TokenAcquisitionStatus
from apps.core.interfaces import LoginAttemptResult, TokenAcquisitionResult

logger = logging.getLogger(__name__)


class TokenHistoryRecorder:
    """
    Token获取历史记录器
    
    功能：
    1. 记录Token获取历史
    2. 统计分析支持
    3. 性能数据持久化
    """
    
    def __init__(self, db_service=None):
        """
        初始化历史记录器
        
        Args:
            db_service: 数据库服务（可选，支持依赖注入）
        """
        self._db_service = db_service
    
    @property
    def db_service(self):
        """延迟加载数据库服务"""
        if self._db_service is None:
            # 使用Django ORM作为默认数据库服务
            from django.db import models
            self._db_service = models
        return self._db_service
    
    async def record_acquisition_history(
        self,
        acquisition_id: str,
        site_name: str,
        account: str,
        credential_id: Optional[int],
        result: TokenAcquisitionResult,
        trigger_reason: str = "token_needed"
    ) -> None:
        """
        记录Token获取历史
        
        Args:
            acquisition_id: 获取流程ID
            site_name: 网站名称
            account: 使用账号
            credential_id: 凭证ID
            result: 获取结果
            trigger_reason: 触发原因
        """
        try:
            # 确定状态
            if result.success:
                status = TokenAcquisitionStatus.SUCCESS
            else:
                error_type = result.error_details.get('error_type', '') if result.error_details else ''
                if 'timeout' in error_type.lower():
                    status = TokenAcquisitionStatus.TIMEOUT
                elif 'network' in error_type.lower():
                    status = TokenAcquisitionStatus.NETWORK_ERROR
                elif 'captcha' in error_type.lower():
                    status = TokenAcquisitionStatus.CAPTCHA_ERROR
                elif 'credential' in error_type.lower():
                    status = TokenAcquisitionStatus.CREDENTIAL_ERROR
                else:
                    status = TokenAcquisitionStatus.FAILED
            
            # 计算统计信息
            attempt_count = len(result.login_attempts)
            login_duration = None
            captcha_attempts = 0
            network_retries = 0
            
            if result.login_attempts:
                # 使用第一次尝试的登录耗时
                login_duration = result.login_attempts[0].attempt_duration
                
                # 统计重试次数（简化处理）
                for attempt in result.login_attempts:
                    if not attempt.success:
                        if 'captcha' in (attempt.error_message or '').lower():
                            captcha_attempts += 1
                        elif 'network' in (attempt.error_message or '').lower():
                            network_retries += 1
            
            # Token预览（前50个字符）
            token_preview = None
            if result.success and result.token:
                token_preview = result.token[:50]
            
            # 错误信息
            error_message = None
            if not result.success and result.error_details:
                error_message = result.error_details.get('message', '未知错误')
            
            # 创建历史记录
            @sync_to_async
            def create_history():
                return TokenAcquisitionHistory.objects.create(
                    site_name=site_name,
                    account=account,
                    credential_id=credential_id,
                    status=status,
                    trigger_reason=trigger_reason,
                    attempt_count=attempt_count,
                    total_duration=result.total_duration,
                    login_duration=login_duration,
                    captcha_attempts=captcha_attempts,
                    network_retries=network_retries,
                    token_preview=token_preview,
                    error_message=error_message,
                    error_details=result.error_details,
                    started_at=timezone.now() - timezone.timedelta(seconds=result.total_duration),
                    finished_at=timezone.now()
                )
            
            history = await create_history()
            
            logger.info(f"Token获取历史已记录", extra={
                'acquisition_id': acquisition_id,
                'history_id': history.id,
                'site_name': site_name,
                'account': account,
                'status': status,
                'duration': result.total_duration
            })
            
        except Exception as e:
            logger.error(f"记录Token获取历史失败: {e}", extra={
                'acquisition_id': acquisition_id,
                'site_name': site_name,
                'account': account
            }, exc_info=True)
    
    async def get_recent_statistics(
        self,
        site_name: Optional[str] = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        获取最近的统计信息
        
        Args:
            site_name: 网站名称过滤
            hours: 统计小时数
            
        Returns:
            统计信息字典
        """
        try:
            from django.db.models import Count, Avg, Q
            
            # 计算时间范围
            start_time = timezone.now() - timezone.timedelta(hours=hours)
            
            @sync_to_async
            def get_stats():
                queryset = TokenAcquisitionHistory.objects.filter(
                    created_at__gte=start_time
                )
                
                if site_name:
                    queryset = queryset.filter(site_name=site_name)
                
                # 基础统计
                total_count = queryset.count()
                success_count = queryset.filter(status=TokenAcquisitionStatus.SUCCESS).count()
                
                # 按状态分组
                status_stats = queryset.values('status').annotate(
                    count=Count('id')
                ).order_by('-count')
                
                # 平均耗时
                avg_duration = queryset.aggregate(Avg('total_duration'))['total_duration__avg'] or 0
                avg_login_duration = queryset.aggregate(Avg('login_duration'))['login_duration__avg'] or 0
                
                return {
                    'total_acquisitions': total_count,
                    'successful_acquisitions': success_count,
                    'failed_acquisitions': total_count - success_count,
                    'success_rate': (success_count / total_count * 100) if total_count > 0 else 0,
                    'avg_duration': avg_duration,
                    'avg_login_duration': avg_login_duration,
                    'status_breakdown': list(status_stats),
                    'period_hours': hours
                }
            
            return await get_stats()
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}", exc_info=True)
            return {
                'total_acquisitions': 0,
                'successful_acquisitions': 0,
                'failed_acquisitions': 0,
                'success_rate': 0,
                'avg_duration': 0,
                'avg_login_duration': 0,
                'status_breakdown': [],
                'period_hours': hours
            }
    
    async def cleanup_old_records(self, days: int = 30) -> int:
        """
        清理旧的历史记录
        
        Args:
            days: 保留天数
            
        Returns:
            删除的记录数
        """
        try:
            cutoff_date = timezone.now() - timezone.timedelta(days=days)
            
            @sync_to_async
            def delete_old_records():
                deleted_count, _ = TokenAcquisitionHistory.objects.filter(
                    created_at__lt=cutoff_date
                ).delete()
                return deleted_count
            
            deleted_count = await delete_old_records()
            
            logger.info(f"清理了 {deleted_count} 条历史记录", extra={
                'cutoff_date': cutoff_date.isoformat(),
                'retention_days': days
            })
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"清理历史记录失败: {e}", exc_info=True)
            return 0
    
    async def get_account_performance(
        self,
        account: str,
        site_name: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        获取特定账号的性能表现
        
        Args:
            account: 账号名称
            site_name: 网站名称
            days: 统计天数
            
        Returns:
            账号性能数据
        """
        try:
            from django.db.models import Count, Avg
            
            start_time = timezone.now() - timezone.timedelta(days=days)
            
            @sync_to_async
            def get_account_stats():
                queryset = TokenAcquisitionHistory.objects.filter(
                    account=account,
                    site_name=site_name,
                    created_at__gte=start_time
                )
                
                total_count = queryset.count()
                success_count = queryset.filter(status=TokenAcquisitionStatus.SUCCESS).count()
                
                # 平均耗时
                avg_duration = queryset.aggregate(Avg('total_duration'))['total_duration__avg'] or 0
                avg_login_duration = queryset.aggregate(Avg('login_duration'))['login_duration__avg'] or 0
                
                # 最近一次成功时间
                last_success = queryset.filter(
                    status=TokenAcquisitionStatus.SUCCESS
                ).order_by('-created_at').first()
                
                return {
                    'account': account,
                    'site_name': site_name,
                    'period_days': days,
                    'total_attempts': total_count,
                    'successful_attempts': success_count,
                    'success_rate': (success_count / total_count * 100) if total_count > 0 else 0,
                    'avg_duration': avg_duration,
                    'avg_login_duration': avg_login_duration,
                    'last_success_at': last_success.created_at.isoformat() if last_success else None
                }
            
            return await get_account_stats()
            
        except Exception as e:
            logger.error(f"获取账号性能数据失败: {e}", extra={
                'account': account,
                'site_name': site_name
            }, exc_info=True)
            return {
                'account': account,
                'site_name': site_name,
                'period_days': days,
                'total_attempts': 0,
                'successful_attempts': 0,
                'success_rate': 0,
                'avg_duration': 0,
                'avg_login_duration': 0,
                'last_success_at': None
            }


# 全局实例（为了向后兼容）
history_recorder = TokenHistoryRecorder()

# 注意：推荐通过 ServiceLocator 或依赖注入获取服务实例