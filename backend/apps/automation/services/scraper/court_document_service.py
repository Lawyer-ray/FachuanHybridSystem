"""
法院文书服务层
处理文书记录的创建、更新和查询
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from django.db import transaction
from django.utils import timezone

from apps.automation.models import CourtDocument, ScraperTask, DocumentDownloadStatus
from apps.core.exceptions import ValidationException, NotFoundError, BusinessException
from apps.core.interfaces import ICourtDocumentService

logger = logging.getLogger("apps.automation")


class CourtDocumentService:
    """
    法院文书服务
    
    负责文书记录的业务逻辑处理
    """
    
    def __init__(self, *args, **kwargs):
        """
        初始化服务（支持依赖注入）
        
        Args:
            *args: 位置参数（保持接口兼容性）
            **kwargs: 关键字参数（保持接口兼容性）
        """
        # 目前此服务不需要特殊的依赖注入，但保持接口一致性
        pass
    
    @transaction.atomic
    def create_document_from_api_data(
        self,
        scraper_task_id: int,
        api_data: Dict[str, Any],
        case_id: Optional[int] = None
    ) -> CourtDocument:
        """
        从API数据创建文书记录
        
        Args:
            scraper_task_id: 爬虫任务ID
            api_data: API返回的文书数据
            case_id: 关联案件ID（可选）
            
        Returns:
            创建的文书记录
            
        Raises:
            ValidationException: 数据验证失败
            NotFoundError: 爬虫任务不存在
        """
        # 验证爬虫任务存在
        try:
            scraper_task = ScraperTask.objects.get(id=scraper_task_id)
        except ScraperTask.DoesNotExist:
            raise NotFoundError(
                message=f"爬虫任务不存在: {scraper_task_id}",
                code="SCRAPER_TASK_NOT_FOUND",
                errors={"scraper_task_id": scraper_task_id}
            )
        
        # 验证必需字段
        required_fields = [
            'c_sdbh', 'c_stbh', 'wjlj', 'c_wsbh',
            'c_wsmc', 'c_fybh', 'c_fymc', 'c_wjgs', 'dt_cjsj'
        ]
        
        missing_fields = [field for field in required_fields if field not in api_data]
        if missing_fields:
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.missing_required_fields(missing_fields)
        
        # 解析创建时间
        dt_cjsj = api_data['dt_cjsj']
        if isinstance(dt_cjsj, str):
            try:
                # 尝试解析 ISO 格式
                dt_cjsj = datetime.fromisoformat(dt_cjsj.replace('Z', '+00:00'))
            except ValueError:
                # 如果解析失败，使用当前时间
                logger.warning(f"无法解析时间格式: {dt_cjsj}，使用当前时间")
                dt_cjsj = timezone.now()
        
        # 创建或获取文书记录（处理唯一约束冲突）
        try:
            # 使用 c_wsbh 和 c_sdbh 作为唯一标识查找现有记录
            document, created = CourtDocument.objects.get_or_create(
                c_wsbh=api_data['c_wsbh'],
                c_sdbh=api_data['c_sdbh'],
                defaults={
                    'scraper_task': scraper_task,
                    'case_id': case_id,
                    'c_stbh': api_data['c_stbh'],
                    'wjlj': api_data['wjlj'],
                    'c_wsmc': api_data['c_wsmc'],
                    'c_fybh': api_data['c_fybh'],
                    'c_fymc': api_data['c_fymc'],
                    'c_wjgs': api_data['c_wjgs'],
                    'dt_cjsj': dt_cjsj,
                    'download_status': DocumentDownloadStatus.PENDING
                }
            )
            
            if not created:
                # 记录已存在，更新 scraper_task 关联和其他可能变化的字段
                logger.info(
                    f"文书记录已存在，更新关联: Document ID={document.id}, "
                    f"旧 Task ID={document.scraper_task_id}, 新 Task ID={scraper_task_id}"
                )
                document.scraper_task = scraper_task
                if case_id and not document.case_id:
                    document.case_id = case_id
                # 如果之前下载失败，重置状态以便重新下载
                if document.download_status == DocumentDownloadStatus.FAILED:
                    document.download_status = DocumentDownloadStatus.PENDING
                    document.error_message = None
                document.save()
            
            from apps.automation.utils.logging import AutomationLogger
            AutomationLogger.log_document_creation_success(
                document_id=document.id,
                scraper_task_id=scraper_task_id,
                c_wsbh=document.c_wsbh,
                c_wsmc=document.c_wsmc
            )
            
            return document
            
        except Exception as e:
            logger.error(
                f"创建文书记录失败: {e}",
                extra={
                    "scraper_task_id": scraper_task_id,
                    "api_data": api_data
                }
            )
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.create_document_failed(
                error_message=str(e)
            )
    
    @transaction.atomic
    def update_download_status(
        self,
        document_id: int,
        status: str,
        local_file_path: Optional[str] = None,
        file_size: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> CourtDocument:
        """
        更新文书下载状态
        
        Args:
            document_id: 文书记录ID
            status: 下载状态
            local_file_path: 本地文件路径（可选）
            file_size: 文件大小（可选）
            error_message: 错误信息（可选）
            
        Returns:
            更新后的文书记录
            
        Raises:
            NotFoundError: 文书记录不存在
            ValidationException: 状态值无效
        """
        # 验证文书记录存在
        try:
            document = CourtDocument.objects.get(id=document_id)
        except CourtDocument.DoesNotExist:
            raise NotFoundError(
                message=f"文书记录不存在: {document_id}",
                code="DOCUMENT_NOT_FOUND",
                errors={"document_id": document_id}
            )
        
        # 验证状态值
        valid_statuses = [choice[0] for choice in DocumentDownloadStatus.choices]
        if status not in valid_statuses:
            from apps.core.exceptions import AutomationExceptions
            raise AutomationExceptions.invalid_download_status(status, valid_statuses)
        
        # 记录旧状态
        old_status = document.download_status
        
        # 更新字段
        document.download_status = status
        
        if local_file_path is not None:
            document.local_file_path = local_file_path
        
        if file_size is not None:
            document.file_size = file_size
        
        if error_message is not None:
            document.error_message = error_message
        
        # 如果状态是成功，设置下载完成时间
        if status == DocumentDownloadStatus.SUCCESS:
            document.downloaded_at = timezone.now()
        
        document.save()
        
        from apps.automation.utils.logging import AutomationLogger
        AutomationLogger.log_document_status_update(
            document_id=document_id,
            old_status=old_status,
            new_status=status,
            c_wsmc=document.c_wsmc,
            local_file_path=local_file_path
        )
        
        return document
    
    def get_documents_by_task(
        self,
        scraper_task_id: int
    ) -> List[CourtDocument]:
        """
        获取任务的所有文书记录
        
        Args:
            scraper_task_id: 爬虫任务ID
            
        Returns:
            文书记录列表
        """
        documents = CourtDocument.objects.filter(
            scraper_task_id=scraper_task_id
        ).select_related('scraper_task', 'case').order_by('-created_at')
        
        return list(documents)
    
    def get_document_by_id(
        self,
        document_id: int
    ) -> Optional[CourtDocument]:
        """
        根据ID获取文书记录
        
        Args:
            document_id: 文书记录ID
            
        Returns:
            文书记录，不存在时返回 None
        """
        try:
            document = CourtDocument.objects.select_related(
                'scraper_task', 'case'
            ).get(id=document_id)
            return document
        except CourtDocument.DoesNotExist:
            return None


class CourtDocumentServiceAdapter(ICourtDocumentService):
    """
    法院文书服务适配器
    
    实现 ICourtDocumentService Protocol，将 CourtDocumentService 适配为标准接口
    """
    
    def __init__(self, service: Optional[CourtDocumentService] = None):
        """
        初始化适配器
        
        Args:
            service: CourtDocumentService 实例，为 None 时创建新实例
        """
        self._service = service
    
    @property
    def service(self) -> CourtDocumentService:
        """延迟加载服务实例"""
        if self._service is None:
            self._service = CourtDocumentService()
        return self._service
    
    def create_document_from_api_data(
        self,
        scraper_task_id: int,
        api_data: Dict[str, Any],
        case_id: Optional[int] = None
    ) -> Any:
        """
        从API数据创建文书记录
        
        Args:
            scraper_task_id: 爬虫任务ID
            api_data: API返回的文书数据
            case_id: 关联案件ID（可选）
            
        Returns:
            创建的文书记录
            
        Raises:
            ValidationException: 数据验证失败
            NotFoundError: 爬虫任务不存在
        """
        return self.service.create_document_from_api_data(scraper_task_id, api_data, case_id)
    
    def update_download_status(
        self,
        document_id: int,
        status: str,
        local_file_path: Optional[str] = None,
        file_size: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> Any:
        """
        更新文书下载状态
        
        Args:
            document_id: 文书记录ID
            status: 下载状态
            local_file_path: 本地文件路径（可选）
            file_size: 文件大小（可选）
            error_message: 错误信息（可选）
            
        Returns:
            更新后的文书记录
            
        Raises:
            NotFoundError: 文书记录不存在
            ValidationException: 状态值无效
        """
        return self.service.update_download_status(
            document_id, status, local_file_path, file_size, error_message
        )
    
    def get_documents_by_task(
        self,
        scraper_task_id: int
    ) -> List[Any]:
        """
        获取任务的所有文书记录
        
        Args:
            scraper_task_id: 爬虫任务ID
            
        Returns:
            文书记录列表
        """
        return self.service.get_documents_by_task(scraper_task_id)
    
    def get_document_by_id(
        self,
        document_id: int
    ) -> Optional[Any]:
        """
        根据ID获取文书记录
        
        Args:
            document_id: 文书记录ID
            
        Returns:
            文书记录，不存在时返回 None
        """
        return self.service.get_document_by_id(document_id)
    
    # 内部方法版本，供其他模块调用
    def create_document_from_api_data_internal(
        self,
        scraper_task_id: int,
        api_data: Dict[str, Any],
        case_id: Optional[int] = None
    ) -> Any:
        """
        从API数据创建文书记录（内部接口，无权限检查）
        """
        return self.service.create_document_from_api_data(scraper_task_id, api_data, case_id)
    
    def update_download_status_internal(
        self,
        document_id: int,
        status: str,
        local_file_path: Optional[str] = None,
        file_size: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> Any:
        """
        更新文书下载状态（内部接口，无权限检查）
        """
        return self.service.update_download_status(
            document_id, status, local_file_path, file_size, error_message
        )
    
    def get_documents_by_task_internal(
        self,
        scraper_task_id: int
    ) -> List[Any]:
        """
        获取任务的所有文书记录（内部接口，无权限检查）
        """
        return self.service.get_documents_by_task(scraper_task_id)
    
    def get_document_by_id_internal(
        self,
        document_id: int
    ) -> Optional[Any]:
        """
        根据ID获取文书记录（内部接口，无权限检查）
        """
        return self.service.get_document_by_id(document_id)
