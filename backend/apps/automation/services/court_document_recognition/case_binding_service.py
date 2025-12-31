"""
案件绑定服务

负责将识别出的法院文书绑定到对应案件，创建案件日志并附加文件。

通过 ServiceLocator 获取 CaseService，实现跨模块调用。

Requirements: 5.1, 5.2, 5.3, 5.4, 5.6
"""
import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional

from django.db import transaction

from apps.core.exceptions import NotFoundError

from .data_classes import BindingResult, DocumentType

if TYPE_CHECKING:
    from apps.core.interfaces import ICaseService

logger = logging.getLogger("apps.automation")


class CaseBindingService:
    """
    案件绑定服务
    
    职责：
    1. 根据案号查找匹配的案件
    2. 创建案件日志（含提醒时间）
    3. 将文书文件作为附件保存
    
    通过 ServiceLocator 访问 cases 模块，避免直接依赖。
    
    Requirements: 5.1, 5.2, 5.3, 5.4, 5.6
    """
    
    def __init__(self, case_service: Optional["ICaseService"] = None):
        """
        初始化服务（支持依赖注入）
        
        Args:
            case_service: 案件服务接口（可选，默认通过 ServiceLocator 获取）
        """
        self._case_service = case_service
    
    @property
    def case_service(self) -> "ICaseService":
        """
        延迟加载案件服务
        
        通过 ServiceLocator 获取，避免循环导入。
        """
        if self._case_service is None:
            from apps.core.interfaces import ServiceLocator
            self._case_service = ServiceLocator.get_case_service()
        return self._case_service
    
    def find_case_by_number(self, case_number: str) -> Optional[int]:
        """
        根据案号查找案件
        
        使用 ICaseService 的 search_cases_by_case_number_internal 方法
        进行模糊匹配搜索。
        
        Args:
            case_number: 案号字符串
            
        Returns:
            匹配到的案件 ID，未找到时返回 None
            
        Requirements: 5.1
        """
        if not case_number or not case_number.strip():
            logger.warning(
                "案号为空，无法查找案件",
                extra={
                    "action": "find_case_by_number",
                    "case_number": case_number
                }
            )
            return None
        
        try:
            # 使用 ICaseService 接口搜索案件
            cases = self.case_service.search_cases_by_case_number_internal(case_number)
            
            if not cases:
                logger.info(
                    f"未找到案号匹配的案件",
                    extra={
                        "action": "find_case_by_number",
                        "case_number": case_number,
                        "result": "not_found"
                    }
                )
                return None
            
            # 返回第一个匹配的案件 ID
            case_id = cases[0].id
            logger.info(
                f"找到案号匹配的案件",
                extra={
                    "action": "find_case_by_number",
                    "case_number": case_number,
                    "case_id": case_id,
                    "match_count": len(cases)
                }
            )
            return case_id
            
        except Exception as e:
            logger.error(
                f"查找案件失败：{e}",
                extra={
                    "action": "find_case_by_number",
                    "case_number": case_number,
                    "error": str(e)
                }
            )
            return None
    
    @transaction.atomic
    def create_case_log(
        self,
        case_id: int,
        content: str,
        reminder_time: Optional[datetime],
        file_path: str,
        document_type: Optional[DocumentType] = None,
        user: Optional[Any] = None
    ) -> int:
        """
        创建案件日志并附加文件
        
        在事务中执行以下操作：
        1. 创建案件日志（包含文书内容和提醒时间）
        2. 将文书文件作为附件保存
        
        Args:
            case_id: 案件 ID
            content: 日志内容（文书信息摘要）
            reminder_time: 提醒时间（开庭时间/保全到期时间）
            file_path: 文书文件路径
            document_type: 文书类型（用于确定提醒类型）
            user: 当前用户（可选）
            
        Returns:
            创建的案件日志 ID
            
        Raises:
            NotFoundError: 案件不存在
            
        Requirements: 5.2, 5.3, 5.4, 5.6
        """
        user_id = getattr(user, "id", None) if user else None
        
        logger.info(
            f"开始创建案件日志",
            extra={
                "action": "create_case_log",
                "case_id": case_id,
                "has_reminder": reminder_time is not None,
                "file_path": file_path,
                "user_id": user_id
            }
        )
        
        # 1. 创建案件日志
        # 使用 ICaseService 的内部方法创建日志
        case_log_id = self.case_service.create_case_log_internal(
            case_id=case_id,
            content=content,
            user_id=user_id
        )
        
        # 2. 如果有提醒时间，需要更新日志的提醒时间和类型
        if reminder_time:
            self._update_log_reminder(case_log_id, reminder_time, document_type)
        
        # 3. 添加文件附件
        if file_path:
            file_name = os.path.basename(file_path)
            success = self.case_service.add_case_log_attachment_internal(
                case_log_id=case_log_id,
                file_path=file_path,
                file_name=file_name
            )
            
            if not success:
                logger.warning(
                    f"添加日志附件失败",
                    extra={
                        "action": "create_case_log",
                        "case_log_id": case_log_id,
                        "file_path": file_path
                    }
                )
        
        logger.info(
            f"案件日志创建成功",
            extra={
                "action": "create_case_log",
                "case_id": case_id,
                "case_log_id": case_log_id,
                "reminder_time": str(reminder_time) if reminder_time else None
            }
        )
        
        return case_log_id
    
    def _update_log_reminder(
        self,
        case_log_id: int,
        reminder_time: datetime,
        document_type: Optional[DocumentType] = None
    ) -> None:
        """
        更新日志的提醒时间和类型
        
        根据文书类型设置对应的提醒类型：
        - 传票 -> hearing（开庭）
        - 执行裁定书 -> asset_preservation（财产保全）
        - 其他 -> other（其他）
        
        Args:
            case_log_id: 案件日志 ID
            reminder_time: 提醒时间
            document_type: 文书类型
        """
        try:
            from apps.cases.models import CaseLog
            from apps.core.enums import CaseLogReminderType
            
            # 根据文书类型确定提醒类型
            if document_type == DocumentType.SUMMONS:
                reminder_type = CaseLogReminderType.HEARING  # 开庭
            elif document_type == DocumentType.EXECUTION_RULING:
                reminder_type = CaseLogReminderType.ASSET_PRESERVATION  # 财产保全
            else:
                reminder_type = CaseLogReminderType.OTHER  # 其他
            
            CaseLog.objects.filter(id=case_log_id).update(
                reminder_time=reminder_time,
                reminder_type=reminder_type
            )
            
            logger.debug(
                f"更新日志提醒成功",
                extra={
                    "action": "_update_log_reminder",
                    "case_log_id": case_log_id,
                    "reminder_time": str(reminder_time),
                    "reminder_type": reminder_type
                }
            )
        except Exception as e:
            logger.error(
                f"更新日志提醒失败：{e}",
                extra={
                    "action": "_update_log_reminder",
                    "case_log_id": case_log_id,
                    "error": str(e)
                }
            )
    
    def bind_document_to_case(
        self,
        case_number: str,
        document_type: DocumentType,
        content: str,
        key_time: Optional[datetime],
        file_path: str,
        user: Optional[Any] = None
    ) -> BindingResult:
        """
        将文书绑定到案件
        
        完整的绑定流程：
        1. 根据案号查找案件
        2. 创建案件日志（含提醒时间和附件）
        3. 返回绑定结果
        
        Args:
            case_number: 识别出的案号
            document_type: 文书类型
            content: 日志内容
            key_time: 关键时间（开庭时间/保全到期时间）
            file_path: 文书文件路径
            user: 当前用户（可选）
            
        Returns:
            BindingResult 对象，包含绑定结果
            
        Requirements: 5.1, 5.2, 5.3, 5.4, 5.6, 5.8
        """
        # 1. 检查案号是否存在
        if not case_number:
            return BindingResult.failure_result(
                message="未识别到案号，无法绑定案件",
                error_code="CASE_NUMBER_NOT_FOUND"
            )
        
        # 2. 查找匹配的案件
        case_id = self.find_case_by_number(case_number)
        
        if case_id is None:
            return BindingResult.failure_result(
                message=f"未找到案号 {case_number} 对应的案件",
                error_code="CASE_NOT_FOUND"
            )
        
        # 3. 获取案件名称
        case_dto = self.case_service.get_case_by_id_internal(case_id)
        if case_dto is None:
            return BindingResult.failure_result(
                message=f"案件 {case_id} 不存在",
                error_code="CASE_NOT_FOUND"
            )
        
        case_name = case_dto.name
        
        # 4. 创建案件日志
        try:
            case_log_id = self.create_case_log(
                case_id=case_id,
                content=content,
                reminder_time=key_time,
                file_path=file_path,
                document_type=document_type,
                user=user
            )
            
            logger.info(
                f"文书绑定成功",
                extra={
                    "action": "bind_document_to_case",
                    "case_number": case_number,
                    "case_id": case_id,
                    "case_name": case_name,
                    "case_log_id": case_log_id,
                    "document_type": document_type.value
                }
            )
            
            return BindingResult.success_result(
                case_id=case_id,
                case_name=case_name,
                case_log_id=case_log_id
            )
            
        except NotFoundError as e:
            logger.error(
                f"绑定失败：案件不存在",
                extra={
                    "action": "bind_document_to_case",
                    "case_number": case_number,
                    "case_id": case_id,
                    "error": str(e)
                }
            )
            return BindingResult.failure_result(
                message=str(e),
                error_code="CASE_NOT_FOUND"
            )
        except Exception as e:
            logger.error(
                f"绑定失败：{e}",
                extra={
                    "action": "bind_document_to_case",
                    "case_number": case_number,
                    "case_id": case_id,
                    "error": str(e)
                }
            )
            return BindingResult.failure_result(
                message=f"绑定失败：{str(e)}",
                error_code="BINDING_ERROR"
            )
    
    def format_log_content(
        self,
        document_type: DocumentType,
        case_number: Optional[str],
        key_time: Optional[datetime],
        raw_text: str
    ) -> str:
        """
        格式化日志内容
        
        根据文书类型生成结构化的日志内容。
        
        Args:
            document_type: 文书类型
            case_number: 案号
            key_time: 关键时间
            raw_text: 原始文本（截取前500字符）
            
        Returns:
            格式化后的日志内容
        """
        type_labels = {
            DocumentType.SUMMONS: "传票",
            DocumentType.EXECUTION_RULING: "执行裁定书",
            DocumentType.OTHER: "其他文书"
        }
        
        type_label = type_labels.get(document_type, "法院文书")
        
        lines = [f"【{type_label}】"]
        
        if case_number:
            lines.append(f"案号：{case_number}")
        
        if key_time:
            if document_type == DocumentType.SUMMONS:
                lines.append(f"开庭时间：{key_time.strftime('%Y-%m-%d %H:%M')}")
            elif document_type == DocumentType.EXECUTION_RULING:
                lines.append(f"保全到期时间：{key_time.strftime('%Y-%m-%d')}")
        
        # 添加原始文本摘要（限制长度）
        if raw_text:
            text_preview = raw_text[:500]
            if len(raw_text) > 500:
                text_preview += "..."
            lines.append(f"\n文书内容摘要：\n{text_preview}")
        
        return "\n".join(lines)

    @transaction.atomic
    def manual_bind_document_to_case(
        self,
        task_id: int,
        case_id: int,
        user: Optional[Any] = None
    ) -> BindingResult:
        """
        手动绑定文书到案件
        
        与自动绑定的区别：
        1. 跳过案号匹配步骤
        2. 直接使用用户选择的案件ID
        3. 触发后续通知流程
        
        Args:
            task_id: 识别任务ID
            case_id: 用户选择的案件ID
            user: 当前用户（可选）
            
        Returns:
            BindingResult 对象，包含绑定结果
            
        Requirements: 3.1, 3.2, 4.1, 4.2, 4.3, 4.4
        """
        from apps.automation.models import DocumentRecognitionTask
        from apps.cases.models import Case, CaseLog
        
        logger.info(
            f"开始手动绑定文书到案件",
            extra={
                "action": "manual_bind_document_to_case",
                "task_id": task_id,
                "case_id": case_id,
                "user_id": getattr(user, "id", None) if user else None
            }
        )
        
        # 1. 获取识别任务
        try:
            task = DocumentRecognitionTask.objects.get(id=task_id)
        except DocumentRecognitionTask.DoesNotExist:
            return BindingResult.failure_result(
                message=f"任务 {task_id} 不存在",
                error_code="TASK_NOT_FOUND"
            )
        
        # 2. 检查任务是否已绑定
        if task.binding_success:
            return BindingResult.failure_result(
                message="任务已绑定到案件",
                error_code="ALREADY_BOUND"
            )
        
        # 3. 获取案件信息
        case_dto = self.case_service.get_case_by_id_internal(case_id)
        if case_dto is None:
            return BindingResult.failure_result(
                message=f"案件 {case_id} 不存在",
                error_code="CASE_NOT_FOUND"
            )
        
        case_name = case_dto.name
        
        # 4. 确定文书类型
        document_type = DocumentType.OTHER
        if task.document_type:
            try:
                document_type = DocumentType(task.document_type)
            except ValueError:
                document_type = DocumentType.OTHER
        
        # 5. 格式化日志内容
        content = self.format_log_content(
            document_type=document_type,
            case_number=task.case_number,
            key_time=task.key_time,
            raw_text=task.raw_text or ""
        )
        
        # 6. 获取文件路径（优先使用重命名后的路径）
        file_path = task.renamed_file_path or task.file_path
        
        # 7. 创建案件日志
        try:
            case_log_id = self.create_case_log(
                case_id=case_id,
                content=content,
                reminder_time=task.key_time,
                file_path=file_path,
                document_type=document_type,
                user=user
            )
        except Exception as e:
            logger.error(
                f"创建案件日志失败：{e}",
                extra={
                    "action": "manual_bind_document_to_case",
                    "task_id": task_id,
                    "case_id": case_id,
                    "error": str(e)
                }
            )
            return BindingResult.failure_result(
                message=f"创建案件日志失败：{str(e)}",
                error_code="LOG_CREATE_ERROR"
            )
        
        # 8. 更新任务状态（使用外键字段）
        try:
            case_obj = Case.objects.get(id=case_id)
            case_log_obj = CaseLog.objects.get(id=case_log_id)
            
            task.case = case_obj
            task.case_log = case_log_obj
            task.binding_success = True
            task.binding_message = f"手动绑定到案件 {case_name}"
            task.binding_error_code = None
            task.save(update_fields=[
                'case', 'case_log', 'binding_success',
                'binding_message', 'binding_error_code'
            ])
        except Exception as e:
            logger.error(
                f"更新任务状态失败：{e}",
                extra={
                    "action": "manual_bind_document_to_case",
                    "task_id": task_id,
                    "case_id": case_id,
                    "error": str(e)
                }
            )
            # 回滚事务
            raise
        
        # 9. 触发飞书通知（异步）
        self._trigger_notification(task, case_id, case_name, document_type)
        
        logger.info(
            f"手动绑定成功",
            extra={
                "action": "manual_bind_document_to_case",
                "task_id": task_id,
                "case_id": case_id,
                "case_name": case_name,
                "case_log_id": case_log_id
            }
        )
        
        return BindingResult.success_result(
            case_id=case_id,
            case_name=case_name,
            case_log_id=case_log_id
        )
    
    def _trigger_notification(
        self,
        task: Any,
        case_id: int,
        case_name: str,
        document_type: DocumentType
    ) -> None:
        """
        触发飞书通知
        
        直接调用通知服务发送通知，不使用异步任务。
        通知失败不影响绑定结果，仅记录错误。
        
        Args:
            task: DocumentRecognitionTask 实例
            case_id: 案件ID
            case_name: 案件名称
            document_type: 文书类型
            
        Requirements: 4.4
        """
        try:
            from .notification_service import DocumentRecognitionNotificationService
            from django.utils import timezone
            
            notification_service = DocumentRecognitionNotificationService()
            
            # 使用重命名后的文件路径（如果有），否则使用原始路径
            file_path = task.renamed_file_path or task.file_path
            
            notification_result = notification_service.send_notification(
                case_id=case_id,
                document_type=document_type.value,
                case_number=task.case_number,
                key_time=task.key_time,
                file_path=file_path,
                case_name=case_name,
            )
            
            # 更新任务通知状态
            task.notification_sent = notification_result.success
            task.notification_sent_at = notification_result.sent_at
            task.notification_file_sent = notification_result.file_sent
            
            if not notification_result.success:
                task.notification_error = notification_result.message
                logger.warning(
                    f"文书识别通知发送失败",
                    extra={
                        "action": "_trigger_notification",
                        "task_id": task.id,
                        "case_id": case_id,
                        "error": notification_result.message
                    }
                )
            else:
                logger.info(
                    f"📨 文书识别通知发送成功",
                    extra={
                        "action": "_trigger_notification",
                        "task_id": task.id,
                        "case_id": case_id,
                        "file_sent": notification_result.file_sent
                    }
                )
            
            task.save(update_fields=[
                "notification_sent",
                "notification_sent_at",
                "notification_file_sent",
                "notification_error",
            ])
            
        except Exception as e:
            # 通知失败不影响绑定结果，仅记录错误
            logger.warning(
                f"发送飞书通知失败：{e}",
                extra={
                    "action": "_trigger_notification",
                    "task_id": task.id,
                    "case_id": case_id,
                    "error": str(e)
                }
            )
            # 更新通知错误状态
            try:
                task.notification_sent = False
                task.notification_error = str(e)
                task.save(update_fields=["notification_sent", "notification_error"])
            except Exception:
                pass  # 忽略保存错误
