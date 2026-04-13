"""
法院文书下载爬虫主入口

根据 URL 或页面结构自动选择对应的下载策略
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

    平台识别策略：
    1. 优先使用已知域名快速识别（性能最好）
    2. 域名未命中时使用 Playwright 打开页面进行结构探测
    3. 探测成功后复用现有平台 Scraper
    """

    def __init__(self, task: Any, document_service: ICourtDocumentService | None = None) -> None:
        super().__init__(task, document_service)
        self._scraper: Any = None

    def _run(self) -> dict[str, Any]:
        """执行文书下载任务"""
        logger.info("执行法院文书下载: %s", self.task.url)

        scraper_cls = self._resolve_scraper_class(self.task.url)
        return self._dispatch_to_scraper(scraper_cls)

    def _resolve_scraper_class(self, url: str) -> Any:
        url_lower = url.lower()

        # 第一层：已知域名快速识别
        if "zxfw.court.gov.cn" in url_lower:
            return ZxfwCourtScraper
        if "sd.gdems.com" in url_lower:
            return GdemsCourtScraper
        if "dzsd.hbfy.gov.cn" in url_lower:
            return HbfyCourtScraper
        if "jysd.10102368.com" in url_lower:
            return JysdCourtScraper
        if "sfpt.cdfy12368.gov.cn" in url_lower or "171.106.48.55:28083" in url_lower:
            return SfdwCourtScraper

        # 第二层：结构识别兜底
        detected_platform = self._detect_platform_by_structure()
        if detected_platform == "zxfw":
            return ZxfwCourtScraper
        if detected_platform == "gdems":
            return GdemsCourtScraper
        if detected_platform == "hbfy":
            return HbfyCourtScraper
        if detected_platform == "jysd":
            return JysdCourtScraper
        if detected_platform == "sfdw":
            return SfdwCourtScraper

        raise ValueError(f"不支持的链接格式，且结构探测未识别平台: {url}")

    def _dispatch_to_scraper(self, scraper_cls: type[BaseCourtDocumentScraper]) -> dict[str, Any]:
        self._scraper = scraper_cls(self.task, self._document_service)

        # 复用当前浏览器上下文，避免重复创建
        if hasattr(self, "page"):
            self._scraper.page = self.page
        if hasattr(self, "context"):
            self._scraper.context = self.context
        if hasattr(self, "browser"):
            self._scraper.browser = self.browser

        result = self._scraper.run()
        if not isinstance(result, dict):
            raise ValueError("法院文书爬虫返回结果格式错误")
        return cast(dict[str, Any], result)

    def _detect_platform_by_structure(self) -> str | None:
        """使用 Playwright 打开页面并根据结构特征识别平台。"""
        try:
            self.navigate_to_url(timeout=35000)
            assert self.page is not None
            self.page.wait_for_timeout(1500)

            current_url = (self.page.url or "").lower()
            content_lower = self.page.content().lower()

            # 简易送达：典型是内嵌 sifayun iframe
            frame_urls = [
                (frame.url or "").lower()
                for frame in self.page.frames
                if frame is not None
            ]
            if any("sifayun.com" in frame_url for frame_url in frame_urls):
                logger.info("结构识别命中简易送达特征（sifayun iframe）")
                return "jysd"

            # 司法送达网：验证码输入框 + Vue 方法特征
            if self._has_selector("#checkCode") or ("checkyzm" in content_lower and "wslist" in content_lower):
                logger.info("结构识别命中司法送达网特征")
                return "sfdw"

            # 广东电子送达：确认按钮/下载按钮结构
            if self._has_selector("#submit-btn") or self._has_selector("a.downloadPackClass"):
                logger.info("结构识别命中广东电子送达特征")
                return "gdems"

            # 湖北电子送达：路径与入口特征
            if "/hb/msg=" in current_url or "/sfsddz" in current_url:
                logger.info("结构识别命中湖北电子送达特征")
                return "hbfy"

            # 人民法院在线服务网：hash 路由与 wssd 特征
            if "/pagesajkj/app/wssd/index" in current_url or "getwslistbysdbhnew" in content_lower:
                logger.info("结构识别命中人民法院在线服务网特征")
                return "zxfw"

            logger.warning("结构识别未命中任何已知平台特征: %s", current_url)
            return None

        except Exception as exc:
            logger.warning("结构识别失败，回退为不支持平台: %s", exc)
            return None

    def _has_selector(self, selector: str) -> bool:
        """安全判断页面上是否存在指定选择器。"""
        try:
            assert self.page is not None
            return int(self.page.locator(selector).count()) > 0
        except Exception:
            return False
