"""
文书处理器

负责下载后的文书处理:解压、案件匹配、重命名、通知等.
"""

import logging
import queue
import tempfile
import threading
import zipfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, cast

from django.utils.translation import gettext_lazy as _

from apps.automation.models import DocumentQueryHistory
from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord, DocumentProcessResult
from apps.core.interfaces import ServiceLocator

if TYPE_CHECKING:
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.document_renamer import DocumentRenamer
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService

logger = logging.getLogger("apps.automation")


class DocumentProcessor:
    """文书处理器"""

    def __init__(
        self,
        case_matcher: Optional["CaseMatcher"] = None,
        document_renamer: Optional["DocumentRenamer"] = None,
        notification_service: Optional["SMSNotificationService"] = None,
    ) -> None:
        """
        初始化文书处理器

        Args:
            case_matcher: 案件匹配服务实例(可选)
            document_renamer: 文书重命名服务实例(可选)
            notification_service: 通知服务实例(可选)
        """
        self._case_matcher = case_matcher
        self._document_renamer = document_renamer
        self._notification_service = notification_service

        logger.debug("DocumentProcessor 初始化完成")

    @property
    def case_matcher(self) -> "CaseMatcher":
        """延迟加载案件匹配服务"""
        if self._case_matcher is None:
            from apps.automation.services.sms.case_matcher import CaseMatcher

            self._case_matcher = CaseMatcher()
        return self._case_matcher

    @property
    def document_renamer(self) -> "DocumentRenamer":
        """延迟加载文书重命名服务"""
        if self._document_renamer is None:
            from apps.automation.services.sms.document_renamer import DocumentRenamer

            self._document_renamer = DocumentRenamer()
        return self._document_renamer

    @property
    def notification_service(self) -> "SMSNotificationService":
        """延迟加载通知服务"""
        if self._notification_service is None:
            from apps.automation.services.sms.sms_notification_service import SMSNotificationService

            self._notification_service = SMSNotificationService()
        return self._notification_service

    def extract_zip_if_needed(self, file_path: str) -> list[str] | None:
        """
        如果是 ZIP 文件则解压,返回解压后的文件列表

        Args:
            file_path: 文件路径

        Returns:
            解压后的文件路径列表,如果不是 ZIP 文件则返回 None
        """
        if not file_path.lower().endswith(".zip"):
            return None

        try:
            extract_dir = tempfile.mkdtemp(prefix="extracted_documents_")
            extract_path = Path(extract_dir)

            with zipfile.ZipFile(file_path, "r") as zip_ref:
                for member in zip_ref.infolist():
                    target = (extract_path / member.filename).resolve()
                    if not str(target).startswith(str(extract_path.resolve())):
                        logger.warning(f"跳过不安全的 ZIP 条目: {member.filename}")
                        continue
                    zip_ref.extract(member, extract_path)

            extracted_files: list[Any] = []
            for root, _dirs, files in extract_path.walk():
                for file in files:
                    file_full_path = root / file
                    extracted_files.append(str(file_full_path))

            logger.info(f"ZIP 解压成功: {len(extracted_files)} 个文件")
            return extracted_files

        except Exception as e:
            logger.error(f"ZIP 解压失败: {e!s}")
            return None

    def process_document(
        self, record: DocumentDeliveryRecord, file_path: str, extracted_files: list[str], credential_id: int
    ) -> DocumentProcessResult:
        """
        处理下载的文书 - 解压文件后在独立线程中执行后续处理

        注意:此方法在 Playwright 上下文中调用,ORM 操作需要在独立线程中执行

        Args:
            record: 文书记录
            file_path: 文件路径
            extracted_files: 解压后的文件列表
            credential_id: 账号凭证 ID

        Returns:
            DocumentProcessResult
        """
        logger.info(f"开始处理下载的文书: {file_path}")

        result = DocumentProcessResult(
            success=False,
            case_id=None,
            case_log_id=None,
            renamed_path=None,
            notification_sent=False,
            error_message=None,
        )

        try:
            # 处理 ZIP 压缩包(纯文件操作,不涉及 ORM)
            if not extracted_files:
                extracted_files = self.extract_zip_if_needed(file_path) or [file_path]

            logger.info(f"文书下载完成: 案号={record.case_number}, 文件={file_path}")
            if len(extracted_files) > 1:
                logger.info(f"ZIP 解压完成: {len(extracted_files)} 个文件")
                for i, extracted_file in enumerate(extracted_files):
                    logger.info(f"  文件 {i + 1}: {extracted_file}")

            # 在独立线程中执行后续处理(创建 CourtSMS、案件匹配、通知等)
            process_result = self._process_sms_in_thread(
                record=record, file_path=file_path, extracted_files=extracted_files, credential_id=credential_id
            )

            result.success = process_result.get("success", False)
            result.case_id = process_result.get("case_id")
            result.case_log_id = process_result.get("case_log_id")
            result.renamed_path = process_result.get("renamed_path", file_path)
            result.notification_sent = process_result.get("notification_sent", False)
            result.error_message = process_result.get("error_message")

        except Exception as e:
            error_msg = f"处理下载文书失败: {e!s}"
            logger.error(error_msg)
            result.error_message = error_msg

        return result

    def record_query_history(self, credential_id: int, entry: DocumentDeliveryRecord) -> None:
        """
        在独立线程中记录查询历史,避免异步上下文问题

        Args:
            credential_id: 账号凭证 ID
            entry: 文书记录
        """

        def do_record() -> None:
            try:
                from django.db import connection, transaction
                from django.utils import timezone

                connection.ensure_connection()

                with transaction.atomic():
                    DocumentQueryHistory.objects.get_or_create(
                        credential_id=credential_id,
                        case_number=entry.case_number,
                        send_time=entry.send_time,
                        defaults={"queried_at": timezone.now()},
                    )
                logger.debug(f"记录查询历史成功: {entry.case_number} - {entry.send_time}")
            except Exception as e:
                logger.warning(f"记录查询历史失败: {e!s}")

        thread = threading.Thread(target=do_record)
        thread.start()
        thread.join(timeout=10)

    def _process_sms_in_thread(
        self, record: DocumentDeliveryRecord, file_path: str, extracted_files: list[str], credential_id: int
    ) -> dict[str, Any]:
        """
        在独立线程中执行 SMS 处理流程,避免异步上下文问题

        流程:创建 CourtSMS: record: 文书记录
            file_path: 文件路径
            extracted_files: 解压后的文件列表
            credential_id: 账号凭证 ID

        Returns:
            处理结果字典
        """
        result_queue: queue.Queue[dict[str, Any]] = queue.Queue()

        def do_process() -> None:
            try:
                from django.db import connection
                from django.utils import timezone

                from apps.automation.models import CourtSMS, CourtSMSStatus

                connection.ensure_connection()

                result: dict[str, Any] = {
                    "success": False,
                    "case_id": None,
                    "case_log_id": None,
                    "renamed_path": file_path,
                    "notification_sent": False,
                    "error_message": None,
                }

                # 1. 创建 CourtSMS 记录
                logger.info(f"创建 CourtSMS 记录: 案号={record.case_number}")
                case_numbers_list: list[Any] = [record.case_number]
                sms = CourtSMS.objects.create(  # type: ignore
                    content=f"文书送达自动下载: {record.case_number}",
                    received_at=record.send_time,
                    status=CourtSMSStatus.MATCHING,
                    case_numbers=case_numbers_list,
                    sms_type="document_delivery",
                )
                logger.info(f"CourtSMS 创建成功: ID={sms.id}")

                # 2. 案件匹配 - 先通过案号,失败后从文书提取当事人匹配
                sms_id = sms.id
                logger.info(f"开始案件匹配: SMS ID={sms_id}, 案号={record.case_number}")
                matched_case = self._match_case_by_number(record.case_number)

                # 如果案号匹配失败,尝试从文书中提取当事人进行匹配
                if not matched_case:
                    logger.info("案号匹配失败,尝试从文书中提取当事人进行匹配")
                    matched_case = self._match_case_by_document_parties(extracted_files)

                if matched_case:
                    # 直接设置外键 ID,避免跨模块 Model 导入
                    sms.case_id = cast(int, matched_case.id)
                    sms.status = CourtSMSStatus.RENAMING
                    sms.save()
                    result["case_id"] = cast(int, matched_case.id)
                    sms_id = sms.id
                    case_id = cast(int, matched_case.id)
                    logger.info(f"案件匹配成功: SMS ID={sms_id}, Case ID={case_id}")

                    # 3. 将案号写入案件(如果案件还没有这个案号)
                    self._sync_case_number_to_case(cast(int, matched_case.id), record.case_number)

                    # 4. 重命名文书并添加到案件日志
                    renamed_files, case_log_id = self._rename_and_attach_documents(
                        sms=sms, case=matched_case, extracted_files=extracted_files
                    )

                    if renamed_files:
                        result["renamed_path"] = renamed_files[0] if renamed_files else file_path
                    if case_log_id:
                        result["case_log_id"] = case_log_id
                        sms.case_log_id = case_log_id

                    sms.status = CourtSMSStatus.NOTIFYING
                    sms.save()

                    # 5. 发送通知
                    notification_sent = self._send_notification(sms, renamed_files or extracted_files)
                    result["notification_sent"] = notification_sent

                    if notification_sent:
                        sms.status = CourtSMSStatus.COMPLETED
                        sms.feishu_sent_at = timezone.now()
                        sms_id = sms.id
                        logger.info(f"通知发送成功: SMS ID={sms_id}")
                    else:
                        sms.status = CourtSMSStatus.FAILED
                        sms.error_message = _("通知发送失败")  # type: ignore
                        sms_id = sms.id
                        logger.warning(f"通知发送失败: SMS ID={sms_id}")

                    sms.save()
                    result["success"] = True

                else:
                    # 未匹配到案件,标记为待人工处理
                    sms.status = CourtSMSStatus.PENDING_MANUAL
                    sms.error_message = f"未能匹配到案件: {record.case_number}"
                    sms.save()
                    result["error_message"] = sms.error_message
                    result["success"] = True  # 下载成功,只是匹配失败
                    sms_id = sms.id
                    logger.warning(f"案件匹配失败,待人工处理: SMS ID={sms_id}")

                result_queue.put(result)

            except Exception as e:
                logger.error(f"SMS 处理失败: {e!s}")
                result_queue.put({"success": False, "error_message": str(e)})

        thread = threading.Thread(target=do_process)
        thread.start()
        thread.join(timeout=60)

        if not result_queue.empty():
            return result_queue.get()

        return {"success": False, "error_message": "SMS 处理超时"}

    def _match_case_by_number(self, case_number: str) -> Any:
        """
        通过案号匹配案件

        委托给 CaseMatcher 执行,统一案件匹配逻辑

        Args:
            case_number: 案号

        Returns:
            匹配的案件或 None

        Requirements: 3.1
        """
        return self.case_matcher.match_by_case_number([case_number])

    def _match_case_by_document_parties(self, document_paths: list[str]) -> Any:
        """
        从文书中提取当事人进行案件匹配

        委托给 CaseMatcher 执行,统一案件匹配逻辑

        Args:
            document_paths: 文书路径列表

        Returns:
            匹配的案件或 None

        Requirements: 3.1
        """
        try:
            from apps.core.models.enums import CaseStatus

            for doc_path in document_paths:
                logger.info(f"尝试从文书中提取当事人: {doc_path}")

                # 使用 CaseMatcher 从文书中提取当事人
                extracted_parties = self.case_matcher.extract_parties_from_document(doc_path)

                if not extracted_parties:
                    logger.info(f"从文书 {doc_path} 中未能提取到当事人")
                    continue

                logger.info(f"从文书中提取到当事人: {extracted_parties}")

                # 使用 CaseMatcher 通过当事人匹配案件
                matched_case = self.case_matcher.match_by_party_names(extracted_parties)

                if matched_case:
                    # 检查案件状态
                    if matched_case.status == CaseStatus.ACTIVE:
                        logger.info(f"通过文书当事人匹配到在办案件: Case ID={matched_case.id}")
                        return matched_case
                    else:
                        logger.info(f"匹配到案件但状态为 {matched_case.status},继续尝试")
                        continue
                else:
                    logger.info(f"当事人 {extracted_parties} 未匹配到案件")

            logger.info("所有文书都未能匹配到在办案件")
            return None

        except Exception as e:
            logger.warning(f"从文书提取当事人匹配失败: {e!s}")
            return None

    def _sync_case_number_to_case(self, case_id: int, case_number: str) -> bool:
        """
        将案号同步到案件(如果案件还没有这个案号)

        Args:
            case_id: 案件 ID
            case_number: 案号

        Returns:
            是否成功同步
        """
        try:
            case_number_service = ServiceLocator.get_case_number_service()

            # 检查案件是否已有这个案号
            existing_numbers = case_number_service.list_numbers_internal(case_id=case_id)

            for num in existing_numbers:
                if num.number == case_number:
                    logger.info(f"案件 {case_id} 已有案号 {case_number},无需同步")
                    return True

            # 创建新案号
            case_number_service.create_number_internal(
                case_id=case_id, number=case_number, remarks="文书送达自动下载同步"
            )

            logger.info(f"案号同步成功: Case ID={case_id}, 案号={case_number}")
            return True

        except Exception as e:
            logger.warning(f"案号同步失败: Case ID={case_id}, 案号={case_number}, 错误: {e!s}")
            return False

    def _rename_and_attach_documents(
        self, sms: Any, case: Any, extracted_files: list[str]
    ) -> tuple[list[str], int | None]:
        """
        重命名文书并添加到案件日志

        Args:
            sms: CourtSMS 实例
            case: 案件实例
            extracted_files: 文件路径列表

        Returns:
            (重命名后的文件列表, 案件日志 ID)
        """
        renamed_files: list[str] = []
        case_log_id: int | None = None

        try:
            # 使用 DocumentRenamer 重命名文书
            for file_path in extracted_files:
                try:
                    renamed_path = self.document_renamer.rename(
                        document_path=file_path, case_name=case.name, received_date=date.today()
                    )
                    if renamed_path:
                        renamed_files.append(renamed_path)
                        logger.info(f"文书重命名成功: {file_path} -> {renamed_path}")
                    else:
                        renamed_files.append(file_path)
                except Exception as e:
                    logger.warning(f"文书重命名失败: {file_path}, 错误: {e!s}")
                    renamed_files.append(file_path)

            # 创建案件日志
            if renamed_files:
                case_log_service = ServiceLocator.get_caselog_service()
                file_names: list[Any] = []
                case_log = case_log_service.create_log(
                    case_id=cast(int, case.id),
                    content=f"文书送达自动下载: {', '.join(file_names)}",
                    user=None,  # 系统自动操作
                )
                if case_log:
                    case_log_id = cast(int, case_log.id)
                    logger.info(f"案件日志创建成功: CaseLog ID={case_log_id}")

                    # 添加附件 - 使用 Django 文件上传方式
                    from django.core.files.uploadedfile import SimpleUploadedFile

                    for file_path in renamed_files:
                        try:
                            if Path(file_path).exists():
                                with open(file_path, "rb") as f:
                                    file_content = f.read()
                                file_name = Path(file_path).name
                                uploaded_file = SimpleUploadedFile(
                                    name=file_name, content=file_content, content_type="application/octet-stream"
                                )
                                files_list: list[Any] = [uploaded_file]
                                case_log_service.upload_attachments(
                                    log_id=cast(int, case_log.id),
                                    files=files_list,
                                    user=None,
                                    perm_open_access=True,  # 系统操作,跳过权限检查
                                )
                                logger.info(f"附件上传成功: {file_name}")
                        except Exception as e:
                            logger.warning(f"添加附件失败: {file_path}, 错误: {e!s}")

        except Exception as e:
            logger.error(f"重命名和附件处理失败: {e!s}")

        return renamed_files, case_log_id

    def _send_notification(self, sms: Any, document_paths: list[str]) -> bool:
        """
        发送通知

        Args:
            sms: CourtSMS 实例
            document_paths: 文书路径列表

        Returns:
            是否发送成功
        """
        try:
            if not sms.case:
                logger.warning(f"SMS {sms.id} 未绑定案件,无法发送通知")
                return False

            return bool(self.notification_service.send_case_chat_notification(sms, document_paths))
        except Exception as e:
            logger.error(f"发送通知失败: {e!s}")
            return False
