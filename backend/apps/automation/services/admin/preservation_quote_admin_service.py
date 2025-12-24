"""
财产保全询价 Admin Service
负责处理财产保全询价的复杂管理逻辑
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List
from decimal import Decimal
from django.db import transaction
from django.db.models import Count, Q, Avg, Min, Max
from django.utils import timezone

from apps.core.exceptions import ValidationException, BusinessException, NotFoundError
from apps.core.interfaces import ServiceLocator
from ...models import PreservationQuote, InsuranceQuote, QuoteStatus, QuoteItemStatus


class PreservationQuoteAdminService:
    """
    财产保全询价管理服务
    
    负责处理Admin层的复杂业务逻辑：
    - 执行询价任务
    - 重试失败的询价
    - 询价统计分析
    - 批量操作管理
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    @property
    def preservation_quote_service(self):
        """延迟加载财产保全询价服务"""
        if not hasattr(self, '_preservation_quote_service'):
            self._preservation_quote_service = ServiceLocator.get_preservation_quote_service()
        return self._preservation_quote_service
    
    async def execute_quotes(self, quote_ids: List[int]) -> Dict[str, Any]:
        """
        批量执行询价任务
        
        Args:
            quote_ids: 询价任务ID列表
            
        Returns:
            Dict[str, Any]: 执行结果统计
            
        Raises:
            ValidationException: 参数验证失败
            BusinessException: 执行失败
        """
        if not quote_ids:
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.no_quotes_selected()
        
        try:
            # 获取可执行的任务
            executable_quotes = PreservationQuote.objects.filter(
                id__in=quote_ids,
                status__in=[QuoteStatus.PENDING, QuoteStatus.FAILED]
            )
            
            if not executable_quotes.exists():
                from apps.core.exceptions import AutomationExceptions
                raise AutomationExceptions.no_executable_quotes()
            
            success_count = 0
            error_count = 0
            errors = []
            
            self.logger.info(
                "开始批量执行询价任务",
                extra={
                    "action": "execute_quotes",
                    "quote_count": executable_quotes.count(),
                    "quote_ids": quote_ids
                }
            )
            
            # 逐个执行询价任务
            for quote in executable_quotes:
                try:
                    # 调用询价服务执行任务
                    result = await self.preservation_quote_service.execute_quote(quote.id)
                    success_count += 1
                    
                    self.logger.info(
                        "询价任务执行成功",
                        extra={
                            "action": "execute_quotes",
                            "quote_id": quote.id,
                            "result": result
                        }
                    )
                    
                except Exception as e:
                    error_count += 1
                    error_msg = str(e)
                    errors.append({
                        'quote_id': quote.id,
                        'error': error_msg
                    })
                    
                    self.logger.error(
                        "询价任务执行失败",
                        extra={
                            "action": "execute_quotes",
                            "quote_id": quote.id,
                            "error": error_msg
                        },
                        exc_info=True
                    )
            
            result = {
                'total_requested': len(quote_ids),
                'executable_count': executable_quotes.count(),
                'success_count': success_count,
                'error_count': error_count,
                'errors': errors
            }
            
            self.logger.info(
                "批量执行询价任务完成",
                extra={
                    "action": "execute_quotes",
                    "result": result
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "批量执行询价任务失败",
                extra={
                    "action": "execute_quotes",
                    "quote_ids": quote_ids,
                    "error": str(e)
                },
                exc_info=True
            )
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.execute_quotes_failed()
    
    @transaction.atomic
    def retry_failed_quotes(self, quote_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        重试失败的询价任务
        
        Args:
            quote_ids: 可选的询价任务ID列表，如果不提供则重试所有失败的任务
            
        Returns:
            Dict[str, Any]: 重试结果
            
        Raises:
            BusinessException: 重试失败
        """
        try:
            # 构建查询条件
            query = Q(status__in=[QuoteStatus.FAILED, QuoteStatus.PARTIAL_SUCCESS])
            if quote_ids:
                query &= Q(id__in=quote_ids)
            
            failed_quotes = PreservationQuote.objects.filter(query)
            
            if not failed_quotes.exists():
                return {
                    'retried_count': 0,
                    'message': '没有找到需要重试的询价任务'
                }
            
            # 重置任务状态
            retried_count = 0
            for quote in failed_quotes:
                # 删除旧的报价记录
                quote.quotes.all().delete()
                
                # 重置任务状态
                quote.status = QuoteStatus.PENDING
                quote.error_message = None
                quote.started_at = None
                quote.finished_at = None
                quote.total_companies = 0
                quote.success_count = 0
                quote.failed_count = 0
                quote.save()
                
                retried_count += 1
            
            result = {
                'retried_count': retried_count,
                'message': f'已重置 {retried_count} 个失败的询价任务'
            }
            
            self.logger.info(
                "重试失败询价任务完成",
                extra={
                    "action": "retry_failed_quotes",
                    "retried_count": retried_count,
                    "quote_ids": quote_ids
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "重试失败询价任务失败",
                extra={
                    "action": "retry_failed_quotes",
                    "quote_ids": quote_ids,
                    "error": str(e)
                },
                exc_info=True
            )
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.retry_failed_quotes_failed()
    
    def get_quote_statistics(self, queryset=None) -> Dict[str, Any]:
        """
        获取询价统计数据
        
        Args:
            queryset: 可选的查询集，如果不提供则统计所有询价任务
            
        Returns:
            Dict[str, Any]: 统计数据
            
        Raises:
            BusinessException: 统计失败
        """
        try:
            if queryset is None:
                queryset = PreservationQuote.objects.all()
            
            # 基础统计
            total_quotes = queryset.count()
            
            # 按状态统计
            status_stats = {}
            for status_choice in QuoteStatus.choices:
                status_code = status_choice[0]
                status_name = status_choice[1]
                count = queryset.filter(status=status_code).count()
                status_stats[status_code] = {
                    'name': status_name,
                    'count': count,
                    'percentage': (count / total_quotes * 100) if total_quotes > 0 else 0
                }
            
            # 成功率统计
            success_quotes = queryset.filter(status=QuoteStatus.SUCCESS)
            success_rate = (success_quotes.count() / total_quotes * 100) if total_quotes > 0 else 0
            
            # 保全金额统计
            amount_stats = queryset.aggregate(
                total_amount=Count('preserve_amount'),
                min_amount=Min('preserve_amount'),
                max_amount=Max('preserve_amount'),
                avg_amount=Avg('preserve_amount')
            )
            
            # 按保全金额范围统计
            amount_ranges = [
                (0, 10000, '1万以下'),
                (10000, 100000, '1-10万'),
                (100000, 1000000, '10-100万'),
                (1000000, 10000000, '100-1000万'),
                (10000000, float('inf'), '1000万以上')
            ]
            
            amount_range_stats = []
            for min_val, max_val, label in amount_ranges:
                if max_val == float('inf'):
                    count = queryset.filter(preserve_amount__gte=min_val).count()
                else:
                    count = queryset.filter(
                        preserve_amount__gte=min_val,
                        preserve_amount__lt=max_val
                    ).count()
                
                amount_range_stats.append({
                    'range': label,
                    'count': count,
                    'percentage': (count / total_quotes * 100) if total_quotes > 0 else 0
                })
            
            # 保险公司统计
            insurance_stats = list(
                InsuranceQuote.objects.filter(
                    preservation_quote__in=queryset
                ).values('company_name').annotate(
                    total_quotes=Count('id'),
                    success_quotes=Count('id', filter=Q(status=QuoteItemStatus.SUCCESS)),
                    avg_premium=Avg('min_amount', filter=Q(status=QuoteItemStatus.SUCCESS))
                ).order_by('-total_quotes')[:20]  # 只显示前20个保险公司
            )
            
            # 按日期统计（最近30天）
            now = timezone.now()
            date_stats = []
            for i in range(30):
                date = (now - timezone.timedelta(days=i)).date()
                day_count = queryset.filter(created_at__date=date).count()
                day_success = queryset.filter(
                    created_at__date=date,
                    status=QuoteStatus.SUCCESS
                ).count()
                
                date_stats.append({
                    'date': date.strftime('%m-%d'),
                    'total': day_count,
                    'success': day_success
                })
            
            date_stats.reverse()  # 按时间正序
            
            # 执行时长统计
            duration_stats = []
            completed_quotes = queryset.filter(
                started_at__isnull=False,
                finished_at__isnull=False
            )
            
            for quote in completed_quotes:
                duration = (quote.finished_at - quote.started_at).total_seconds()
                duration_stats.append(duration)
            
            avg_duration = sum(duration_stats) / len(duration_stats) if duration_stats else 0
            
            result = {
                'total_quotes': total_quotes,
                'status_stats': status_stats,
                'success_rate': success_rate,
                'amount_stats': amount_stats,
                'amount_range_stats': amount_range_stats,
                'insurance_stats': insurance_stats,
                'date_stats': date_stats,
                'avg_duration': avg_duration
            }
            
            self.logger.info(
                "获取询价统计数据完成",
                extra={
                    "action": "get_quote_statistics",
                    "total_quotes": total_quotes,
                    "success_rate": success_rate
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "获取询价统计数据失败",
                extra={
                    "action": "get_quote_statistics",
                    "error": str(e)
                },
                exc_info=True
            )
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.get_quote_stats_failed()
    
    @transaction.atomic
    def batch_create_quotes(self, quote_configs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        批量创建询价任务
        
        Args:
            quote_configs: 询价配置列表，每个配置包含preserve_amount等字段
            
        Returns:
            Dict[str, Any]: 创建结果
            
        Raises:
            ValidationException: 参数验证失败
            BusinessException: 创建失败
        """
        if not quote_configs:
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.no_quote_configs()
        
        try:
            created_quotes = []
            errors = []
            
            for i, config in enumerate(quote_configs):
                try:
                    # 验证必需字段
                    if 'preserve_amount' not in config:
                        from apps.core.exceptions import AutomationExceptions
                        raise AutomationExceptions.missing_preserve_amount()
                    
                    preserve_amount = Decimal(str(config['preserve_amount']))
                    if preserve_amount <= 0:
                        raise ValidationException(
                            message="保全金额必须大于0",
                            code="INVALID_PRESERVE_AMOUNT",
                            errors={"preserve_amount": preserve_amount}
                        )
                    
                    # 创建询价任务
                    quote = PreservationQuote.objects.create(
                        preserve_amount=preserve_amount,
                        corp_id=config.get('corp_id', '2550'),
                        category_id=config.get('category_id', '127000'),
                        credential_id=config.get('credential_id')
                    )
                    
                    created_quotes.append(quote)
                    
                except Exception as e:
                    errors.append({
                        'config_index': i,
                        'config': config,
                        'error': str(e)
                    })
            
            result = {
                'created_count': len(created_quotes),
                'error_count': len(errors),
                'created_quote_ids': [q.id for q in created_quotes],
                'errors': errors
            }
            
            self.logger.info(
                "批量创建询价任务完成",
                extra={
                    "action": "batch_create_quotes",
                    "result": result
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "批量创建询价任务失败",
                extra={
                    "action": "batch_create_quotes",
                    "error": str(e)
                },
                exc_info=True
            )
            raise BusinessException(
                message="批量创建询价任务失败",
                code="BATCH_CREATE_QUOTES_FAILED",
                errors={"error": str(e)}
            )
    
    def run_single_quote(self, quote_id: int) -> Dict[str, Any]:
        """
        运行单个询价任务
        
        Args:
            quote_id: 询价任务ID
            
        Returns:
            Dict[str, Any]: 运行结果
            
        Raises:
            NotFoundError: 询价任务不存在
            ValidationException: 任务状态不允许执行
        """
        try:
            from django_q.tasks import async_task
            
            quote = PreservationQuote.objects.get(id=quote_id)
            
            # 检查状态
            if quote.status not in [QuoteStatus.PENDING, QuoteStatus.FAILED]:
                raise ValidationException(
                    message=f"任务当前状态为 {quote.get_status_display()}，无法执行",
                    code="INVALID_QUOTE_STATUS",
                    errors={"status": quote.status}
                )
            
            # 提交到 Django Q 异步任务队列
            task_id = async_task(
                'apps.automation.tasks.execute_preservation_quote_task',
                quote_id,
                task_name=f'询价任务 #{quote_id}',
                timeout=600,  # 10分钟超时
            )
            
            return {
                'success': True,
                'message': f"✅ 任务 #{quote_id} 已提交到队列，Task ID: {task_id}。请确保 Django Q 正在运行。"
            }
            
        except PreservationQuote.DoesNotExist:
            raise NotFoundError(
                message="询价任务不存在",
                code="QUOTE_NOT_FOUND",
                errors={"quote_id": quote_id}
            )
    
    def get_quote_comparison(self, quote_id: int) -> Dict[str, Any]:
        """
        获取询价结果对比分析
        
        Args:
            quote_id: 询价任务ID
            
        Returns:
            Dict[str, Any]: 对比分析结果
            
        Raises:
            NotFoundError: 询价任务不存在
            BusinessException: 分析失败
        """
        try:
            # 获取询价任务
            try:
                quote = PreservationQuote.objects.get(id=quote_id)
            except PreservationQuote.DoesNotExist:
                raise NotFoundError(
                    message="询价任务不存在",
                    code="QUOTE_NOT_FOUND",
                    errors={"quote_id": quote_id}
                )
            
            # 获取所有成功的报价
            successful_quotes = quote.quotes.filter(
                status=QuoteItemStatus.SUCCESS,
                min_amount__isnull=False
            ).order_by('min_amount')
            
            if not successful_quotes.exists():
                return {
                    'quote_id': quote_id,
                    'preserve_amount': float(quote.preserve_amount),
                    'comparison_data': [],
                    'statistics': {},
                    'message': '暂无成功的报价数据'
                }
            
            # 构建对比数据
            comparison_data = []
            premiums = []
            
            for i, insurance_quote in enumerate(successful_quotes):
                premium = float(insurance_quote.min_amount)
                premiums.append(premium)
                
                # 计算费率
                rate = premium / float(quote.preserve_amount) * 100
                
                comparison_data.append({
                    'rank': i + 1,
                    'company_name': insurance_quote.company_name,
                    'premium': premium,
                    'rate': rate,
                    'max_apply_amount': float(insurance_quote.max_apply_amount) if insurance_quote.max_apply_amount else None,
                    'is_best': i == 0  # 第一个是最优报价
                })
            
            # 统计分析
            statistics = {
                'total_companies': len(comparison_data),
                'min_premium': min(premiums),
                'max_premium': max(premiums),
                'avg_premium': sum(premiums) / len(premiums),
                'price_range': max(premiums) - min(premiums),
                'savings_amount': max(premiums) - min(premiums),
                'savings_percentage': ((max(premiums) - min(premiums)) / max(premiums) * 100) if max(premiums) > 0 else 0
            }
            
            result = {
                'quote_id': quote_id,
                'preserve_amount': float(quote.preserve_amount),
                'comparison_data': comparison_data,
                'statistics': statistics
            }
            
            self.logger.info(
                "获取询价对比分析完成",
                extra={
                    "action": "get_quote_comparison",
                    "quote_id": quote_id,
                    "successful_quotes": len(comparison_data)
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "获取询价对比分析失败",
                extra={
                    "action": "get_quote_comparison",
                    "quote_id": quote_id,
                    "error": str(e)
                },
                exc_info=True
            )
            raise BusinessException(
                message="获取询价对比分析失败",
                code="GET_QUOTE_COMPARISON_FAILED",
                errors={"error": str(e)}
            )