"""文档处理与监控相关 Protocol 接口定义。"""

from __future__ import annotations

from typing import Any, Protocol


class IPreservationQuoteService(Protocol):
    """财产保全询价服务接口"""

    def create_quote(
        self,
        case_name: str,
        target_amount: Any,
        applicant_name: str,
        respondent_name: str,
        court_name: str,
        case_type: str = "财产保全",
        **kwargs: Any,
    ) -> Any: ...

    def execute_quote(self, quote_id: int, force_refresh_token: bool = False) -> dict[str, Any]: ...

    def get_quote_by_id(self, quote_id: int) -> Any | None: ...

    def list_quotes(self, status: str | None = None, limit: int = 20, offset: int = 0) -> dict[str, Any]: ...


class IDocumentProcessingService(Protocol):
    """文档处理服务接口"""

    def extract_text_from_pdf(
        self, file_path: str, limit: int | None = None, preview_page: int | None = None
    ) -> dict[str, Any]: ...

    def extract_text_from_docx(self, file_path: str, limit: int | None = None) -> str: ...

    def extract_text_from_image(self, file_path: str, limit: int | None = None) -> str: ...

    def process_uploaded_document(
        self, uploaded_file: Any, limit: int | None = None, preview_page: int | None = None
    ) -> dict[str, Any]: ...


class IAutoNamerService(Protocol):
    """自动命名服务接口"""

    def generate_filename(self, document_content: str, prompt: str | None = None, model: str = "qwen3:0.6b") -> str: ...

    def process_document_for_naming(
        self,
        uploaded_file: Any,
        prompt: str | None = None,
        model: str = "qwen3:0.6b",
        limit: int | None = None,
        preview_page: int | None = None,
    ) -> dict[str, Any]: ...


class IPerformanceMonitorService(Protocol):
    """性能监控服务接口"""

    def get_system_metrics(self) -> dict[str, Any]: ...

    def get_token_acquisition_metrics(self, hours: int = 24) -> dict[str, Any]: ...

    def get_api_performance_metrics(self, api_name: str | None = None, hours: int = 24) -> dict[str, Any]: ...

    def record_performance_metric(self, metric_name: str, value: float, tags: dict[str, str] | None = None) -> None: ...
