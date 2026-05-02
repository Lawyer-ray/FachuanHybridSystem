"""法院自动化相关 Protocol 接口定义。"""

from __future__ import annotations

from typing import Any, Protocol


class IAutomationService(Protocol):
    """自动化服务接口"""

    def create_token_acquisition_history_internal(self, history_data: dict[str, Any]) -> Any: ...


class ICourtSMSService(Protocol):
    """法院短信处理服务接口"""

    def submit_sms(self, content: str, received_at: Any | None = None, sender: str | None = None) -> Any: ...

    def get_sms_detail(self, sms_id: int) -> Any: ...

    def list_sms(
        self,
        status: str | None = None,
        sms_type: str | None = None,
        has_case: bool | None = None,
        date_from: Any | None = None,
        date_to: Any | None = None,
    ) -> list[Any]: ...

    def assign_case(self, sms_id: int, case_id: int) -> Any: ...

    def retry_processing(self, sms_id: int) -> Any: ...


class ICourtDocumentService(Protocol):
    """法院文书服务接口"""

    def create_document_from_api_data(
        self, scraper_task_id: int, api_data: dict[str, Any], case_id: int | None = None
    ) -> Any: ...

    def update_download_status(
        self,
        document_id: int,
        status: str,
        local_file_path: str | None = None,
        file_size: int | None = None,
        error_message: str | None = None,
    ) -> Any: ...

    def get_documents_by_task(self, scraper_task_id: int) -> list[Any]: ...

    def get_document_by_id(self, document_id: int) -> Any | None: ...


class ICourtDocumentRecognitionService(Protocol):
    """法院文书智能识别服务接口"""

    def recognize_document(self, file_path: str, user: Any | None = None) -> Any: ...

    def recognize_document_from_text(self, text: str) -> Any: ...
