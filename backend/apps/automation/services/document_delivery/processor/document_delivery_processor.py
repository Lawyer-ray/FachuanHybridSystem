"""
文书处理服务

负责文书的下载后处理：解压 ZIP、创建 CourtSMS、案件匹配、重命名文书、发送通知。
从 DocumentDeliveryService 中解耦出来，遵循单一职责原则。

Requirements: 1.1, 1.3, 3.3, 5.1, 5.2, 5.5
"""

import logging
import queue
import tempfile
import threading
import zipfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from django.utils.translation import gettext_lazy as _

from apps.automation.models import DocumentQueryHistory
from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord, DocumentProcessResult

if TYPE_CHECKING:
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.document_renamer import DocumentRenamer
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService
    from apps.core.interfaces import ICaseLogService, ICaseNumberService

logger = logging.getLogger("apps.automation")


class DocumentDeliveryProcessor:
    """文书处理服务 - 负责文书下载后的处理流程"""

    def __init__(
        self,
        case_matcher: Optional["CaseMatcher"] = None,
        document_renamer: Optional["DocumentRenamer"] = None,
        notification_service: Optional["SMSNotificationService"] = None,
        caselog_service: Optional["ICaseLogService"] = None,
        case_number_service: Optional["ICaseNumberService"] = None,
    ):
        """初始化文书处理服务，支持依赖注入"""
        self._case_matcher = case_matcher
        self._document_renamer = document_renamer
        self._notification_service = notification_service
        self._caselog_service = caselog_service
        self._case_number_service = case_number_service
        logger.debug("DocumentDeliveryProcessor 初始化完成")

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

    @property
    def caselog_service(self) -> "ICaseLogService":
        """延迟加载案件日志服务"""
        if self._caselog_service is None:
            from apps.core.dependencies.business_case import build_case_log_service

            self._caselog_service = build_case_log_service()
        return self._caselog_service

    @property
    def case_number_service(self) -> "ICaseNumberService":
        """延迟加载案号服务"""
        if self._case_number_service is None:
            from apps.core.dependencies.business_case import build_case_number_service

            self._case_number_service = build_case_number_service()
        return self._case_number_service

    def process_downloaded_document(
        self, file_path: str, record: DocumentDeliveryRecord, credential_id: int
    ) -> DocumentProcessResult:
        """处理下载的文书 - 解压文件后在独立线程中执行后续处理"""
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
            extracted_files = self.extract_zip_if_needed(file_path)
            logger.info(f"文书下载完成: 案号={record.case_number}")
            if extracted_files:
                logger.info(f"ZIP 解压完成: {len(extracted_files)} 个文件")

            process_result = self.process_sms_in_thread(
                record=record,
                file_path=file_path,
                extracted_files=extracted_files or [file_path],
                credential_id=credential_id,
            )

            result.success = process_result.get("success", False)
            result.case_id = process_result.get("case_id")
            result.case_log_id = process_result.get("case_log_id")
            result.renamed_path = process_result.get("renamed_path", file_path)
            result.notification_sent = process_result.get("notification_sent", False)
            result.error_message = process_result.get("error_message")
        except Exception as e:
            result.error_message = f"处理下载文书失败: {e!s}"
            logger.error(result.error_message)

        return result

    def process_sms_in_thread(
        self, record: DocumentDeliveryRecord, file_path: str, extracted_files: list[str], credential_id: int
    ) -> dict[str, Any]:
        """在独立线程中执行 SMS 处理流程"""
        result_queue: queue.Queue[dict[str, Any]] = queue.Queue()

        def do_process() -> None:
            try:
                from django.db import connection
                from django.utils import timezone

                from apps.automation.models import CourtSMSStatus
                from apps.automation.services.sms.court_sms_dedup_service import CourtSMSDedupService

                connection.ensure_connection()
                result = {
                    "success": False,
                    "case_id": None,
                    "case_log_id": None,
                    "renamed_path": file_path,
                    "notification_sent": False,
                    "error_message": None,
                }

                # 1. 创建或复用 CourtSMS 记录
                dedup_service = CourtSMSDedupService()
                dedup_result = dedup_service.get_or_create_document_delivery_sms(
                    record=record,
                    extracted_files=extracted_files,
                    status=CourtSMSStatus.MATCHING,
                )
                sms = dedup_result.sms
                if not dedup_result.created:
                    logger.info(
                        f"命中文书送达重复事件，跳过后续处理: SMS ID={sms.id}, 案号={record.case_number}"
                    )
                    result.update(dedup_service.build_existing_sms_result(sms, file_path))
                    result_queue.put(result)
                    return
                logger.info(f"CourtSMS 创建成功: ID={sms.id}")

                # 2. 案件匹配
                matched_case = self.match_case_by_number(record.case_number)
                if not matched_case:
                    matched_case = self.match_case_by_document_parties(extracted_files)

                if matched_case:
                    sms.case_id = matched_case.id
                    sms.status = CourtSMSStatus.RENAMING
                    sms.save()
                    result["case_id"] = matched_case.id
                    logger.info(f"案件匹配成功: Case ID={matched_case.id}")

                    # 3. 同步案号
                    self.sync_case_number_to_case(matched_case.id, record.case_number)

                    # 4. 重命名文书并添加到案件日志
                    renamed_files, case_log_id = self.rename_and_attach_documents(
                        sms=sms, case=matched_case, extracted_files=extracted_files
                    )
                    if renamed_files:
                        result["renamed_path"] = renamed_files[0]
                        self.archive_to_case_folder(sms=sms, renamed_paths=renamed_files)
                    if case_log_id:
                        result["case_log_id"] = case_log_id
                        sms.case_log_id = case_log_id

                    sms.status = CourtSMSStatus.NOTIFYING
                    sms.save()

                    # 5. 发送通知
                    notification_sent = self.send_notification(sms, renamed_files or extracted_files)
                    result["notification_sent"] = notification_sent

                    if notification_sent:
                        sms.status = CourtSMSStatus.COMPLETED
                        sms.feishu_sent_at = timezone.now()
                    else:
                        sms.status = CourtSMSStatus.FAILED
                        sms.error_message = _("通知发送失败")
                    sms.save()
                    result["success"] = True
                else:
                    sms.status = CourtSMSStatus.PENDING_MANUAL
                    sms.error_message = f"未能匹配到案件: {record.case_number}"
                    sms.save()
                    result["error_message"] = sms.error_message
                    result["success"] = True
                    logger.warning(f"案件匹配失败，待人工处理: SMS ID={sms.id}")

                result_queue.put(result)
            except Exception as e:
                logger.error(f"SMS 处理失败: {e!s}")
                result_queue.put({"success": False, "error_message": str(e)})

        thread = threading.Thread(target=do_process)
        thread.start()
        thread.join(timeout=60)

        return result_queue.get() if not result_queue.empty() else {"success": False, "error_message": "SMS 处理超时"}

    def record_query_history_in_thread(self, credential_id: int, entry: DocumentDeliveryRecord) -> None:
        """在独立线程中记录查询历史"""

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
            except Exception as e:
                logger.warning(f"记录查询历史失败: {e!s}")

        thread = threading.Thread(target=do_record)
        thread.start()
        thread.join(timeout=10)

    def match_case_by_number(self, case_number: str) -> Any:
        """
        通过案号匹配案件

        委托给 CaseMatcher 执行，统一案件匹配逻辑
        Requirements: 3.1
        """
        return self.case_matcher.match_by_case_number([case_number])

    def match_case_by_document_parties(self, document_paths: list[str]) -> Any:
        """
        从文书中提取当事人进行案件匹配

        委托给 CaseMatcher 执行，统一案件匹配逻辑
        Requirements: 3.1
        """
        try:
            from apps.core.models.enums import CaseStatus

            for doc_path in document_paths:
                extracted_parties = self.case_matcher.extract_parties_from_document(doc_path)
                if not extracted_parties:
                    continue

                logger.info(f"从文书中提取到当事人: {extracted_parties}")
                matched_case = self.case_matcher.match_by_party_names(extracted_parties)

                if matched_case and matched_case.status == CaseStatus.ACTIVE:
                    logger.info(f"通过文书当事人匹配到在办案件: Case ID={matched_case.id}")
                    return matched_case
            return None
        except Exception as e:
            logger.warning(f"从文书提取当事人匹配失败: {e!s}")
            return None

    def rename_and_attach_documents(self, sms: Any, case: Any, extracted_files: list[str]) -> tuple[Any, ...]:
        """重命名文书并添加到案件日志"""
        renamed_files = []
        case_log_id = None

        try:
            for file_path in extracted_files:
                try:
                    renamed_path = self.document_renamer.rename(
                        document_path=file_path, case_name=case.name, received_date=date.today()
                    )
                    renamed_files.append(renamed_path if renamed_path else file_path)
                except Exception as e:
                    logger.warning(f"文书重命名失败: {file_path}, 错误: {e!s}")
                    renamed_files.append(file_path)

            if renamed_files:
                system_user = self._get_system_user()
                if system_user is None:
                    logger.error("未找到系统用户，无法创建案件日志")
                    return renamed_files, case_log_id

                case_log_service = self.caselog_service
                file_names = [Path(f).name for f in renamed_files]
                case_log = case_log_service.create_log(
                    case_id=case.id,
                    content=f"文书送达自动下载: {', '.join(file_names)}",
                    user=system_user,
                )
                if case_log:
                    case_log_id = case_log.id
                    self._upload_attachments(case_log_service, case_log.id, renamed_files)
        except Exception as e:
            logger.error(f"重命名和附件处理失败: {e!s}")

        return renamed_files, case_log_id

    def _upload_attachments(self, case_log_service: Any, log_id: int, file_paths: list[str]) -> None:
        """上传附件到案件日志"""
        from django.core.files.uploadedfile import SimpleUploadedFile

        for file_path in file_paths:
            try:
                if Path(file_path).exists():
                    with open(file_path, "rb") as f:
                        file_content = f.read()
                    uploaded_file = SimpleUploadedFile(
                        name=Path(file_path).name, content=file_content, content_type="application/octet-stream"
                    )
                    case_log_service.upload_attachments(
                        log_id=log_id, files=[uploaded_file], user=None, perm_open_access=True
                    )
            except Exception as e:
                logger.warning(f"添加附件失败: {file_path}, 错误: {e!s}")

    def _get_system_user(self) -> Any | None:
        """获取系统操作用户（管理员律师）"""
        try:
            from apps.core.interfaces import ServiceLocator

            lawyer_service = ServiceLocator.get_lawyer_service()
            admin_lawyer = lawyer_service.get_admin_lawyer()
            if not admin_lawyer:
                return None
            return lawyer_service.get_lawyer_model(admin_lawyer.id)
        except Exception as e:
            logger.warning(f"获取系统用户失败: {e!s}")
            return None

    def archive_to_case_folder(self, sms: Any, renamed_paths: list[str]) -> None:
        """将文书归档到案件绑定目录（不影响主流程）"""
        if not sms.case_id or not renamed_paths:
            return

        try:
            from apps.automation.services.sms.case_folder_archive_service import CaseFolderArchiveService

            archived = CaseFolderArchiveService().archive_sms_documents(sms, renamed_paths)
            if archived:
                logger.info(f"短信 {sms.id} 已归档到案件绑定目录")
        except Exception as e:
            logger.warning(f"短信 {sms.id} 归档到案件绑定目录失败，不影响主流程: {e!s}")

    def send_notification(self, sms: Any, document_paths: list[str]) -> bool:
        """发送通知"""
        try:
            if not sms.case:
                logger.warning(f"SMS {sms.id} 未绑定案件，无法发送通知")
                return False
            sent = self.notification_service.send_case_chat_notification(sms, document_paths)
            return bool(sent)
        except Exception as e:
            logger.error(f"发送通知失败: {e!s}")
            return False

    def extract_zip_if_needed(self, file_path: str) -> list[str] | None:
        """如果是 ZIP 文件则解压，返回解压后的文件列表"""
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

            extracted_files = []
            for root, _dirs, files in Path(extract_dir).walk():
                for file in files:
                    extracted_files.append(str(root / file))

            logger.info(f"ZIP 解压成功: {len(extracted_files)} 个文件")
            return extracted_files
        except Exception as e:
            logger.error(f"ZIP 解压失败: {e!s}")
            return None

    def sync_case_number_to_case(self, case_id: int, case_number: str) -> bool:
        """将案号同步到案件（如果案件还没有这个案号）"""
        try:
            case_number_service = self.case_number_service

            list_method = getattr(case_number_service, "list_numbers_internal", None)
            if list_method is None:
                list_method = getattr(case_number_service, "list_numbers", None)

            create_method = getattr(case_number_service, "create_number_internal", None)
            if create_method is None:
                create_method = getattr(case_number_service, "create_number", None)

            if list_method is None or create_method is None:
                logger.warning("案号服务不支持查询或创建方法，跳过案号同步")
                return False

            existing_numbers = list_method(case_id=case_id)
            for num in existing_numbers:
                if getattr(num, "number", None) == case_number:
                    return True

            create_method(case_id=case_id, number=case_number, remarks="文书送达自动下载同步")
            logger.info(f"案号同步成功: Case ID={case_id}, 案号={case_number}")
            return True
        except Exception as e:
            logger.warning(f"案号同步失败: {e!s}")
            return False
