"""文书送达匹配 Mixin — 案件匹配、重命名、通知、案号同步"""

import logging
import queue
import threading
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext_lazy as _

from .data_classes import DocumentDeliveryRecord

if TYPE_CHECKING:
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.document_renamer import DocumentRenamer
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService
    from apps.core.interfaces import ICaseLogService, ICaseNumberService

from abc import abstractmethod

logger = logging.getLogger("apps.automation")


class DocumentDeliveryMatchingMixin:
    """案件匹配、重命名、通知相关方法"""

    @property
    @abstractmethod
    def case_matcher(self) -> "CaseMatcher": ...

    @property
    @abstractmethod
    def document_renamer(self) -> "DocumentRenamer": ...

    @property
    @abstractmethod
    def notification_service(self) -> "SMSNotificationService": ...

    def __init__(
        self,
        caselog_service: "ICaseLogService | None" = None,
        case_number_service: "ICaseNumberService | None" = None,
    ) -> None:
        self._caselog_service = caselog_service
        self._case_number_service = case_number_service

    @property
    def caselog_service(self) -> "ICaseLogService":
        if self._caselog_service is None:
            from apps.core.dependencies import build_case_log_service

            self._caselog_service = build_case_log_service()
        return self._caselog_service

    @property
    def case_number_service(self) -> "ICaseNumberService":
        if self._case_number_service is None:
            from apps.core.dependencies import build_case_number_service

            self._case_number_service = build_case_number_service()
        return self._case_number_service

    def _match_case_by_number(self, case_number: str) -> Any:
        """通过案号匹配案件"""
        return self.case_matcher.match_by_case_number([case_number])

    def _match_case_by_document_parties(self, document_paths: list[str]) -> Any:
        """从文书中提取当事人进行案件匹配"""
        try:
            from apps.core.models.enums import CaseStatus

            for doc_path in document_paths:
                logger.info(f"尝试从文书中提取当事人: {doc_path}")
                extracted_parties = self.case_matcher.extract_parties_from_document(doc_path)
                if not extracted_parties:
                    logger.info(f"从文书 {doc_path} 中未能提取到当事人")
                    continue
                logger.info(f"从文书中提取到当事人: {extracted_parties}")
                matched_case = self.case_matcher.match_by_party_names(extracted_parties)
                if matched_case:
                    if matched_case.status == CaseStatus.ACTIVE:
                        logger.info(f"通过文书当事人匹配到在办案件: Case ID={matched_case.id}")
                        return matched_case
                    logger.info(f"匹配到案件但状态为 {matched_case.status}，继续尝试")
                else:
                    logger.info(f"当事人 {extracted_parties} 未匹配到案件")
            logger.info("所有文书都未能匹配到在办案件")
            return None
        except Exception as e:
            logger.warning(f"从文书提取当事人匹配失败: {e!s}")
            return None

    def _rename_and_attach_documents(self, sms: Any, case: Any, extracted_files: list[str]) -> tuple[Any, ...]:
        """重命名文书并添加到案件日志"""
        renamed_files: list[str] = []
        case_log_id = None
        try:
            for file_path in extracted_files:
                try:
                    renamed_path = self.document_renamer.rename(
                        document_path=file_path,
                        case_name=case.name,
                        received_date=date.today(),
                    )
                    renamed_files.append(renamed_path if renamed_path else file_path)
                    if renamed_path:
                        logger.info(f"文书重命名成功: {file_path} -> {renamed_path}")
                except Exception as e:
                    logger.warning(f"文书重命名失败: {file_path}, 错误: {e!s}")
                    renamed_files.append(file_path)

            if renamed_files:
                case_log_service = self.caselog_service
                file_names = [f.split("/")[-1] for f in renamed_files]
                case_log = case_log_service.create_log(
                    case_id=case.id,
                    content=f"文书送达自动下载: {', '.join(file_names)}",
                    user=None,
                )
                if case_log:
                    case_log_id = case_log.id
                    logger.info(f"案件日志创建成功: CaseLog ID={case_log_id}")
                    from django.core.files.uploadedfile import SimpleUploadedFile

                    for file_path in renamed_files:
                        try:
                            if Path(file_path).exists():
                                with open(file_path, "rb") as f:
                                    file_content = f.read()
                                uploaded_file = SimpleUploadedFile(
                                    name=Path(file_path).name,
                                    content=file_content,
                                    content_type="application/octet-stream",
                                )
                                case_log_service.upload_attachments(
                                    log_id=case_log.id,
                                    files=[uploaded_file],
                                    user=None,
                                    perm_open_access=True,
                                )
                                logger.info(f"附件上传成功: {Path(file_path).name}")
                        except Exception as e:
                            logger.warning(f"添加附件失败: {file_path}, 错误: {e!s}")
        except Exception as e:
            logger.error(f"重命名和附件处理失败: {e!s}")
        return renamed_files, case_log_id

    def _send_notification(self, sms: Any, document_paths: list[str]) -> bool:
        """发送通知"""
        try:
            if not sms.case:
                logger.warning(f"SMS {sms.id} 未绑定案件，无法发送通知")
                return False
            return self.notification_service.send_case_chat_notification(sms, document_paths)
        except Exception as e:
            logger.error(f"发送通知失败: {e!s}")
            return False

    def _sync_case_number_to_case(self, case_id: int, case_number: str) -> bool:
        """将案号同步到案件"""
        try:
            case_number_service = self.case_number_service
            existing_numbers = case_number_service.list_numbers(case_id=case_id)  # type: ignore
            for num in existing_numbers:
                if num.number == case_number:
                    logger.info(f"案件 {case_id} 已有案号 {case_number}，无需同步")
                    return True
            case_number_service.create_number(  # type: ignore
                case_id=case_id,
                number=case_number,
                remarks="文书送达自动下载同步",
            )
            logger.info(f"案号同步成功: Case ID={case_id}, 案号={case_number}")
            return True
        except Exception as e:
            logger.warning(f"案号同步失败: Case ID={case_id}, 案号={case_number}, 错误: {e!s}")
            return False

    def _process_sms_in_thread(
        self,
        record: DocumentDeliveryRecord,
        file_path: str,
        extracted_files: list[str],
        credential_id: int,
    ) -> dict[str, Any]:
        """在独立线程中执行 SMS 处理流程"""
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

                logger.info(f"创建 CourtSMS 记录: 案号={record.case_number}")
                sms = CourtSMS.objects.create(
                    content=f"文书送达自动下载: {record.case_number}",
                    received_at=record.send_time,
                    status=CourtSMSStatus.MATCHING,
                    case_numbers=[record.case_number],
                    sms_type="document_delivery",
                )
                logger.info(f"CourtSMS 创建成功: ID={sms.id}")

                matched_case = self._match_case_by_number(record.case_number)
                if not matched_case:
                    logger.info("案号匹配失败，尝试从文书中提取当事人进行匹配")
                    matched_case = self._match_case_by_document_parties(extracted_files)

                if matched_case:
                    sms.case_id = matched_case.id
                    sms.status = CourtSMSStatus.RENAMING
                    sms.save()
                    result["case_id"] = matched_case.id
                    logger.info(f"案件匹配成功: SMS ID={sms.id}, Case ID={matched_case.id}")

                    self._sync_case_number_to_case(matched_case.id, record.case_number)

                    renamed_files, case_log_id = self._rename_and_attach_documents(
                        sms=sms, case=matched_case, extracted_files=extracted_files
                    )
                    if renamed_files:
                        result["renamed_path"] = renamed_files[0]
                    if case_log_id:
                        result["case_log_id"] = case_log_id
                        sms.case_log_id = case_log_id

                    sms.status = CourtSMSStatus.NOTIFYING
                    sms.save()

                    notification_sent = self._send_notification(sms, renamed_files or extracted_files)
                    result["notification_sent"] = notification_sent

                    if notification_sent:
                        sms.status = CourtSMSStatus.COMPLETED
                        sms.feishu_sent_at = timezone.now()
                        logger.info(f"通知发送成功: SMS ID={sms.id}")
                    else:
                        sms.status = CourtSMSStatus.FAILED
                        sms.error_message = _("通知发送失败")
                        logger.warning(f"通知发送失败: SMS ID={sms.id}")

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
        if not result_queue.empty():
            return result_queue.get()
        return {"success": False, "error_message": "SMS 处理超时"}
