"""
文书送达 API 查询服务

负责通过 API 查询文书列表和处理文书，从 DocumentDeliveryService 中提取。
"""

import logging
from typing import TYPE_CHECKING, Optional

from apps.automation.services.document_delivery.court_document_api_client import CourtDocumentApiClient

from ._matching import DocumentMatchingMixin
from ._process import DocumentProcessMixin
from ._query import DocumentQueryMixin

if TYPE_CHECKING:
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.document_renamer import DocumentRenamer
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService

logger = logging.getLogger("apps.automation")

__all__ = ["DocumentDeliveryApiService"]


class DocumentDeliveryApiService(DocumentQueryMixin, DocumentProcessMixin, DocumentMatchingMixin):
    """
    文书送达 API 查询服务

    职责：
    1. 通过 API 查询文书列表
    2. 处理分页逻辑
    3. 处理单个文书（下载、匹配、通知）
    4. 检查文书是否需要处理

    Requirements: 1.1, 1.3, 5.1, 5.2, 5.5
    """

    def __init__(
        self,
        api_client: CourtDocumentApiClient | None = None,
        case_matcher: Optional["CaseMatcher"] = None,
        document_renamer: Optional["DocumentRenamer"] = None,
        notification_service: Optional["SMSNotificationService"] = None,
    ):
        self._api_client = api_client
        self._case_matcher = case_matcher
        self._document_renamer = document_renamer
        self._notification_service = notification_service

        logger.debug("DocumentDeliveryApiService 初始化完成")

    @property
    def api_client(self) -> CourtDocumentApiClient:
        """延迟加载 API 客户端"""
        if self._api_client is None:
            self._api_client = CourtDocumentApiClient()
        return self._api_client

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
