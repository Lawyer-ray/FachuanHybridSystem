"""Data processing logic."""

from django.utils.translation import gettext_lazy as _
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord, DocumentProcessResult

    class _DataProcessorHost(Protocol):
        @property
        def history_repo(self) -> Any: ...
        @property
        def processor(self) -> Any: ...
        def _download_document(self, page: Any, entry: "DocumentDeliveryRecord") -> str | None: ...


logger = logging.getLogger("apps.automation")


class DataProcessorMixin:
    def _should_process(
        self: "_DataProcessorHost", record: "DocumentDeliveryRecord", cutoff_time: datetime, credential_id: int
    ) -> Any:
        if record.send_time is None or record.send_time <= cutoff_time:
            return False

        return self.history_repo.should_process(credential_id, record.case_number, record.send_time)

    def _process_document_entry(
        self: "_DataProcessorHost", page: Any, entry: "DocumentDeliveryRecord", credential_id: int
    ) -> "DocumentProcessResult":
        from apps.automation.services.document_delivery.data_classes import DocumentProcessResult

        result = DocumentProcessResult(
            success=False,
            case_id=None,
            case_log_id=None,
            renamed_path=None,
            notification_sent=False,
            error_message=None,
        )

        file_path = self._download_document(page, entry)
        if not file_path:
            result.error_message = str(_("文书下载失败"))
            return result

        process_result = self.processor.process_downloaded_document(
            file_path=file_path,
            record=entry,
            credential_id=credential_id,
        )

        result.success = process_result.success
        result.case_id = cast(int, process_result.case_id)
        result.case_log_id = process_result.case_log_id
        result.renamed_path = process_result.renamed_path
        result.notification_sent = process_result.notification_sent
        result.error_message = process_result.error_message

        return result
