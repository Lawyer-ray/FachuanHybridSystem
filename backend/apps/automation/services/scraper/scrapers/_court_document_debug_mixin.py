"""法院文书爬虫 — 调试工具 Mixin"""

import contextlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger("apps.automation")


class CourtDocumentDebugMixin:
    """调试和页面分析相关方法"""

    debug_info: dict[str, Any]
    page: "Page"

    # 子类提供
    def _prepare_download_dir(self) -> Path:
        raise NotImplementedError

    def screenshot(self, name: str) -> Any:
        raise NotImplementedError

    def _debug_log(self, message: str, data: Any = None) -> None:
        """调试日志"""
        from apps.core.services.system_config_service import SystemConfigService

        debug_mode = SystemConfigService().get_value("DEBUG_MODE", "false").lower() in ("true", "1", "yes")
        if debug_mode:
            logger.info(f"[DEBUG] {message}")
            if data:
                logger.info(f"[DEBUG] Data: {data}")

    def _save_debug_info(self, key: str, value: Any) -> None:
        """保存调试信息"""
        self.debug_info[key] = value
        from apps.core.services.system_config_service import SystemConfigService

        debug_mode = SystemConfigService().get_value("DEBUG_MODE", "false").lower() in ("true", "1", "yes")
        if debug_mode:
            logger.info(f"[DEBUG] Saved {key}: {type(value)}")

    def _analyze_page_elements(self) -> dict[str, Any]:
        """分析页面元素，用于调试"""
        analysis: dict[str, Any] = {
            "url": self.page.url,
            "title": self.page.title(),
            "buttons": [],
            "links": [],
            "download_elements": [],
            "iframes": [],
        }
        try:
            buttons = self.page.locator("button").all()
            for i, btn in enumerate(buttons[:10]):
                with contextlib.suppress(Exception):
                    analysis["buttons"].append({
                        "index": i,
                        "text": btn.inner_text()[:50] if btn.inner_text() else "",
                        "visible": btn.is_visible(),
                    })
            links = self.page.locator("a").all()
            for i, link in enumerate(links[:10]):
                with contextlib.suppress(Exception):
                    analysis["links"].append({
                        "index": i,
                        "text": link.inner_text()[:50] if link.inner_text() else "",
                        "href": (link.get_attribute("href") or "")[:100],
                        "visible": link.is_visible(),
                    })
            download_elements = self.page.locator('*:has-text("下载")').all()
            for i, elem in enumerate(download_elements[:10]):
                try:
                    tag = elem.evaluate("el => el.tagName")
                    analysis["download_elements"].append({
                        "index": i,
                        "tag": tag,
                        "text": elem.inner_text()[:50] if elem.inner_text() else "",
                        "visible": elem.is_visible(),
                    })
                except Exception:
                    pass
            iframes = self.page.locator("iframe").all()
            for i, iframe in enumerate(iframes):
                with contextlib.suppress(Exception):
                    analysis["iframes"].append({
                        "index": i,
                        "src": (iframe.get_attribute("src") or "")[:100],
                    })
        except Exception as e:
            analysis["error"] = str(e)
        return analysis

    def _save_page_state(self, name: str) -> dict[str, Any]:
        """保存页面状态（截图 + HTML + 元素分析）"""
        download_dir = self._prepare_download_dir()
        screenshot_path = self.screenshot(name)
        html_path = download_dir / f"{name}_page.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(self.page.content())
        analysis = self._analyze_page_elements()
        analysis_path = download_dir / f"{name}_analysis.json"
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
        logger.info(f"[DEBUG] 页面状态已保存: {name}")
        return {"screenshot": screenshot_path, "html": str(html_path), "analysis": analysis}
