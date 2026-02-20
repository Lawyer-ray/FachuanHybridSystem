"""文书送达下载 Mixin — 文件下载、解压、历史记录"""

import logging
import os
from datetime import datetime
from pathlib import Path
import queue
import tempfile
import threading
import zipfile
from typing import Any

from playwright.sync_api import Page

from apps.automation.models import DocumentQueryHistory

from .data_classes import DocumentDeliveryRecord, DocumentProcessResult

logger = logging.getLogger("apps.automation")


class DocumentDeliveryDownloadingMixin:
    """文件下载相关方法"""

    DOWNLOAD_BUTTON_SELECTOR: str
    PAGE_LOAD_WAIT: int

    # 子类必须实现的方法（Protocol 声明）
    def _process_sms_in_thread(
        self,
        record: DocumentDeliveryRecord,
        file_path: str,
        extracted_files: list[str],
        credential_id: int,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _should_process(
        self, record: DocumentDeliveryRecord, cutoff_time: Any, credential_id: int
    ) -> bool:
        raise NotImplementedError

    def _download_document(self, page: Page, entry: DocumentDeliveryRecord) -> str | None:
        """点击下载按钮下载文书"""
        logger.info(f"开始下载文书: {entry.case_number}")
        try:
            download_buttons = page.locator(self.DOWNLOAD_BUTTON_SELECTOR).all()
            logger.info(f"找到 {len(download_buttons)} 个下载按钮")
            if entry.element_index >= len(download_buttons):
                logger.error(
                    f"下载按钮索引超出范围: {entry.element_index} >= {len(download_buttons)}"
                )
                return None
            download_button = download_buttons[entry.element_index]
            if not download_button.is_visible():
                logger.error(f"下载按钮不可见: {entry.case_number}")
                return None
            logger.info(f"点击第 {entry.element_index} 个下载按钮")
            with page.expect_download() as download_info:
                download_button.click()
            download = download_info.value
            temp_dir = tempfile.mkdtemp(prefix="court_document_")
            file_path = os.path.join(
                temp_dir, download.suggested_filename or f"{entry.case_number}.pdf"
            )
            download.save_as(file_path)
            logger.info(f"文书下载成功: {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"下载文书失败: {e!s}")
            return None

    def _process_downloaded_document(
        self,
        file_path: str,
        record: DocumentDeliveryRecord,
        credential_id: int,
    ) -> DocumentProcessResult:
        """处理下载的文书"""
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
            extracted_files = self._extract_zip_if_needed(file_path)
            logger.info(f"文书下载完成: 案号={record.case_number}, 文件={file_path}")
            if extracted_files:
                logger.info(f"ZIP 解压完成: {len(extracted_files)} 个文件")
            process_result = self._process_sms_in_thread(
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

    def _extract_zip_if_needed(self, file_path: str) -> list[str] | None:
        """如果是 ZIP 文件则解压，返回解压后的文件列表（安全逐文件解压，防 zip slip）"""
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
            for root, _dirs, files in os.walk(extract_dir):
                for file in files:
                    extracted_files.append(os.path.join(root, file))
            logger.info(f"ZIP 解压成功: {len(extracted_files)} 个文件")
            return extracted_files
        except Exception as e:
            logger.error(f"ZIP 解压失败: {e!s}")
            return None

    def _check_not_processed_in_thread(
        self, credential_id: int, record: DocumentDeliveryRecord
    ) -> bool:
        """在独立线程中检查文书是否已成功处理完成"""
        result_queue: queue.Queue[bool] = queue.Queue()
        send_time: datetime | None = record.send_time

        def do_check() -> None:
            try:
                from django.db import connection
                from apps.automation.models import CourtSMS, CourtSMSStatus

                connection.ensure_connection()
                completed_sms = CourtSMS.objects.filter(
                    case_numbers__contains=[record.case_number],
                    status=CourtSMSStatus.COMPLETED,
                ).first()
                if completed_sms:
                    logger.info(
                        f"🔄 文书已成功处理完成: {record.case_number}, SMS ID={completed_sms.id}"
                    )
                    result_queue.put(False)
                    return
                if send_time is not None:
                    existing_history = DocumentQueryHistory.objects.filter(
                        credential_id=credential_id,
                        case_number=record.case_number,
                        send_time=send_time,
                    ).first()
                    if existing_history:
                        logger.info(f"🔄 文书有历史记录但未成功完成，重新处理: {record.case_number}")
                        existing_history.delete()
                logger.info(f"🆕 文书符合处理条件: {record.case_number} - {send_time}")
                result_queue.put(True)
            except Exception as e:
                logger.warning(f"检查文书处理历史失败: {e!s}")
                result_queue.put(True)

        thread = threading.Thread(target=do_check)
        thread.start()
        thread.join(timeout=10)
        if not result_queue.empty():
            return result_queue.get()
        logger.warning("检查文书处理历史超时，默认处理")
        return True

    def _record_query_history_in_thread(
        self, credential_id: int, entry: DocumentDeliveryRecord
    ) -> None:
        """在独立线程中记录查询历史"""
        send_time: datetime | None = entry.send_time

        def do_record() -> None:
            try:
                from django.db import connection, transaction
                from django.utils import timezone

                connection.ensure_connection()
                if send_time is not None:
                    with transaction.atomic():
                        DocumentQueryHistory.objects.get_or_create(
                            credential_id=credential_id,
                            case_number=entry.case_number,
                            send_time=send_time,
                            defaults={"queried_at": timezone.now()},
                        )
                    logger.debug(f"记录查询历史成功: {entry.case_number} - {send_time}")
            except Exception as e:
                logger.warning(f"记录查询历史失败: {e!s}")

        thread = threading.Thread(target=do_record)
        thread.start()
        thread.join(timeout=10)
