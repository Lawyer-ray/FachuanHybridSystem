"""
SMS 提交服务

负责短信的提交、案件指定和重试处理。
从 CourtSMSService 中提取的单一职责服务。

Requirements: 2.1, 2.3, 5.1, 5.2, 5.5
"""
import logging
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from django.utils import timezone
from django.db import transaction
from django_q.tasks import async_task

from apps.core.exceptions import ValidationException, NotFoundError
from apps.automation.models import CourtSMS, CourtSMSStatus

if TYPE_CHECKING:
    from apps.core.interfaces import ICaseService, ILawyerService

logger = logging.getLogger("apps.automation")


class SMSSubmissionService:
    """
    SMS 提交服务
    
    负责：
    - 短信提交和记录创建
    - 手动指定案件
    - 重试处理
    
    遵循架构规范：
    - 使用实例方法而非 @staticmethod
    - 通过依赖注入获取依赖
    - 使用 apps.core.exceptions 中定义的异常类
    - 遵循延迟加载模式
    """
    
    def __init__(
        self,
        case_service: Optional["ICaseService"] = None,
        lawyer_service: Optional["ILawyerService"] = None,
    ):
        """
        初始化服务，支持依赖注入
        
        Args:
            case_service: 案件服务（可选，延迟加载）
            lawyer_service: 律师服务（可选，延迟加载）
        """
        self._case_service = case_service
        self._lawyer_service = lawyer_service
    
    @property
    def case_service(self) -> "ICaseService":
        """延迟加载案件服务"""
        if self._case_service is None:
            from apps.core.interfaces import ServiceLocator
            self._case_service = ServiceLocator.get_case_service()
        return self._case_service
    
    @property
    def lawyer_service(self) -> "ILawyerService":
        """延迟加载律师服务"""
        if self._lawyer_service is None:
            from apps.core.interfaces import ServiceLocator
            self._lawyer_service = ServiceLocator.get_lawyer_service()
        return self._lawyer_service
    
    def submit_sms(self, content: str, received_at: datetime = None) -> CourtSMS:
        """
        提交短信，创建记录并触发异步处理
        
        Args:
            content: 短信内容
            received_at: 收到时间，默认为当前时间
            
        Returns:
            CourtSMS: 创建的短信记录
            
        Raises:
            ValidationException: 参数验证失败
        """
        if not content or not content.strip():
            raise ValidationException(
                message="短信内容不能为空",
                code="EMPTY_SMS_CONTENT",
                errors={"content": "短信内容不能为空"}
            )
        
        if received_at is None:
            received_at = timezone.now()
        
        try:
            # 创建 CourtSMS 记录
            sms = CourtSMS.objects.create(
                content=content.strip(),
                received_at=received_at,
                status=CourtSMSStatus.PENDING
            )
            
            logger.info(f"创建短信记录成功: ID={sms.id}, 长度={len(content)}")
            
            # 提交异步处理任务
            task_id = async_task(
                'apps.automation.services.sms.court_sms_service.process_sms_async',
                sms.id,
                task_name=f"court_sms_processing_{sms.id}"
            )
            
            logger.info(f"提交异步处理任务: SMS ID={sms.id}, Task ID={task_id}")
            
            return sms
            
        except Exception as e:
            logger.error(f"提交短信处理失败: {str(e)}")
            raise ValidationException(
                message=f"提交短信处理失败: {str(e)}",
                code="SMS_SUBMIT_FAILED",
                errors={"error": str(e)}
            )
    
    @transaction.atomic
    def assign_case(self, sms_id: int, case_id: int) -> CourtSMS:
        """
        手动指定案件
        
        手动指定后直接创建案件绑定，跳过匹配阶段，进入重命名和通知流程。
        
        Args:
            sms_id: 短信记录ID
            case_id: 案件ID
            
        Returns:
            CourtSMS: 更新后的短信记录
            
        Raises:
            NotFoundError: 记录不存在
            ValidationException: 操作失败
        """
        try:
            sms = CourtSMS.objects.get(id=sms_id)
        except CourtSMS.DoesNotExist:
            raise NotFoundError(f"短信记录不存在: ID={sms_id}")
        
        # 验证案件是否存在
        case_dto = self.case_service.get_case_by_id_internal(case_id)
        if not case_dto:
            raise NotFoundError(f"案件不存在: ID={case_id}")
        
        try:
            # 更新短信记录 - 直接设置外键 ID，避免跨模块 Model 导入
            sms.case_id = case_id
            sms.error_message = None  # 清除之前的错误信息
            sms.save()
            
            logger.info(f"手动指定案件成功: SMS ID={sms_id}, Case ID={case_id}")
            
            # 创建案件绑定（跳过匹配阶段）
            success = self._create_case_binding(sms)
            if success:
                sms.status = CourtSMSStatus.RENAMING
                sms.save()
                logger.info(f"案件绑定创建成功，进入重命名阶段: SMS ID={sms_id}")
            else:
                sms.status = CourtSMSStatus.FAILED
                sms.error_message = "创建案件绑定失败"
                sms.save()
                logger.error(f"案件绑定创建失败: SMS ID={sms_id}")
                return sms
            
            # 触发后续处理流程（从重命名阶段开始）
            task_id = async_task(
                'apps.automation.services.sms.court_sms_service.process_sms_from_renaming',
                sms.id,
                task_name=f"court_sms_continue_{sms.id}"
            )
            
            logger.info(f"触发后续处理任务: SMS ID={sms.id}, Task ID={task_id}")
            
            return sms
            
        except Exception as e:
            logger.error(f"手动指定案件失败: SMS ID={sms_id}, Case ID={case_id}, 错误: {str(e)}")
            raise ValidationException(
                message=f"手动指定案件失败: {str(e)}",
                code="CASE_ASSIGNMENT_FAILED",
                errors={"error": str(e)}
            )
    
    def retry_processing(self, sms_id: int) -> CourtSMS:
        """
        重新处理短信
        
        Args:
            sms_id: 短信记录ID
            
        Returns:
            CourtSMS: 更新后的短信记录
            
        Raises:
            NotFoundError: 记录不存在
            ValidationException: 操作失败
        """
        try:
            sms = CourtSMS.objects.get(id=sms_id)
        except CourtSMS.DoesNotExist:
            raise NotFoundError(f"短信记录不存在: ID={sms_id}")
        
        try:
            # 重置状态和错误信息
            sms.status = CourtSMSStatus.PENDING
            sms.error_message = None
            sms.retry_count += 1
            
            # 清理关联数据（保留原始解析结果）
            sms.scraper_task = None
            sms.case = None
            sms.case_log = None
            sms.feishu_sent_at = None
            sms.feishu_error = None
            
            sms.save()
            
            logger.info(f"重置短信状态成功: SMS ID={sms_id}, 重试次数={sms.retry_count}")
            
            # 重新提交处理任务
            task_id = async_task(
                'apps.automation.services.sms.court_sms_service.process_sms_async',
                sms.id,
                task_name=f"court_sms_retry_{sms.id}_{sms.retry_count}"
            )
            
            logger.info(f"重新提交处理任务: SMS ID={sms.id}, Task ID={task_id}")
            
            return sms
            
        except Exception as e:
            logger.error(f"重新处理短信失败: SMS ID={sms_id}, 错误: {str(e)}")
            raise ValidationException(
                message=f"重新处理短信失败: {str(e)}",
                code="SMS_RETRY_FAILED",
                errors={"error": str(e)}
            )
    
    def _create_case_binding(self, sms: CourtSMS) -> bool:
        """
        创建案件绑定和日志
        
        注意：
        1. 此方法只创建案件日志，不添加附件。附件会在重命名阶段完成后添加。
        2. 如果短信提取到案号，但案件中还没有该案号，则自动写入案件的 case_numbers 字段。
        
        Args:
            sms: CourtSMS 实例
            
        Returns:
            bool: 是否创建成功
        """
        if not sms.case:
            return False
        
        try:
            # 获取 CaseLogService
            from apps.core.interfaces import ServiceLocator
            case_log_service = ServiceLocator.get_caselog_service()
            
            # 获取系统用户（使用管理员用户作为系统操作人）
            admin_lawyer_dto = self.lawyer_service.get_admin_lawyer_internal()
            if not admin_lawyer_dto:
                logger.error("未找到管理员用户，无法创建案件日志")
                return False
            
            # 通过 ServiceLocator 获取 Lawyer 服务，避免跨模块 Model 导入
            system_user = self.lawyer_service.get_lawyer_internal(admin_lawyer_dto.id)
            
            # 如果短信提取到案号，自动写入案件（如果不存在）
            if sms.case_numbers:
                self._add_case_numbers_to_case(sms)
            
            # 创建案件日志（只包含短信内容，附件在重命名后添加）
            case_log = case_log_service.create_log(
                case_id=sms.case.id,
                content=f"收到法院短信：{sms.content}",
                user=system_user
            )
            
            sms.case_log = case_log
            sms.save()
            
            logger.info(f"案件绑定创建成功: SMS ID={sms.id}, CaseLog ID={case_log.id}")
            return True
            
        except Exception as e:
            logger.error(f"创建案件绑定失败: SMS ID={sms.id}, 错误: {str(e)}")
            return False
    
    def _add_case_numbers_to_case(self, sms: CourtSMS) -> None:
        """
        将短信中提取的案号写入案件（如果不存在）
        
        Args:
            sms: CourtSMS 实例（必须已绑定案件）
        """
        import re
        
        if not sms.case or not sms.case_numbers:
            return
        
        try:
            # 过滤掉明显不是案号的内容（如日期）
            valid_case_numbers = []
            for num in sms.case_numbers:
                # 跳过日期格式（如 "2025年12月17号"）
                if "年" in num and "月" in num and "日" in num:
                    continue
                if "年" in num and "月" in num and num.endswith("号"):
                    # 检查是否是日期格式
                    if re.match(r'^\d{4}年\d{1,2}月\d{1,2}号?$', num):
                        continue
                valid_case_numbers.append(num)
            
            if not valid_case_numbers:
                logger.info(f"短信 {sms.id} 没有有效的案号需要写入")
                return
            
            # 获取管理员用户ID
            admin_lawyer_dto = self.lawyer_service.get_admin_lawyer_internal()
            user_id = admin_lawyer_dto.id if admin_lawyer_dto else None
            
            # 逐个添加案号
            added_count = 0
            for case_number in valid_case_numbers:
                success = self.case_service.add_case_number_internal(
                    case_id=sms.case.id,
                    case_number=case_number,
                    user_id=user_id
                )
                if success:
                    added_count += 1
            
            if added_count > 0:
                logger.info(f"为案件 {sms.case.id} 添加了 {added_count} 个案号: {valid_case_numbers}")
                
        except Exception as e:
            # 案号写入失败不影响主流程
            logger.warning(f"写入案号失败: SMS ID={sms.id}, 错误: {str(e)}")
