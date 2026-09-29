"""
案件绑定服务

负责将识别出的法院文书绑定到对应案件，创建案件日志并附加文件。

通过 ServiceLocator 获取 CaseService，实现跨模块调用。

Requirements: 5.1, 5.2, 5.3, 5.4, 5.6
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from django.db import transaction

from apps.core.exceptions import NotFoundError
from apps.core.exceptions.error_codes import CASE_NOT_FOUND

from .data_classes import BindingResult, DocumentType

if TYPE_CHECKING:
    from apps.core.interfaces import ICaseService

logger = logging.getLogger("apps.document_recognition")


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

    def find_case_by_number(self, case_number: str) -> int | None:
        """
        根据案号查找案件（弱匹配，仅兼容旧调用方）

        .. deprecated::
            自动绑定已改用 DocumentCaseMatchingService.auto_match 的严格匹配
            （规范化精确 + 在办 + 唯一）。新代码不要调用本方法。

        Args:
            case_number: 案号字符串

        Returns:
            匹配到的案件 ID，未找到时返回 None
        """
        if not case_number or not case_number.strip():
            return None

        try:
            cases = self.case_service.search_cases_by_case_number_internal(case_number)
            if not cases:
                return None
            return cases[0].id
        except Exception as e:
            logger.error(
                f"查找案件失败：{e}",
                extra={"action": "find_case_by_number", "case_number": case_number, "error": str(e)},
            )
            return None

    @staticmethod
    def _media_relative(file_path: str) -> str:
        """绝对路径 → media 相对路径（不在 media 下时原样返回）。"""
        try:
            from django.conf import settings

            return str(Path(file_path).resolve().relative_to(Path(settings.MEDIA_ROOT).resolve()))
        except (ValueError, ImportError):
            return file_path

    @transaction.atomic
    def create_case_log(
        self,
        case_id: int,
        content: str,
        file_path: str,
        user: Any | None = None,
    ) -> int:
        """
        创建案件日志并附加文件（不写提醒）

        在事务中执行以下操作：
        1. 创建案件日志（文书信息摘要）
        2. 将文书文件作为附件保存

        提醒不再随绑定自动创建——日期候选由律师在确认接口逐条人工确认后才写入
        重要日期提醒（date_candidate_service.confirm_candidates 是唯一写入入口）。

        Args:
            case_id: 案件 ID
            content: 日志内容（文书信息摘要）
            file_path: 文书文件路径
            user: 当前用户（可选）

        Returns:
            创建的案件日志 ID

        Raises:
            NotFoundError: 案件不存在

        Requirements: 5.2, 5.3, 5.4, 5.6
        """
        user_id = getattr(user, "id", None) if user else None

        logger.info(
            "开始创建案件日志",
            extra={
                "action": "create_case_log",
                "case_id": case_id,
                "file_path": file_path,
                "user_id": user_id,
            },
        )

        # 1. 创建案件日志
        # 使用 ICaseService 的内部方法创建日志
        case_log_id = self.case_service.create_case_log_internal(case_id=case_id, content=content, user_id=user_id)

        # 2. 添加文件附件（FileField 需 media 相对路径：绝对路径超出 varchar(100) 且语义错误）
        if file_path:
            file_name = Path(file_path).name
            success = self.case_service.add_case_log_attachment_internal(
                case_log_id=case_log_id, file_path=self._media_relative(file_path), file_name=file_name
            )

            if not success:
                logger.warning(
                    "添加日志附件失败",
                    extra={"action": "create_case_log", "case_log_id": case_log_id, "file_path": file_path},
                )

        logger.info(
            "案件日志创建成功",
            extra={
                "action": "create_case_log",
                "case_id": case_id,
                "case_log_id": case_log_id,
            },
        )

        return case_log_id

    def bind_document_to_case(
        self,
        case_id: int,
        document_type: DocumentType,
        content: str,
        file_path: str,
        user: Any | None = None,
    ) -> BindingResult:
        """
        将文书绑定到（已由严格匹配确定的）案件

        完整的绑定流程：
        1. 获取案件信息
        2. 创建案件日志（含附件，不含提醒——提醒只走人工确认接口）
        3. 返回绑定结果

        案号的严格匹配（精确+在办+唯一）由 DocumentCaseMatchingService.auto_match
        在调用前完成；本方法不再自行按案号搜索。

        Args:
            case_id: 严格匹配命中的案件 ID
            document_type: 文书类型
            content: 日志内容
            file_path: 文书文件路径
            user: 当前用户（可选）

        Returns:
            BindingResult 对象，包含绑定结果

        Requirements: 5.1, 5.2, 5.3, 5.4, 5.6, 5.8
        """
        # 1. 获取案件名称
        case_dto = self.case_service.get_case_by_id_internal(case_id)
        if case_dto is None:
            return BindingResult.failure_result(message=f"案件 {case_id} 不存在", error_code=CASE_NOT_FOUND)

        case_name = case_dto.name

        # 2. 创建案件日志
        try:
            case_log_id = self.create_case_log(
                case_id=case_id,
                content=content,
                file_path=file_path,
                user=user,
            )

            logger.info(
                "文书绑定成功",
                extra={
                    "action": "bind_document_to_case",
                    "case_id": case_id,
                    "case_name": case_name,
                    "case_log_id": case_log_id,
                    "document_type": document_type.value,
                },
            )

            return BindingResult.success_result(case_id=case_id, case_name=case_name, case_log_id=case_log_id)

        except NotFoundError as e:
            logger.error(
                "绑定失败：案件不存在",
                extra={
                    "action": "bind_document_to_case",
                    "case_id": case_id,
                    "error": str(e),
                },
            )
            return BindingResult.failure_result(message=str(e), error_code=CASE_NOT_FOUND)
        except Exception as e:
            logger.error(
                f"绑定失败：{e}",
                extra={
                    "action": "bind_document_to_case",
                    "case_id": case_id,
                    "error": str(e),
                },
            )
            return BindingResult.failure_result(message=f"绑定失败：{e!s}", error_code="BINDING_ERROR")

    def format_log_content(
        self, document_type: DocumentType, case_number: str | None, raw_text: str, date_count: int = 0
    ) -> str:
        """
        格式化日志内容

        根据文书类型生成结构化的日志内容。日期不直接写入日志正文，
        改为提示识别到的候选数量（候选由律师人工确认后写入提醒）。

        Args:
            document_type: 文书类型
            case_number: 案号
            raw_text: 原始文本（截取前500字符）
            date_count: 识别到的日期候选数量

        Returns:
            格式化后的日志内容
        """
        type_labels = {
            DocumentType.SUMMONS: "传票",
            DocumentType.EXECUTION_RULING: "执行裁定书",
            DocumentType.OTHER: "其他文书",
        }

        type_label = type_labels.get(document_type, "法院文书")

        lines = [f"【{type_label}】"]

        if case_number:
            lines.append(f"案号：{case_number}")

        if date_count > 0:
            lines.append(f"识别到 {date_count} 个关键日期（待人工确认后写入重要日期提醒）")

        from apps.document_recognition.services.contact_extraction_service import extract_address, extract_contacts

        for row in extract_contacts(raw_text):
            name, phone = str(row["name"]), row["phone"]
            if name and phone:
                lines.append(f"联系人：{name}（{phone}）")
            elif name:
                lines.append(f"联系人：{name}")
            elif phone:
                lines.append(f"联系电话：{phone}")
        address = extract_address(raw_text)
        if address:
            lines.append(f"地址：{address}")

        # 添加原始文本摘要（限制长度）
        if raw_text:
            text_preview = raw_text[:500]
            if len(raw_text) > 500:
                text_preview += "..."
            lines.append(f"\n文书内容摘要：\n{text_preview}")

        return "\n".join(lines)

    @transaction.atomic
    def manual_bind_document_to_case(self, task_id: int, case_id: int, user: Any | None = None) -> BindingResult:
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
        from apps.document_recognition.models import DocumentRecognitionTask

        logger.info(
            "开始手动绑定文书到案件",
            extra={
                "action": "manual_bind_document_to_case",
                "task_id": task_id,
                "case_id": case_id,
                "user_id": getattr(user, "id", None) if user else None,
            },
        )

        # 1. 获取识别任务（行锁防止并发请求重复绑定/重复建日志）
        try:
            task = DocumentRecognitionTask.objects.select_for_update().get(id=task_id)
        except DocumentRecognitionTask.DoesNotExist:
            return BindingResult.failure_result(message=f"任务 {task_id} 不存在", error_code="TASK_NOT_FOUND")

        # 2. 检查任务是否已绑定
        if task.binding_success:
            return BindingResult.failure_result(message="任务已绑定到案件", error_code="ALREADY_BOUND")

        # 3. 获取案件信息
        case_dto = self.case_service.get_case_by_id_internal(case_id)
        if case_dto is None:
            return BindingResult.failure_result(message=f"案件 {case_id} 不存在", error_code=CASE_NOT_FOUND)

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
            raw_text=task.raw_text or "",
            date_count=task.date_candidates.count(),
        )

        # 6. 获取文件路径（优先使用重命名后的路径）
        file_path = task.renamed_file_path or task.file_path

        # 7. 创建案件日志
        try:
            case_log_id = self.create_case_log(
                case_id=case_id,
                content=content,
                file_path=file_path,
                user=user,
            )
        except Exception as e:
            logger.error(
                "创建案件日志失败：%s",
                e,
                extra={
                    "action": "manual_bind_document_to_case",
                    "task_id": task_id,
                    "case_id": case_id,
                    "error": str(e),
                },
            )
            return BindingResult.failure_result(message=f"创建案件日志失败：{e!s}", error_code="LOG_CREATE_ERROR")

        # 8. 更新任务状态（外键直接按 id 赋值，省两次整对象查询）
        task.case_id = case_id
        task.case_log_id = case_log_id
        task.binding_success = True
        task.binding_message = f"手动绑定到案件 {case_name}"
        task.binding_error_code = None
        task.save(update_fields=["case", "case_log", "binding_success", "binding_message", "binding_error_code"])

        # 9. 触发飞书通知：事务提交后再发（网络 IO 不进事务、不拉长锁持有时间）；
        #    非事务上下文下 on_commit 立即执行
        transaction.on_commit(lambda: self._trigger_notification(task, case_id, case_name, document_type))

        logger.info(
            "手动绑定成功",
            extra={
                "action": "manual_bind_document_to_case",
                "task_id": task_id,
                "case_id": case_id,
                "case_name": case_name,
                "case_log_id": case_log_id,
            },
        )

        return BindingResult.success_result(case_id=case_id, case_name=case_name, case_log_id=case_log_id)

    def _trigger_notification(self, task: Any, case_id: int, case_name: str, document_type: DocumentType) -> None:
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
                date_count=task.date_candidates.count(),
            )

            # 更新任务通知状态
            task.notification_sent = notification_result.success
            task.notification_sent_at = notification_result.sent_at
            task.notification_file_sent = notification_result.file_sent

            if not notification_result.success:
                task.notification_error = notification_result.message
                logger.warning(
                    "文书识别通知发送失败",
                    extra={
                        "action": "_trigger_notification",
                        "task_id": task.id,
                        "case_id": case_id,
                        "error": notification_result.message,
                    },
                )
            else:
                logger.info(
                    "📨 文书识别通知发送成功",
                    extra={
                        "action": "_trigger_notification",
                        "task_id": task.id,
                        "case_id": case_id,
                        "file_sent": notification_result.file_sent,
                    },
                )

            task.save(
                update_fields=[
                    "notification_sent",
                    "notification_sent_at",
                    "notification_file_sent",
                    "notification_error",
                ]
            )

        except Exception as e:
            # 通知失败不影响绑定结果，仅记录错误
            logger.warning(
                "发送飞书通知失败：%s",
                e,
                extra={"action": "_trigger_notification", "task_id": task.id, "case_id": case_id, "error": str(e)},
            )
            # 更新通知错误状态
            try:
                task.notification_sent = False
                task.notification_error = str(e)
                task.save(update_fields=["notification_sent", "notification_error"])
            except Exception as save_error:
                logger.warning(
                    "记录通知失败状态异常: %s",
                    save_error,
                    extra={"action": "_trigger_notification", "task_id": task.id},
                )
