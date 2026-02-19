"""
法院文书下载爬虫
支持两种链接格式：
1. https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?...
2. https://sd.gdems.com/v3/dzsd/...
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from django.conf import settings

from ._court_document_db_mixin import CourtDocumentDbMixin
from ._court_document_debug_mixin import CourtDocumentDebugMixin
from ._court_document_gdems_mixin import CourtDocumentGdemsMixin
from ._court_document_zxfw_mixin import CourtDocumentZxfwMixin
from .base import BaseScraper

if TYPE_CHECKING:
    from apps.core.interfaces import ICourtDocumentService

logger = logging.getLogger("apps.automation")


class CourtDocumentScraper(
    CourtDocumentZxfwMixin,
    CourtDocumentGdemsMixin,
    CourtDocumentDbMixin,
    CourtDocumentDebugMixin,
    BaseScraper,
):
    """
    法院文书下载爬虫

    根据不同的链接格式，自动选择对应的下载策略
    """

    def __init__(self, task: Any, document_service: Optional["ICourtDocumentService"] = None) -> None:
        super().__init__(task)
        self.site_name = "court_document"
        self.debug_info: dict[str, Any] = {}
        self._document_service = document_service

    @property
    def document_service(self) -> "ICourtDocumentService":
        """获取文书服务实例（延迟加载）"""
        if self._document_service is None:
            from apps.core.interfaces import ServiceLocator
            self._document_service = ServiceLocator.get_court_document_service()
        return self._document_service

    def _prepare_download_dir(self) -> Path:
        """准备下载目录"""
        if self.task.case_id:
            download_dir = Path(settings.MEDIA_ROOT) / "case_logs" / str(self.task.case_id) / "documents"
        else:
            download_dir = Path(settings.MEDIA_ROOT) / "automation" / "downloads" / f"task_{self.task.id}"
        download_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"下载目录: {download_dir}")
        return download_dir

    def _run(self) -> dict[str, Any]:
        """执行文书下载任务"""
        logger.info(f"执行法院文书下载: {self.task.url}")
        url = self.task.url
        if "zxfw.court.gov.cn" in url:
            return self._download_zxfw_court(url)
        elif "sd.gdems.com" in url:
            return self._download_gdems(url)
        else:
            raise ValueError(f"不支持的链接格式: {url}")
