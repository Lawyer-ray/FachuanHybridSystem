"""
法院文书 Admin Service
负责处理法院文书的复杂管理逻辑
"""
import logging
import os
from typing import Optional, Dict, Any, List
from django.db import transaction
from django.db.models import Count, Q, Sum, Avg
from django.utils import timezone
from django.http import HttpResponse
from django.conf import settings

from apps.core.exceptions import ValidationException, BusinessException, NotFoundError
from ...models import CourtDocument, DocumentDownloadStatus, ScraperTask


class CourtDocumentAdminService:
    """
    法院文书管理服务
    
    负责处理Admin层的复杂业务逻辑：
    - 批量下载文书
    - 批量删除文书
    - 文书统计分析
    - 文件管理操作
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    @transaction.atomic
    def batch_download_documents(self, document_ids: List[int]) -> Dict[str, Any]:
        """
        批量下载文书
        
        Args:
            document_ids: 文书ID列表
            
        Returns:
            Dict[str, Any]: 下载结果统计
            
        Raises:
            ValidationException: 参数验证失败
            BusinessException: 下载失败
        """
        if not document_ids:
            raise ValidationException(
                message="没有选中任何文书",
                code="NO_DOCUMENTS_SELECTED",
                errors={}
            )
        
        try:
            # 获取待下载的文书
            documents = CourtDocument.objects.filter(
                id__in=document_ids,
                download_status__in=[DocumentDownloadStatus.PENDING, DocumentDownloadStatus.FAILED]
            )
            
            if not documents.exists():
                raise ValidationException(
                    message="没有找到可下载的文书",
                    code="NO_DOWNLOADABLE_DOCUMENTS",
                    errors={"document_ids": document_ids}
                )
            
            # 更新状态为下载中
            updated_count = documents.update(
                download_status=DocumentDownloadStatus.DOWNLOADING,
                updated_at=timezone.now()
            )
            
            self.logger.info(
                "开始批量下载文书",
                extra={
                    "action": "batch_download_documents",
                    "document_count": updated_count,
                    "document_ids": document_ids
                }
            )
            
            # 这里应该触发异步下载任务
            # 实际实现中会调用下载服务
            
            result = {
                'total_requested': len(document_ids),
                'started_download': updated_count,
                'already_downloaded': len(document_ids) - updated_count
            }
            
            self.logger.info(
                "批量下载文书任务已启动",
                extra={
                    "action": "batch_download_documents",
                    "result": result
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "批量下载文书失败",
                extra={
                    "action": "batch_download_documents",
                    "document_ids": document_ids,
                    "error": str(e)
                },
                exc_info=True
            )
            raise BusinessException(
                message="批量下载文书失败",
                code="BATCH_DOWNLOAD_FAILED",
                errors={"error": str(e)}
            )
    
    @transaction.atomic
    def batch_delete_documents(self, document_ids: List[int], delete_files: bool = False) -> Dict[str, Any]:
        """
        批量删除文书记录
        
        Args:
            document_ids: 文书ID列表
            delete_files: 是否同时删除本地文件
            
        Returns:
            Dict[str, Any]: 删除结果统计
            
        Raises:
            ValidationException: 参数验证失败
            BusinessException: 删除失败
        """
        if not document_ids:
            raise ValidationException(
                message="没有选中任何文书",
                code="NO_DOCUMENTS_SELECTED",
                errors={}
            )
        
        try:
            # 获取要删除的文书
            documents = CourtDocument.objects.filter(id__in=document_ids)
            
            if not documents.exists():
                raise ValidationException(
                    message="没有找到要删除的文书",
                    code="NO_DOCUMENTS_FOUND",
                    errors={"document_ids": document_ids}
                )
            
            deleted_files_count = 0
            file_errors = []
            
            # 如果需要删除文件
            if delete_files:
                for document in documents:
                    if document.local_file_path and os.path.exists(document.local_file_path):
                        try:
                            os.remove(document.local_file_path)
                            deleted_files_count += 1
                        except Exception as e:
                            file_errors.append({
                                'document_id': document.id,
                                'file_path': document.local_file_path,
                                'error': str(e)
                            })
            
            # 删除数据库记录
            deleted_count = documents.count()
            documents.delete()
            
            result = {
                'deleted_records': deleted_count,
                'deleted_files': deleted_files_count,
                'file_errors': file_errors
            }
            
            self.logger.info(
                "批量删除文书完成",
                extra={
                    "action": "batch_delete_documents",
                    "result": result,
                    "delete_files": delete_files
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "批量删除文书失败",
                extra={
                    "action": "batch_delete_documents",
                    "document_ids": document_ids,
                    "delete_files": delete_files,
                    "error": str(e)
                },
                exc_info=True
            )
            raise BusinessException(
                message="批量删除文书失败",
                code="BATCH_DELETE_FAILED",
                errors={"error": str(e)}
            )
    
    def get_document_statistics(self, queryset=None) -> Dict[str, Any]:
        """
        获取文书统计数据
        
        Args:
            queryset: 可选的查询集，如果不提供则统计所有文书
            
        Returns:
            Dict[str, Any]: 统计数据
            
        Raises:
            BusinessException: 统计失败
        """
        try:
            if queryset is None:
                queryset = CourtDocument.objects.all()
            
            # 基础统计
            total_documents = queryset.count()
            
            # 按状态统计
            status_stats = {}
            for status_choice in DocumentDownloadStatus.choices:
                status_code = status_choice[0]
                status_name = status_choice[1]
                count = queryset.filter(download_status=status_code).count()
                status_stats[status_code] = {
                    'name': status_name,
                    'count': count,
                    'percentage': (count / total_documents * 100) if total_documents > 0 else 0
                }
            
            # 按法院统计
            court_stats = list(queryset.values('c_fymc').annotate(
                total=Count('id'),
                success=Count('id', filter=Q(download_status=DocumentDownloadStatus.SUCCESS)),
                pending=Count('id', filter=Q(download_status=DocumentDownloadStatus.PENDING)),
                failed=Count('id', filter=Q(download_status=DocumentDownloadStatus.FAILED))
            ).order_by('-total')[:20])  # 只显示前20个法院
            
            # 按文件格式统计
            format_stats = list(queryset.values('c_wjgs').annotate(
                count=Count('id')
            ).order_by('-count'))
            
            # 文件大小统计
            file_size_stats = queryset.filter(
                download_status=DocumentDownloadStatus.SUCCESS,
                file_size__isnull=False
            ).aggregate(
                total_size=Sum('file_size'),
                avg_size=Avg('file_size'),
                count=Count('id')
            )
            
            # 按日期统计（最近30天）
            now = timezone.now()
            date_stats = []
            for i in range(30):
                date = (now - timezone.timedelta(days=i)).date()
                day_count = queryset.filter(created_at__date=date).count()
                day_success = queryset.filter(
                    created_at__date=date,
                    download_status=DocumentDownloadStatus.SUCCESS
                ).count()
                
                date_stats.append({
                    'date': date.strftime('%m-%d'),
                    'total': day_count,
                    'success': day_success
                })
            
            date_stats.reverse()  # 按时间正序
            
            # 按爬虫任务统计
            task_stats = list(queryset.values('scraper_task__id', 'scraper_task__task_type').annotate(
                count=Count('id'),
                success=Count('id', filter=Q(download_status=DocumentDownloadStatus.SUCCESS))
            ).order_by('-count')[:10])  # 只显示前10个任务
            
            result = {
                'total_documents': total_documents,
                'status_stats': status_stats,
                'court_stats': court_stats,
                'format_stats': format_stats,
                'file_size_stats': file_size_stats,
                'date_stats': date_stats,
                'task_stats': task_stats
            }
            
            self.logger.info(
                "获取文书统计数据完成",
                extra={
                    "action": "get_document_statistics",
                    "total_documents": total_documents
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "获取文书统计数据失败",
                extra={
                    "action": "get_document_statistics",
                    "error": str(e)
                },
                exc_info=True
            )
            raise BusinessException(
                message="获取文书统计数据失败",
                code="GET_DOCUMENT_STATS_FAILED",
                errors={"error": str(e)}
            )
    
    @transaction.atomic
    def retry_failed_downloads(self, document_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        重试失败的下载任务
        
        Args:
            document_ids: 可选的文书ID列表，如果不提供则重试所有失败的下载
            
        Returns:
            Dict[str, Any]: 重试结果
            
        Raises:
            BusinessException: 重试失败
        """
        try:
            # 构建查询条件
            query = Q(download_status=DocumentDownloadStatus.FAILED)
            if document_ids:
                query &= Q(id__in=document_ids)
            
            failed_documents = CourtDocument.objects.filter(query)
            
            if not failed_documents.exists():
                return {
                    'retried_count': 0,
                    'message': '没有找到失败的下载任务'
                }
            
            # 重置状态为待下载
            retried_count = failed_documents.update(
                download_status=DocumentDownloadStatus.PENDING,
                error_message=None,
                updated_at=timezone.now()
            )
            
            result = {
                'retried_count': retried_count,
                'message': f'已重置 {retried_count} 个失败的下载任务'
            }
            
            self.logger.info(
                "重试失败下载任务完成",
                extra={
                    "action": "retry_failed_downloads",
                    "retried_count": retried_count,
                    "document_ids": document_ids
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "重试失败下载任务失败",
                extra={
                    "action": "retry_failed_downloads",
                    "document_ids": document_ids,
                    "error": str(e)
                },
                exc_info=True
            )
            raise BusinessException(
                message="重试失败下载任务失败",
                code="RETRY_FAILED_DOWNLOADS_FAILED",
                errors={"error": str(e)}
            )
    
    def cleanup_orphaned_files(self) -> Dict[str, Any]:
        """
        清理孤立的文件（数据库中没有记录但文件存在）
        
        Returns:
            Dict[str, Any]: 清理结果
            
        Raises:
            BusinessException: 清理失败
        """
        try:
            # 获取所有已下载文书的文件路径
            downloaded_files = set(
                CourtDocument.objects.filter(
                    download_status=DocumentDownloadStatus.SUCCESS,
                    local_file_path__isnull=False
                ).values_list('local_file_path', flat=True)
            )
            
            # 扫描文件系统中的文件
            media_root = getattr(settings, 'MEDIA_ROOT', '')
            documents_dir = os.path.join(media_root, 'court_documents')
            
            if not os.path.exists(documents_dir):
                return {
                    'orphaned_files': 0,
                    'deleted_files': 0,
                    'message': '文档目录不存在'
                }
            
            orphaned_files = []
            for root, dirs, files in os.walk(documents_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, media_root)
                    
                    if relative_path not in downloaded_files:
                        orphaned_files.append(file_path)
            
            # 删除孤立文件
            deleted_count = 0
            delete_errors = []
            
            for file_path in orphaned_files:
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except Exception as e:
                    delete_errors.append({
                        'file_path': file_path,
                        'error': str(e)
                    })
            
            result = {
                'orphaned_files': len(orphaned_files),
                'deleted_files': deleted_count,
                'delete_errors': delete_errors
            }
            
            self.logger.info(
                "清理孤立文件完成",
                extra={
                    "action": "cleanup_orphaned_files",
                    "result": result
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "清理孤立文件失败",
                extra={
                    "action": "cleanup_orphaned_files",
                    "error": str(e)
                },
                exc_info=True
            )
            raise BusinessException(
                message="清理孤立文件失败",
                code="CLEANUP_ORPHANED_FILES_FAILED",
                errors={"error": str(e)}
            )
    
    def get_download_progress(self, task_id: Optional[int] = None) -> Dict[str, Any]:
        """
        获取下载进度统计
        
        Args:
            task_id: 可选的爬虫任务ID，如果提供则只统计该任务的进度
            
        Returns:
            Dict[str, Any]: 下载进度数据
            
        Raises:
            BusinessException: 获取进度失败
        """
        try:
            # 构建查询条件
            queryset = CourtDocument.objects.all()
            if task_id:
                queryset = queryset.filter(scraper_task_id=task_id)
            
            # 统计各状态的数量
            total = queryset.count()
            pending = queryset.filter(download_status=DocumentDownloadStatus.PENDING).count()
            downloading = queryset.filter(download_status=DocumentDownloadStatus.DOWNLOADING).count()
            success = queryset.filter(download_status=DocumentDownloadStatus.SUCCESS).count()
            failed = queryset.filter(download_status=DocumentDownloadStatus.FAILED).count()
            
            # 计算进度百分比
            progress_percentage = (success / total * 100) if total > 0 else 0
            
            result = {
                'total': total,
                'pending': pending,
                'downloading': downloading,
                'success': success,
                'failed': failed,
                'progress_percentage': progress_percentage,
                'task_id': task_id
            }
            
            self.logger.info(
                "获取下载进度完成",
                extra={
                    "action": "get_download_progress",
                    "task_id": task_id,
                    "progress_percentage": progress_percentage
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "获取下载进度失败",
                extra={
                    "action": "get_download_progress",
                    "task_id": task_id,
                    "error": str(e)
                },
                exc_info=True
            )
            raise BusinessException(
                message="获取下载进度失败",
                code="GET_DOWNLOAD_PROGRESS_FAILED",
                errors={"error": str(e)}
            )