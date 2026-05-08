"""进度上报 + 截图 + 引擎解析。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from .form_utils import FormUtilsMixin

logger = logging.getLogger("apps.automation")


class ProgressReporterMixin(FormUtilsMixin):
    """进度上报 Mixin，需要子类提供 self.page 和 self.save_debug。"""

    page: Page
    save_debug: bool

    @staticmethod
    def _resolve_filing_engine(case_data: dict[str, Any]) -> str:
        engine = str(case_data.get("filing_engine", "") or "").strip().lower()
        if engine in {"api", "playwright"}:
            return engine
        if "use_api_for_execution" in case_data:
            return "api" if bool(case_data.get("use_api_for_execution")) else "playwright"
        try:
            from plugins import has_court_filing_api_plugin

            if has_court_filing_api_plugin():
                return "api"
        except ImportError:
            pass
        return "playwright"

    @staticmethod
    def _allow_playwright_fallback(case_data: dict[str, Any]) -> bool:
        value = case_data.get("playwright_fallback", True)
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "off"}
        return bool(value)

    def _report_progress(
        self,
        case_data: dict[str, Any],
        *,
        phase: str,
        stage: str,
        message: str,
        level: str = "info",
        detail: str = "",
    ) -> None:
        reporter = case_data.get("_progress_reporter")
        if not callable(reporter):
            return
        payload: dict[str, Any] = {
            "phase": phase,
            "stage": stage,
            "level": level,
            "message": message,
        }
        if detail:
            payload["detail"] = detail
        try:
            reporter(payload)
        except Exception:
            logger.debug("court_filing_progress_report_failed", exc_info=True)

    def _save_screenshot(self, name: str) -> str:
        """保存调试截图"""
        from datetime import datetime

        from django.conf import settings

        screenshot_dir = Path(settings.MEDIA_ROOT) / "automation" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = screenshot_dir / filename

        self.page.screenshot(path=str(filepath))
        logger.info("截图已保存: %s", filepath)
        return str(filepath)

    def _step6_preview_submit(self) -> None:
        """预览提交页 - 仅查看，不点提交"""
        from django.utils.translation import gettext_lazy as _

        logger.info(str(_("步骤6: 预览（不提交）")))
        self._random_wait(2, 3)
        logger.info(str(_("步骤6完成: 已到达预览页，未提交")))

