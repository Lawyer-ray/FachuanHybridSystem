"""文书下载与 SMS 处理逻辑"""

import logging
import queue
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.automation.services.document_delivery.data_classes import (
    DocumentDeliveryRecord,
    DocumentProcessResult,
    DocumentRecord,
)

if TYPE_CHECKING:
    from apps.automation.services.document_delivery.court_document_api_client import CourtDocumentApiClient
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.document_renamer import DocumentRenamer
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService

from abc import abstractmethod

logger = logging.getLogger("apps.automation")

__all__ = ["DocumentProcessMixin"]


class DocumentProcessMixin:
    """文书下载与 SMS 处理 Mixin"""

    @property
    @abstractmethod
    def api_client(self) -> "CourtDocumentApiClient": ...

    @property
    @abstractmethod
    def case_matcher(self) -> "CaseMatcher": ...

    @property
    @abstractmethod
    def document_renamer(self) -> "DocumentRenamer": ...

    @property
    @abstractmethod
    def notification_service(self) -> "SMSNotificationService": ...

    def process_document(self, record: DocumentRecord, token: str, credential_id: int) -> DocumentProcessResult:
        """
        通过 API 处理单个文书

        Requirements: 2.1, 2.2, 2.3, 4.1, 4.2, 4.3
        """
        logger.info(f"开始 API 处理文书: {record.ah}, sdbh={record.sdbh}")

        result = DocumentProcessResult(
            success=False,
            case_id=None,
            case_log_id=None,
            renamed_path=None,
            notification_sent=False,
            error_message=None,
        )

        try:
            details = self.api_client.fetch_document_details(token=token, sdbh=record.sdbh)

            if not details:
                result.error_message = f"未获取到文书详情: sdbh={record.sdbh}"
                logger.warning(result.error_message)
                return result

            logger.info(f"获取到 {len(details)} 个文书下载链接")

            temp_dir = tempfile.mkdtemp(prefix="court_document_api_")
            downloaded_files: list[str] = []

            for detail in details:
                if not detail.wjlj:
                    logger.warning(f"文书缺少下载链接: {detail.c_wsmc}")
                    continue

                file_ext = detail.c_wjgs or "pdf"
                file_name = f"{detail.c_wsmc}.{file_ext}"
                save_path = Path(temp_dir) / file_name

                success = self.api_client.download_document(url=detail.wjlj, save_path=save_path)

                if success:
                    downloaded_files.append(str(save_path))
                    logger.info(f"文书下载成功: {file_name}")
                else:
                    logger.warning(f"文书下载失败: {file_name}")

            if not downloaded_files:
                result.error_message = str(_("所有文书下载失败"))
                logger.error(result.error_message)
                return result

            logger.info(f"成功下载 {len(downloaded_files)} 个文书")

            send_time = record.parse_fssj()
            if send_time:
                send_time = timezone.make_aware(send_time)
            else:
                send_time = timezone.now()

            delivery_record = DocumentDeliveryRecord(
                case_number=record.ah,
                send_time=send_time,
                element_index=0,
                document_name=record.wsmc,
                court_name=record.fymc,
                delivery_event_id=record.sdbh,
            )

            process_result = self._process_sms_in_thread(
                record=delivery_record,
                file_path=downloaded_files[0],
                extracted_files=downloaded_files,
                credential_id=credential_id,
            )

            self._record_query_history_in_thread(credential_id, delivery_record)

            result.success = process_result.get("success", False)
            result.case_id = process_result.get("case_id")
            result.case_log_id = process_result.get("case_log_id")
            result.renamed_path = process_result.get("renamed_path")
            result.notification_sent = process_result.get("notification_sent", False)
            result.error_message = process_result.get("error_message")

        except Exception as e:
            error_msg = f"API 处理文书失败: {e!s}"
            logger.error(error_msg)
            result.error_message = error_msg

        return result

    def _process_sms_in_thread(
        self, record: DocumentDeliveryRecord, file_path: str, extracted_files: list[str], credential_id: int
    ) -> dict[str, Any]:
        """在独立线程中执行 SMS 处理流程"""
        result_queue: queue.Queue[dict[str, Any]] = queue.Queue()

        def do_process() -> None:
            try:
                from django.db import connection

                from apps.automation.models import CourtSMSStatus
                from apps.automation.services.sms.court_sms_dedup_service import CourtSMSDedupService

                connection.ensure_connection()

                result: dict[str, Any] = {
                    "success": False,
                    "case_id": None,
                    "case_log_id": None,
                    "renamed_path": file_path,
                    "notification_sent": False,
                    "error_message": None,
                }

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

                logger.info(f"开始案件匹配: SMS ID={sms.id}, 案号={record.case_number}")
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
                        result["renamed_path"] = renamed_files[0] if renamed_files else file_path
                        archive_method = getattr(self, "_archive_to_case_folder", None)
                        if callable(archive_method):
                            archive_method(sms=sms, renamed_paths=renamed_files)
                    if case_log_id:
                        result["case_log_id"] = case_log_id
                        sms.case_log_id = case_log_id

                    sms.status = CourtSMSStatus.NOTIFYING
                    sms.save()

                    notification_sent = self._send_notification(sms, renamed_files or extracted_files)
                    result["notification_sent"] = notification_sent

                    if notification_sent:
                        sms.status = CourtSMSStatus.COMPLETED
                        logger.info(f"通知发送成功: SMS ID={sms.id}")
                    else:
                        sms.status = CourtSMSStatus.FAILED
                        sms.error_message = str(_("通知发送失败"))
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

    # 以下方法由子类实现
    def _match_case_by_number(self, case_number: str) -> Any:
        raise NotImplementedError

    def _match_case_by_document_parties(self, document_paths: list[str]) -> Any:
        raise NotImplementedError

    def _sync_case_number_to_case(self, case_id: int, case_number: str) -> bool:
        raise NotImplementedError

    def _rename_and_attach_documents(self, sms: Any, case: Any, extracted_files: list[str]) -> tuple[Any, ...]:
        raise NotImplementedError

    def _send_notification(self, sms: Any, document_paths: list[str]) -> bool:
        raise NotImplementedError

    def _record_query_history_in_thread(self, credential_id: int, entry: DocumentDeliveryRecord) -> None:
        raise NotImplementedError
