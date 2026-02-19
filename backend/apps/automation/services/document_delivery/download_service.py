"""
文书送达下载服务

负责文书下载、解压和文件处理逻辑.
"""

import logging
import tempfile
from typing import TYPE_CHECKING, Any, Optional

from apps.core.path import Path

from .api.document_delivery_api_service import DocumentDeliveryApiService
from .data_classes import DocumentDeliveryRecord, DocumentProcessResult, DocumentRecord
from .processor.document_delivery_processor import DocumentDeliveryProcessor
from .repo.document_history_repo import DocumentHistoryRepo

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.document_renamer import DocumentRenamer
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService
    from apps.core.interfaces import ICaseLogService, ICaseNumberService

    from .court_document_api_client import CourtDocumentApiClient

logger = logging.getLogger("apps.automation")


class DocumentDownloadService:
    """文书下载服务 - 负责下载和文件处理逻辑"""

    def __init__(
        self,
        api_client: Optional["CourtDocumentApiClient"] = None,
        case_matcher: Optional["CaseMatcher"] = None,
        document_renamer: Optional["DocumentRenamer"] = None,
        notification_service: Optional["SMSNotificationService"] = None,
        case_log_service: Optional["ICaseLogService"] = None,
        case_number_service: Optional["ICaseNumberService"] = None,
        processor: DocumentDeliveryProcessor | None = None,
        history_repo: DocumentHistoryRepo | None = None,
        api_service: DocumentDeliveryApiService | None = None,
    ) -> None:
        """
        初始化文书下载服务

        Args:
            api_client: API 客户端实例(可选,用于依赖注入)
            case_matcher: 案件匹配服务实例(可选,用于依赖注入)
            document_renamer: 文书重命名服务实例(可选,用于依赖注入)
            notification_service: 通知服务实例(可选,用于依赖注入)
        """
        self._api_client = api_client
        self._case_matcher = case_matcher
        self._document_renamer = document_renamer
        self._notification_service = notification_service
        self._case_log_service = case_log_service
        self._case_number_service = case_number_service
        self._processor = processor
        self._history_repo = history_repo
        self._api_service = api_service

        logger.debug("DocumentDownloadService 初始化完成")

    @property
    def processor(self) -> DocumentDeliveryProcessor:
        if self._processor is None:
            self._processor = DocumentDeliveryProcessor(
                case_matcher=self._case_matcher,
                document_renamer=self._document_renamer,
                notification_service=self._notification_service,
                case_log_service=self._case_log_service,
                case_number_service=self._case_number_service,
                history_repo=self._history_repo,
            )
        return self._processor

    @property
    def history_repo(self) -> DocumentHistoryRepo:
        if self._history_repo is None:
            self._history_repo = DocumentHistoryRepo()
        return self._history_repo

    @property
    def api_service(self) -> DocumentDeliveryApiService:
        if self._api_service is None:
            self._api_service = DocumentDeliveryApiService(
                api_client=self.api_client,
                processor=self.processor,
                history_repo=self.history_repo,
            )
        return self._api_service

    @property
    def api_client(self) -> "CourtDocumentApiClient":
        """延迟加载 API 客户端"""
        if self._api_client is None:
            from .court_document_api_client import CourtDocumentApiClient

            self._api_client = CourtDocumentApiClient()
        return self._api_client

    @property
    def case_matcher(self) -> "CaseMatcher":
        """延迟加载案件匹配服务"""
        return self.processor.case_matcher

    @property
    def document_renamer(self) -> "DocumentRenamer":
        """延迟加载文书重命名服务"""
        return self.processor.document_renamer

    @property
    def notification_service(self) -> "SMSNotificationService":
        """延迟加载通知服务"""
        return self.processor.notification_service

    # ==================== API 下载方法 ====================

    def process_document_via_api(self, record: DocumentRecord, token: str, credential_id: int) -> DocumentProcessResult:
        """
        通过 API 处理单个文书

        Args:
            record: 文书记录
            token: 认证令牌
            credential_id: 账号凭证 ID

        Returns:
            DocumentProcessResult: 处理结果
        """
        return self.api_service.process_document(record=record, token=token, credential_id=credential_id)

    # ==================== Playwright 下载方法 ====================

    def download_document_via_playwright(
        self, page: "Page", entry: DocumentDeliveryRecord, download_button_selector: str
    ) -> str | None:
        """
        点击下载按钮下载文书

        Args:
            page: Playwright 页面实例
            entry: 文书条目
            download_button_selector: 下载按钮选择器

        Returns:
            下载的文件路径
        """
        logger.info(f"开始下载文书: {entry.case_number}")

        try:
            download_buttons = page.locator(download_button_selector).all()
            logger.info(f"找到 {len(download_buttons)} 个下载按钮")

            if entry.element_index >= len(download_buttons):
                logger.error(f"下载按钮索引超出范围: {entry.element_index} >= {len(download_buttons)}")
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
            file_path = Path(temp_dir) / (download.suggested_filename or f"{entry.case_number}.pdf")

            download.save_as(file_path)

            logger.info(f"文书下载成功: {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"下载文书失败: {e!s}")
            return None

    def process_downloaded_document(
        self, file_path: str, record: DocumentDeliveryRecord, credential_id: int
    ) -> DocumentProcessResult:
        return self.processor.process_downloaded_document(
            file_path=file_path,
            record=record,
            credential_id=credential_id,
        )

    # ==================== 文件处理方法 ====================

    def extract_zip_if_needed(self, file_path: str) -> list[str] | None:
        """
        如果是 ZIP 文件则解压

        Args:
            file_path: 文件路径

        Returns:
            解压后的文件路径列表,如果不是 ZIP 文件则返回 None
        """
        from .utils.zip_extractor import extract_zip_if_needed

        return extract_zip_if_needed(file_path)

    # ==================== SMS 处理方法 ====================

    def process_sms_in_thread(
        self, record: DocumentDeliveryRecord, file_path: str, extracted_files: list[str], credential_id: int
    ) -> dict[str, Any]:
        return self.processor.process_sms_in_thread(
            record=record,
            file_path=file_path,
            extracted_files=extracted_files,
            credential_id=credential_id,
        )

    def record_query_history_in_thread(self, credential_id: int, entry: DocumentDeliveryRecord) -> None:
        try:
            self.history_repo.enqueue_record_query_history(
                credential_id=credential_id,
                case_number=entry.case_number,
                send_time=entry.send_time,
            )
        except Exception as e:
            logger.warning("记录查询历史失败", extra={"credential_id": credential_id, "error": str(e)})

    # ==================== 辅助方法 ====================

    def _match_case_by_document_parties(self, document_paths: list[str]) -> Any:
        return self.processor.match_case_by_document_parties(document_paths)

    def _sync_case_number_to_case(self, case_id: int, case_number: str) -> None:
        self.processor.sync_case_number_to_case(case_id=case_id, case_number=case_number)

    def _rename_and_attach_documents(
        self, sms: Any, case_id: int, case_name: str, extracted_files: list[str]
    ) -> tuple[list[str], int | None]:
        class _CaseLite:
            def __init__(self, id: int, name: str) -> None:
                self.id = id
                self.name = name

        return self.processor.rename_and_attach_documents(
            sms=sms,
            case=_CaseLite(id=case_id, name=case_name),
            extracted_files=extracted_files,
        )

    def _upload_attachments(self, case_log_service: Any, case_log_id: int, file_paths: list[str]) -> None:
        self.processor._upload_attachments(case_log_service, log_id=case_log_id, file_paths=file_paths)

    def _send_notification(self, sms: Any, document_paths: list[str]) -> bool:
        return self.processor.send_notification(sms, document_paths)
