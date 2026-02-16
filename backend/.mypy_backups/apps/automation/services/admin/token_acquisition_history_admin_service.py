"""
Token获取历史记录 Admin Service
负责处理Token获取历史记录的复杂管理逻辑
"""
import csv
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from django.http import HttpResponse
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Avg, Q

from apps.core.exceptions import ValidationException, BusinessException
from ...models import TokenAcquisitionHistory, TokenAcquisitionStatus


class TokenAcquisitionHistoryAdminService:
    """
    Token获取历史记录管理服务
    
    负责处理Admin层的复杂业务逻辑：
    - 清理旧的历史记录
    - 导出CSV文件
    - 重新分析性能数据
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    @transaction.atomic
    def cleanup_old_records(self, days: int = 30) -> int:
        """
        清理旧的历史记录
        
        Args:
            days: 保留天数，默认30天
            
        Returns:
            int: 删除的记录数量
            
        Raises:
            ValidationException: 参数验证失败
            BusinessException: 业务逻辑错误
        """
        if days <= 0:
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.invalid_days_parameter()
        
        try:
            cutoff_date = timezone.now() - timedelta(days=days)
            old_records = TokenAcquisitionHistory.objects.filter(created_at__lt=cutoff_date)
            count = old_records.count()
            
            if count > 0:
                # 记录清理操作
                self.logger.info(
                    "开始清理Token获取历史记录",
                    extra={
                        "action": "cleanup_old_records",
                        "cutoff_date": cutoff_date.isoformat(),
                        "records_to_delete": count,
                        "retention_days": days
                    }
                )
                
                old_records.delete()
                
                self.logger.info(
                    "Token获取历史记录清理完成",
                    extra={
                        "action": "cleanup_old_records",
                        "deleted_count": count,
                        "retention_days": days
                    }
                )
                
                return count
            else:
                self.logger.info(
                    "没有找到需要清理的历史记录",
                    extra={
                        "action": "cleanup_old_records",
                        "cutoff_date": cutoff_date.isoformat(),
                        "retention_days": days
                    }
                )
                return 0
                
        except Exception as e:
            self.logger.error(
                "清理历史记录失败",
                extra={
                    "action": "cleanup_old_records",
                    "error": str(e),
                    "retention_days": days
                },
                exc_info=True
            )
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.cleanup_records_failed()
    
    def export_to_csv(self, queryset) -> HttpResponse:
        """
        导出选中记录为CSV文件
        
        Args:
            queryset: Django QuerySet对象
            
        Returns:
            HttpResponse: CSV文件响应
            
        Raises:
            ValidationException: 参数验证失败
            BusinessException: 导出失败
        """
        if not queryset:
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.no_records_selected()
        
        try:
            # 创建HTTP响应
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"token_acquisition_history_{timestamp}.csv"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            # 添加BOM以支持Excel正确显示中文
            response.write('\ufeff')
            
            writer = csv.writer(response)
            
            # 写入表头
            headers = [
                'ID', '网站名称', '账号', '凭证ID', '状态', '触发原因',
                '尝试次数', '总耗时(秒)', '登录耗时(秒)', '验证码尝试', '网络重试',
                'Token预览', '错误信息', '创建时间', '开始时间', '完成时间'
            ]
            writer.writerow(headers)
            
            # 写入数据
            exported_count = 0
            for record in queryset:
                row = [
                    record.id,
                    record.site_name,
                    record.account,
                    record.credential_id or '',
                    record.get_status_display(),
                    record.trigger_reason,
                    record.attempt_count,
                    record.total_duration or '',
                    record.login_duration or '',
                    record.captcha_attempts,
                    record.network_retries,
                    record.token_preview or '',
                    record.error_message or '',
                    record.created_at.strftime('%Y-%m-%d %H:%M:%S') if record.created_at else '',
                    record.started_at.strftime('%Y-%m-%d %H:%M:%S') if record.started_at else '',
                    record.finished_at.strftime('%Y-%m-%d %H:%M:%S') if record.finished_at else '',
                ]
                writer.writerow(row)
                exported_count += 1
            
            # 记录导出操作
            self.logger.info(
                "Token获取历史记录导出完成",
                extra={
                    "action": "export_to_csv",
                    "exported_count": exported_count,
                    "export_filename": filename
                }
            )
            
            return response
            
        except Exception as e:
            self.logger.error(
                "导出CSV文件失败",
                extra={
                    "action": "export_to_csv",
                    "error": str(e)
                },
                exc_info=True
            )
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.export_csv_failed()
    
    def reanalyze_performance(self, queryset) -> Dict[str, Any]:
        """
        重新分析性能数据
        
        Args:
            queryset: Django QuerySet对象
            
        Returns:
            Dict[str, Any]: 分析结果
            
        Raises:
            ValidationException: 参数验证失败
            BusinessException: 分析失败
        """
        if not queryset:
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.no_records_selected()
        
        try:
            # 统计分析
            total_count = queryset.count()
            success_count = queryset.filter(status=TokenAcquisitionStatus.SUCCESS).count()
            
            # 计算成功率
            success_rate = (success_count / total_count) * 100 if total_count > 0 else 0
            
            # 计算平均耗时（仅成功记录）
            successful_records = queryset.filter(
                status=TokenAcquisitionStatus.SUCCESS,
                total_duration__isnull=False
            )
            
            avg_duration = 0
            if successful_records.exists():
                avg_duration_result = successful_records.aggregate(
                    avg_duration=Avg('total_duration')
                )
                avg_duration = avg_duration_result['avg_duration'] or 0
            
            # 分析错误类型
            error_stats = {}
            failed_records = queryset.exclude(status=TokenAcquisitionStatus.SUCCESS)
            for record in failed_records:
                status = record.get_status_display()
                error_stats[status] = error_stats.get(status, 0) + 1
            
            # 按网站统计
            site_stats = {}
            site_data = queryset.values('site_name').annotate(
                total=Count('id'),
                success=Count('id', filter=Q(status=TokenAcquisitionStatus.SUCCESS))
            )
            for item in site_data:
                site_name = item['site_name']
                total = item['total']
                success = item['success']
                rate = (success / total * 100) if total > 0 else 0
                site_stats[site_name] = {
                    'total': total,
                    'success': success,
                    'rate': rate
                }
            
            # 按账号统计
            account_stats = {}
            account_data = queryset.values('account').annotate(
                total=Count('id'),
                success=Count('id', filter=Q(status=TokenAcquisitionStatus.SUCCESS)),
                avg_duration=Avg('total_duration')
            )
            for item in account_data:
                account = item['account']
                total = item['total']
                success = item['success']
                rate = (success / total * 100) if total > 0 else 0
                avg_dur = item['avg_duration'] or 0
                account_stats[account] = {
                    'total': total,
                    'success': success,
                    'rate': rate,
                    'avg_duration': avg_dur
                }
            
            analysis_result = {
                'total_count': total_count,
                'success_count': success_count,
                'success_rate': success_rate,
                'avg_duration': avg_duration,
                'error_stats': error_stats,
                'site_stats': site_stats,
                'account_stats': account_stats
            }
            
            # 记录分析结果
            self.logger.info(
                "Token获取历史记录性能分析完成",
                extra={
                    "action": "reanalyze_performance",
                    "analyzed_count": total_count,
                    "success_count": success_count,
                    "success_rate": success_rate,
                    "avg_duration": avg_duration,
                    "error_stats": error_stats
                }
            )
            
            return analysis_result
            
        except Exception as e:
            self.logger.error(
                "性能数据分析失败",
                extra={
                    "action": "reanalyze_performance",
                    "error": str(e)
                },
                exc_info=True
            )
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.performance_analysis_failed()
    
    def get_dashboard_statistics(self) -> Dict[str, Any]:
        """
        获取仪表板统计数据
        
        Returns:
            Dict[str, Any]: 统计数据
        """
        try:
            # 基础统计
            total_records = TokenAcquisitionHistory.objects.count()
            success_records = TokenAcquisitionHistory.objects.filter(
                status=TokenAcquisitionStatus.SUCCESS
            ).count()
            
            success_rate = (success_records / total_records * 100) if total_records > 0 else 0
            
            # 时间范围统计
            now = timezone.now()
            time_ranges = {
                '1h': now - timedelta(hours=1),
                '24h': now - timedelta(hours=24),
                '7d': now - timedelta(days=7),
                '30d': now - timedelta(days=30),
            }
            
            time_stats = {}
            for period, start_time in time_ranges.items():
                records = TokenAcquisitionHistory.objects.filter(created_at__gte=start_time)
                success = records.filter(status=TokenAcquisitionStatus.SUCCESS).count()
                total = records.count()
                time_stats[period] = {
                    'total': total,
                    'success': success,
                    'rate': (success / total * 100) if total > 0 else 0
                }
            
            # 按状态统计
            status_stats = list(TokenAcquisitionHistory.objects.values('status').annotate(
                count=Count('id')
            ).order_by('-count'))
            
            # 按网站统计
            site_stats = list(TokenAcquisitionHistory.objects.values('site_name').annotate(
                total=Count('id'),
                success=Count('id', filter=Q(status=TokenAcquisitionStatus.SUCCESS))
            ).order_by('-total'))
            
            # 性能统计
            performance_stats = TokenAcquisitionHistory.objects.filter(
                status=TokenAcquisitionStatus.SUCCESS,
                total_duration__isnull=False
            ).aggregate(
                avg_duration=Avg('total_duration'),
                count=Count('id')
            )
            
            # 最近7天的趋势数据
            trend_data = []
            for i in range(7):
                date = (now - timedelta(days=i)).date()
                day_records = TokenAcquisitionHistory.objects.filter(
                    created_at__date=date
                )
                day_success = day_records.filter(status=TokenAcquisitionStatus.SUCCESS).count()
                day_total = day_records.count()
                
                trend_data.append({
                    'date': date.strftime('%m-%d'),
                    'total': day_total,
                    'success': day_success,
                    'rate': (day_success / day_total * 100) if day_total > 0 else 0
                })
            
            trend_data.reverse()  # 按时间正序
            
            result = {
                'total_records': total_records,
                'success_records': success_records,
                'success_rate': success_rate,
                'time_stats': time_stats,
                'status_stats': status_stats,
                'site_stats': site_stats,
                'performance_stats': performance_stats,
                'trend_data': trend_data
            }
            
            self.logger.info(
                "获取仪表板统计数据完成",
                extra={
                    "action": "get_dashboard_statistics",
                    "total_records": total_records,
                    "success_rate": success_rate
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "获取仪表板统计数据失败",
                extra={
                    "action": "get_dashboard_statistics",
                    "error": str(e)
                },
                exc_info=True
            )
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.get_dashboard_stats_failed()