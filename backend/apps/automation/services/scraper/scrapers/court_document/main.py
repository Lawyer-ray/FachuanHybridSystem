"""
法院文书下载爬虫主入口

根据 URL 或页面结构自动选择对应的下载策略
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse

from .base_court_scraper import BaseCourtDocumentScraper
from .zxfw_scraper import ZxfwCourtScraper

if TYPE_CHECKING:
    from apps.core.interfaces import ICourtDocumentService

logger = logging.getLogger("apps.automation")


def _is_playwright_available() -> bool:  # pragma: no cover
    """检查 Playwright 是否已安装"""
    try:
        import playwright

        return True
    except ImportError:
        return False


class CourtDocumentScraper(BaseCourtDocumentScraper):  # pragma: no cover
    """
    法院文书下载爬虫主入口

    平台识别策略：
    1. 优先使用已知域名快速识别（性能最好）
    2. 域名未命中时使用 Playwright 打开页面进行结构探测（需 Playwright 已安装）
    3. Playwright 未安装时跳过结构探测，仅依赖域名识别

    浏览器创建策略：
    - 如果目标子爬虫 requires_browser=True，在执行前创建浏览器上下文
    - 如果目标子爬虫 requires_browser=False（如一张网纯 API），跳过浏览器创建
    - 当子爬虫需要浏览器但 Playwright 未安装时，抛出明确错误
    """

    # 浏览器创建由 _run() 根据子爬虫类型动态决定
    requires_browser = False

    def __init__(self, task: Any, document_service: ICourtDocumentService | None = None) -> None:  # pragma: no cover
        super().__init__(task, document_service)
        self._scraper: Any = None

    def _run(self) -> dict[str, Any]:  # pragma: no cover
        """执行文书下载任务"""
        logger.info("执行法院文书下载: %s", self.task.url)

        scraper_cls = self._resolve_scraper_class(self.task.url)

        # 根据子爬虫是否需要浏览器，决定是否创建浏览器上下文
        scraper_requires_browser = getattr(scraper_cls, "requires_browser", True)
        if scraper_requires_browser:
            if not _is_playwright_available():
                raise RuntimeError(
                    "当前任务需要 Playwright 浏览器，但 Playwright 未安装。"
                    "请运行: uv add playwright && playwright install chromium"
                )
            # 创建独立的浏览器上下文（启用反检测）
            self.context = self.browser_service.create_context(use_anti_detection=True)
            assert self.context is not None
            self.page = self.context.new_page()

        return self._dispatch_to_scraper(scraper_cls)

    def _extract_host(self, url: str) -> str:  # pragma: no cover
        return (urlparse(url).hostname or "").lower()

    def _host_equals_or_subdomain(self, host: str, domain: str) -> bool:  # pragma: no cover
        return host == domain or host.endswith(f".{domain}")

    def _resolve_scraper_class(self, url: str) -> Any:  # pragma: no cover
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        port = parsed.port

        # 第一层：已知域名快速识别
        if self._host_equals_or_subdomain(host, "zxfw.court.gov.cn"):
            return ZxfwCourtScraper

        # 以下平台需要 Playwright，按需延迟导入
        if self._host_equals_or_subdomain(host, "sd.gdems.com"):
            self._ensure_playwright("广东电子送达")
            from .gdems_scraper import GdemsCourtScraper

            return GdemsCourtScraper
        if self._host_equals_or_subdomain(host, "dzsd.hbfy.gov.cn"):
            self._ensure_playwright("湖北电子送达")
            from .hbfy_scraper import HbfyCourtScraper

            return HbfyCourtScraper
        if self._host_equals_or_subdomain(host, "sfsd.jxfy.gov.cn"):
            from .jxfy_scraper import JxfyCourtScraper

            return JxfyCourtScraper
        if self._host_equals_or_subdomain(host, "jysd.10102368.com"):
            self._ensure_playwright("简易送达")
            from .jysd_scraper import JysdCourtScraper

            return JysdCourtScraper
        if self._host_equals_or_subdomain(host, "sfpt.cdfy12368.gov.cn"):
            self._ensure_playwright("司法送达网")
            from .sfdw_scraper import SfdwCourtScraper

            return SfdwCourtScraper
        if host == "171.106.48.55" and port == 28083:
            self._ensure_playwright("司法送达网")
            from .sfdw_scraper import SfdwCourtScraper

            return SfdwCourtScraper

        # 第二层：结构识别兜底（需要 Playwright）
        if _is_playwright_available():
            # 结构探测需要浏览器，按需创建
            if self.context is None:
                self.context = self.browser_service.create_context(use_anti_detection=True)
            if self.page is None:
                self.page = self.context.new_page()

            detected_platform = self._detect_platform_by_structure()
            if detected_platform == "zxfw":
                return ZxfwCourtScraper
            if detected_platform == "gdems":
                from .gdems_scraper import GdemsCourtScraper

                return GdemsCourtScraper
            if detected_platform == "daolv":
                return self._resolve_daolv_scraper(host)
            if detected_platform == "jysd":
                from .jysd_scraper import JysdCourtScraper

                return JysdCourtScraper
            if detected_platform == "sfdw":
                from .sfdw_scraper import SfdwCourtScraper

                return SfdwCourtScraper
        else:
            logger.warning(
                "Playwright 未安装，无法进行页面结构探测。"
                "仅支持一张网(zxfw.court.gov.cn)的纯 API 下载，其他平台请安装 Playwright"
            )

        raise ValueError(
            f"不支持的链接格式: {url}。"
            "如需使用结构探测识别平台，请安装 Playwright: uv add playwright && playwright install chromium"
        )

    def _ensure_playwright(self, platform_name: str) -> None:  # pragma: no cover
        """确保 Playwright 已安装，否则抛出明确错误"""
        if not _is_playwright_available():
            raise RuntimeError(
                f"「{platform_name}」平台需要 Playwright 浏览器支持，但 Playwright 未安装。"
                "请运行: uv add playwright && playwright install chromium"
            )

    def _dispatch_to_scraper(self, scraper_cls: type[BaseCourtDocumentScraper]) -> dict[str, Any]:  # pragma: no cover
        self._scraper = scraper_cls(self.task, self._document_service)

        # 复用当前浏览器上下文（如果有的话），避免重复创建
        if hasattr(self, "page") and self.page is not None:
            self._scraper.page = self.page
        if hasattr(self, "context") and self.context is not None:
            self._scraper.context = self.context
        if hasattr(self, "browser") and self.browser is not None:
            self._scraper.browser = self.browser

        result = self._scraper.run()
        if not isinstance(result, dict):
            raise ValueError("法院文书爬虫返回结果格式错误")
        return cast(dict[str, Any], result)

    def _detect_platform_by_structure(self) -> str | None:  # pragma: no cover
        """使用 Playwright 打开页面并根据结构特征识别平台。"""
        try:
            self.navigate_to_url(timeout=35000)
            assert self.page is not None
            self.page.wait_for_timeout(1500)

            current_url = (self.page.url or "").lower()
            content_lower = self.page.content().lower()

            # 简易送达：典型是内嵌 sifayun iframe
            frame_urls = [(frame.url or "").lower() for frame in self.page.frames if frame is not None]
            if any(self._extract_host(frame_url) in {"sifayun.com", "www.sifayun.com"} for frame_url in frame_urls):
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

            # 道律「司法送达网」平台：/sfsddz 账号入口 或 /hb/msg= 短信入口
            if "/hb/msg=" in current_url or "/sfsddz" in current_url:
                logger.info("结构识别命中道律司法送达网特征（%s）", current_url)
                return "daolv"

            # 人民法院在线服务网：hash 路由与 wssd 特征
            if "/pagesajkj/app/wssd/index" in current_url or "getwslistbysdbhnew" in content_lower:
                logger.info("结构识别命中人民法院在线服务网特征")
                return "zxfw"

            logger.warning("结构识别未命中任何已知平台特征: %s", current_url)
            return None

        except Exception as exc:
            logger.warning("结构识别失败，回退为不支持平台: %s", exc)
            return None

    def _has_selector(self, selector: str) -> bool:  # pragma: no cover
        """安全判断页面上是否存在指定选择器。"""
        try:
            assert self.page is not None
            return int(self.page.locator(selector).count()) > 0
        except Exception:
            return False

    # ── 道律平台动态解析 ─────────────────────────────────────────

    _DAOLV_KNOWN_DOMAINS: dict[str, str] = {
        "dzsd.hbfy.gov.cn": ".hbfy_scraper.HbfyCourtScraper",
        "sfsd.jxfy.gov.cn": ".jxfy_scraper.JxfyCourtScraper",
    }

    def _resolve_daolv_scraper(self, host: str) -> type[BaseCourtDocumentScraper]:  # pragma: no cover
        """根据域名解析道律平台爬虫。

        已注册的域名返回对应的专用子类；未注册的域名自动创建
        DaolvSifaSongdaScraper 子类，URL 常量从域名推导。
        """
        from .daolv_sifa_songda_scraper import DaolvSifaSongdaScraper

        # 已注册域名 → 延迟导入对应子类
        for domain_suffix, class_path in self._DAOLV_KNOWN_DOMAINS.items():
            if self._host_equals_or_subdomain(host, domain_suffix):
                module_path, class_name = class_path.rsplit(".", 1)
                import importlib

                module = importlib.import_module(module_path, package=__package__)
                scraper_cls: type[BaseCourtDocumentScraper] = getattr(module, class_name)
                logger.info("道律平台域名匹配: %s → %s", host, class_name)
                return scraper_cls

        # 未知域名 → 动态生成子类，URL 从域名推导
        logger.info("道律平台未知域名，动态适配: %s", host)
        return self._create_daolv_scraper_class(host)

    @staticmethod
    def _create_daolv_scraper_class(host: str) -> type[DaolvSifaSongdaScraper]:  # pragma: no cover
        """为未知道律域名动态创建爬虫子类。

        道律平台的 URL 结构完全一致，仅域名不同：
          登录页: http://{host}/sfsddz
          验证码: http://{host}:80/deli/images/yanz.png
          ...
        """
        from .daolv_sifa_songda_scraper import DaolvSifaSongdaScraper

        base = f"http://{host}:80"
        cls_name = f"DaolvScraper_{host.replace('.', '_').replace('-', '_')}"
        cls = type(cls_name, (DaolvSifaSongdaScraper,), {
            "requires_browser": False,
            "_DOMAIN": host,
            "_LOGIN_PAGE_URL": f"http://{host}/sfsddz",
            "_CAPTCHA_IMAGE_URL": f"{base}/deli/images/yanz.png",
            "_CAPTCHA_CHECK_URL": f"{base}/deli/deli-login!checkyzmAjaxp.action",
            "_LOGIN_URL": f"{base}/deli/easy-login!dologinAjax.action",
            "_MAIN_URL": f"{base}/deli/login!main.action",
            "_LIST_URLS": (
                f"{base}/deli/TdeliPubRecord/tdelipubrecord!todoList.action",
                f"{base}/deli/TdeliPubRecord/tdelipubrecord!doneList.action",
                f"{base}/deli/TdeliPubRecord/tdelipubrecord!expiredList.action",
            ),
            "_PLATFORM_LABEL": host.split(".")[0],
        })

        # run() 方法：仅支持 /sfsddz 账号模式
        def _run(self_inner: Any) -> dict[str, Any]:
            url = self_inner.task.url
            if f"{host}/sfsddz" in url:
                return self_inner._run_account_mode(source_domain=host)
            raise ValueError(f"不支持的道律平台链接: {url}")

        cls.run = _run  # type: ignore[method-assign]
        return cls
