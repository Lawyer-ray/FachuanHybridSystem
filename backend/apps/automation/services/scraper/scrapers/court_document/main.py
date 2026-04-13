"""
法院文书下载爬虫主入口

根据 URL 自动选择对应的下载策略
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from .base_court_scraper import BaseCourtDocumentScraper
from .gdems_scraper import GdemsCourtScraper
from .hbfy_scraper import HbfyCourtScraper
from .jysd_scraper import JysdCourtScraper
from .sfdw_scraper import SfdwCourtScraper
from .zxfw_scraper import ZxfwCourtScraper

if TYPE_CHECKING:
    from apps.core.interfaces import ICourtDocumentService

logger = logging.getLogger("apps.automation")


class CourtDocumentScraper(BaseCourtDocumentScraper):
    """
    法院文书下载爬虫主入口

    根据不同的链接格式,自动选择对应的下载策略:
    - zxfw.court.gov.cn: 人民法院在线服务网
    - sd.gdems.com: 睿法智达
    - jysd.10102368.com: 集约送达
    - dzsd.hbfy.gov.cn: 湖北电子送达
    - sfpt.cdfy12368.gov.cn: 司法送达网
    """

    def __init__(self, task: Any, document_service: ICourtDocumentService | None = None) -> None:
        super().__init__(task, document_service)
        self._scraper: BaseCourtDocumentScraper | None = None

    def _run(self) -> dict[str, Any]:
        """
        执行文书下载任务

        Returns:
            包含下载文件路径列表的字典
        """
        logger.info(f"执行法院文书下载: {self.task.url}")

        # 根据 URL 判断链接类型并选择对应的爬虫
        url = self.task.url

        if "zxfw.court.gov.cn" in url:
            self._scraper = ZxfwCourtScraper(self.task, self._document_service)
            # 复制必要的属性
            if hasattr(self, "page"):
                self._scraper.page = self.page
            if hasattr(self, "context"):
                self._scraper.context = self.context
            if hasattr(self, "browser"):
                self._scraper.browser = self.browser
            return cast(dict[str, Any], self._scraper.run())
        elif "sd.gdems.com" in url:
            self._scraper = GdemsCourtScraper(self.task, self._document_service)
            # 复制必要的属性
            if hasattr(self, "page"):
                self._scraper.page = self.page
            if hasattr(self, "context"):
                self._scraper.context = self.context
            if hasattr(self, "browser"):
                self._scraper.browser = self.browser
            return cast(dict[str, Any], self._scraper.run())
        elif "dzsd.hbfy.gov.cn" in url:
            self._scraper = HbfyCourtScraper(self.task, self._document_service)
            if hasattr(self, "page"):
                self._scraper.page = self.page
            if hasattr(self, "context"):
                self._scraper.context = self.context
            if hasattr(self, "browser"):
                self._scraper.browser = self.browser
            return cast(dict[str, Any], self._scraper.run())
        elif "jysd.10102368.com" in url:
            self._scraper = JysdCourtScraper(self.task, self._document_service)
            if hasattr(self, "page"):
                self._scraper.page = self.page
            if hasattr(self, "context"):
                self._scraper.context = self.context
            if hasattr(self, "browser"):
                self._scraper.browser = self.browser
            return cast(dict[str, Any], self._scraper.run())
        elif "sfpt.cdfy12368.gov.cn" in url or "171.106.48.55:28083" in url:
            self._scraper = SfdwCourtScraper(self.task, self._document_service)
            if hasattr(self, "page"):
                self._scraper.page = self.page
            if hasattr(self, "context"):
                self._scraper.context = self.context
            if hasattr(self, "browser"):
                self._scraper.browser = self.browser
            return cast(dict[str, Any], self._scraper.run())
        else:
            raise ValueError(f"不支持的链接格式: {url}")
