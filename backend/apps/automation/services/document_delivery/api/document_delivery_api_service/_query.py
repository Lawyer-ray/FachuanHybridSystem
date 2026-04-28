"""文书送达 API 查询与分页逻辑"""

import logging
import math
import queue
import threading
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from apps.automation.models import DocumentQueryHistory
from apps.automation.services.document_delivery.data_classes import (
    DocumentDeliveryRecord,
    DocumentQueryResult,
    DocumentRecord,
)

if TYPE_CHECKING:
    from apps.automation.services.document_delivery.court_document_api_client import CourtDocumentApiClient

from abc import abstractmethod

logger = logging.getLogger("apps.automation")

__all__ = ["DocumentQueryMixin"]


class DocumentQueryMixin:
    """文书查询与分页 Mixin"""

    @property
    @abstractmethod
    def api_client(self) -> "CourtDocumentApiClient": ...

    def query_documents(self, token: str, cutoff_time: datetime, credential_id: int) -> DocumentQueryResult:
        """
        通过 API 查询文书

        Requirements: 1.1, 1.4, 3.4, 5.1
        """
        logger.info(f"开始 API 查询文书: cutoff_time={cutoff_time}")

        result = DocumentQueryResult(
            total_found=0, processed_count=0, skipped_count=0, failed_count=0, case_log_ids=[], errors=[]
        )

        page_size = 20
        page_num = 1

        try:
            first_response = self.api_client.fetch_document_list(token=token, page_num=page_num, page_size=page_size)

            total = first_response.total
            result.total_found = total

            logger.info(f"API 查询: 总文书数={total}")

            if total == 0:
                logger.info("没有文书需要处理")
                return result

            total_pages = math.ceil(total / page_size)
            logger.info(f"分页计算: total={total}, page_size={page_size}, total_pages={total_pages}")

            self._process_document_page(
                documents=first_response.documents,
                token=token,
                cutoff_time=cutoff_time,
                credential_id=credential_id,
                result=result,
            )

            for page_num in range(2, total_pages + 1):
                logger.info(f"处理第 {page_num}/{total_pages} 页")

                try:
                    page_response = self.api_client.fetch_document_list(
                        token=token, page_num=page_num, page_size=page_size
                    )
                    self._process_document_page(
                        documents=page_response.documents,
                        token=token,
                        cutoff_time=cutoff_time,
                        credential_id=credential_id,
                        result=result,
                    )
                except Exception as e:
                    error_msg = f"处理第 {page_num} 页失败: {e!s}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)
                    continue

        except Exception as e:
            error_msg = f"API 查询失败: {e!s}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            raise

        logger.info(
            f"API 查询完成: 发现={result.total_found}, 处理={result.processed_count}, "
            f"跳过={result.skipped_count}, 失败={result.failed_count}"
        )

        return result

    def _process_document_page(
        self,
        documents: list[Any],
        token: str,
        cutoff_time: datetime,
        credential_id: int,
        result: DocumentQueryResult,
    ) -> None:
        """处理一页文书记录"""
        for record in documents:
            try:
                logger.info(f"检查文书: {record.ah} - {record.fssj}")

                if not self.should_process_document(record, cutoff_time, credential_id):
                    result.skipped_count += 1
                    logger.info(f"跳过文书: {record.ah}")
                    continue

                logger.info(f"开始处理文书: {record.ah}")

                process_result = self.process_document(record=record, token=token, credential_id=credential_id)

                if process_result.success:
                    result.processed_count += 1
                    if process_result.case_log_id:
                        result.case_log_ids.append(process_result.case_log_id)
                    logger.info(f"文书处理成功: {record.ah}")
                else:
                    result.failed_count += 1
                    if process_result.error_message:
                        result.errors.append(process_result.error_message)
                    logger.warning(f"文书处理失败: {record.ah}, 错误: {process_result.error_message}")

            except Exception as e:
                result.failed_count += 1
                error_msg = f"处理文书 {record.ah} 失败: {e!s}"
                result.errors.append(error_msg)
                logger.error(error_msg)

    def should_process_document(self, record: DocumentRecord, cutoff_time: datetime, credential_id: int) -> bool:
        """
        判断是否需要处理该 API 文书记录

        Requirements: 3.1, 3.2, 3.3
        """
        send_time = record.parse_fssj()

        if send_time is None:
            logger.warning(f"无法解析发送时间: {record.fssj}, 默认处理")
            return True

        if timezone.is_aware(cutoff_time):
            send_time = timezone.make_aware(send_time)

        if send_time <= cutoff_time:
            logger.info(f"文书时间 {send_time} 早于截止时间 {cutoff_time}，跳过")
            return False

        return self._check_document_not_processed(credential_id, record)

    def _check_document_not_processed(self, credential_id: int, record: DocumentRecord) -> bool:
        """检查 API 文书是否已成功处理完成"""
        result_queue: queue.Queue[bool] = queue.Queue()

        def do_check() -> None:
            try:
                from django.db import connection

                from apps.automation.services.sms.court_sms_dedup_service import CourtSMSDedupService

                connection.ensure_connection()

                send_time = record.parse_fssj()
                if send_time:
                    send_time = timezone.make_aware(send_time)

                delivery_record = DocumentDeliveryRecord(
                    case_number=record.ah,
                    send_time=send_time,
                    element_index=0,
                    document_name=record.wsmc,
                    court_name=record.fymc,
                    delivery_event_id=record.sdbh,
                )
                existing_sms = CourtSMSDedupService().find_document_delivery_sms(delivery_record)

                if existing_sms:
                    logger.info(f"文书命中重复事件: {record.ah} - {record.fssj}, SMS ID={existing_sms.id}")
                    result_queue.put(False)
                else:
                    if send_time:
                        existing_history = DocumentQueryHistory.objects.filter(
                            credential_id=credential_id, case_number=record.ah, send_time=send_time
                        ).first()

                        if existing_history:
                            logger.info(f"文书有历史记录但未成功完成，重新处理: {record.ah}")
                            existing_history.delete()

                    logger.info(f"文书符合处理条件: {record.ah} - {record.fssj}")
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

    def _record_query_history_in_thread(self, credential_id: int, entry: DocumentDeliveryRecord) -> None:
        """在独立线程中记录查询历史"""

        def do_record() -> None:
            try:
                from django.db import connection, transaction

                connection.ensure_connection()

                with transaction.atomic():
                    DocumentQueryHistory.objects.get_or_create(
                        credential_id=credential_id,
                        case_number=entry.case_number,
                        send_time=entry.send_time,  # type: ignore[misc]
                        defaults={"queried_at": timezone.now()},
                    )
                logger.debug(f"记录查询历史成功: {entry.case_number} - {entry.send_time}")
            except Exception as e:
                logger.warning(f"记录查询历史失败: {e!s}")

        thread = threading.Thread(target=do_record)
        thread.start()
        thread.join(timeout=10)

    # 以下方法由子类实现
    def process_document(self, record: DocumentRecord, token: str, credential_id: int) -> Any:
        raise NotImplementedError
