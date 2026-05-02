"""JtnCaseImportScript facade — 组合所有 mixin。"""

from __future__ import annotations

import logging
from typing import Any, Callable, Generator

import httpx
from playwright.sync_api import Browser, BrowserContext, Page, Playwright

from ..jtn_case_import_models import (
    OACaseData,
    OAListCaseCandidate,
    CaseListFormState,
)
from .jtn_http_client import JtnHttpClientMixin
from .jtn_sso_handler import JtnSsoHandlerMixin
from .jtn_playwright_browser import JtnPlaywrightBrowserMixin
from .jtn_detail_extractor import JtnDetailExtractorMixin

logger = logging.getLogger("apps.oa_filing.jtn_case_import")


class JtnCaseImportScript(
    JtnHttpClientMixin,
    JtnSsoHandlerMixin,
    JtnPlaywrightBrowserMixin,
    JtnDetailExtractorMixin,
):
    """金诚同达 OA 案件导入自动化。"""

    def __init__(
        self,
        account: str,
        password: str,
        *,
        headless: bool = True,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._account = account
        self._password = password
        self._headless = bool(headless)
        self._progress_callback = progress_callback
        self._page: Page | None = None
        self._context: BrowserContext | None = None
        self._http_cookies_cache: dict[str, str] | None = None
        self._name_search_http_client: httpx.Client | None = None
        self._name_search_form_state: CaseListFormState | None = None
        self._name_search_pw: Playwright | None = None
        self._name_search_browser: Browser | None = None
        self._force_playwright_name_search = False

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def search_case(self, case_no: str) -> OACaseData | None:
        """根据案件编号搜索并提取完整数据。

        Args:
            case_no: OA案件编号，如 2024GZM0501

        Returns:
            OACaseData 或 None（未找到）
        """
        normalized_case_no = str(case_no).strip()
        if not normalized_case_no:
            return None

        for _, case_data in self.search_cases([normalized_case_no], workers=1):
            return case_data
        return None

    def search_cases_by_name(self, contract_name: str, *, limit: int = 6) -> list[OAListCaseCandidate]:
        """按案件名称查询 OA 列表候选项（仅在 HTTP 不可用时回退 Playwright）。"""
        keyword = str(contract_name or "").strip()
        if not keyword:
            return []

        effective_limit = max(1, int(limit))

        if self._force_playwright_name_search:
            return self._search_cases_by_name_via_playwright(keyword=keyword, limit=effective_limit)

        last_http_error: Exception | None = None
        for attempt in range(1, 2 + 1):  # _NAME_SEARCH_HTTP_ATTEMPTS = 2
            try:
                return self._search_cases_by_name_via_http(keyword=keyword, limit=effective_limit)
            except Exception as exc:
                last_http_error = exc
                if self._is_sso_blocking_error(exc):
                    raise
                if attempt < 2:
                    logger.warning(
                        "HTTP 按名称查询异常，准备重试 HTTP: keyword=%s attempt=%d/%d err=%s",
                        keyword,
                        attempt,
                        2,
                        exc,
                    )
                    continue

        logger.warning("HTTP 按名称查询异常，准备回退 Playwright: keyword=%s err=%s", keyword, last_http_error)

        playwright_candidates = self._search_cases_by_name_via_playwright(keyword=keyword, limit=effective_limit)
        if playwright_candidates:
            logger.info(
                "按名称查询启用 Playwright 兜底成功: keyword=%s playwright_count=%d",
                keyword,
                len(playwright_candidates),
            )
        return playwright_candidates

    def ensure_name_search_ready(self) -> None:
        """预检查 OA 案件列表可访问性（纯 Playwright 链路）。"""
        self._force_playwright_name_search = True
        self._ensure_name_search_playwright_session()

    def search_cases(
        self,
        case_nos: list[str],
        *,
        workers: int = 1,
        playwright_fallback: bool = True,
    ) -> Generator[tuple[str, OACaseData | None], None, None]:
        """批量搜索案件。

        Args:
            case_nos: 案件编号列表
            workers: HTTP 并发数（同一登录会话下并发查询）
            playwright_fallback: HTTP 失败时是否回落 Playwright

        Yields:
            (case_no, case_data) 元组
        """
        normalized_case_nos = [str(case_no).strip() for case_no in case_nos if str(case_no).strip()]
        if not normalized_case_nos:
            return

        indexed_case_nos = list(enumerate(normalized_case_nos))
        resolved: list[OACaseData | None] = [None] * len(indexed_case_nos)

        # 先走 HTTP 直连链路（一次登录 + 多线程并发查询）。
        http_failed_indexes: list[int] = []
        try:
            http_results = self._search_cases_via_http(indexed_case_nos=indexed_case_nos, workers=workers)
            for index, _, case_data in http_results:
                resolved[index] = case_data
                if case_data is None:
                    http_failed_indexes.append(index)
        except Exception as exc:
            logger.warning("HTTP 批量查询异常，准备回落 Playwright: %s", exc)
            http_failed_indexes = [index for index, _ in indexed_case_nos]

        # HTTP 没查到或解析失败的，统一回落 Playwright（单次登录批量兜底）。
        if playwright_fallback and http_failed_indexes:
            fallback_case_nos = [normalized_case_nos[index] for index in http_failed_indexes]
            logger.info(
                "触发 Playwright 兜底: failed=%d total=%d",
                len(fallback_case_nos),
                len(normalized_case_nos),
            )
            fallback_by_case_no: dict[str, OACaseData | None] = {}
            try:
                fallback_results = list(self._search_cases_via_playwright(fallback_case_nos))
                fallback_by_case_no = dict(fallback_results)
            except Exception as exc:
                logger.warning("Playwright 兜底批量查询异常，返回空结果: %s", exc, exc_info=True)
            for index in http_failed_indexes:
                case_no = normalized_case_nos[index]
                resolved[index] = fallback_by_case_no.get(case_no)

        for index, case_no in indexed_case_nos:
            self._emit_progress(
                "searching",
                case_no=case_no,
                message=f"正在搜索案件 {case_no}",
            )
            yield case_no, resolved[index]

    def close(self) -> None:
        self._reset_name_search_http_session()
        if self._name_search_browser is not None:
            self._name_search_browser.close()
        if self._name_search_pw is not None:
            self._name_search_pw.stop()
        self._name_search_browser = None
        self._name_search_pw = None
        self._context = None
        self._page = None

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _emit_progress(self, event: str, **payload: Any) -> None:
        if self._progress_callback is None:
            return
        try:
            self._progress_callback({"event": event, **payload})
        except Exception:
            logger.debug("进度回调处理异常: event=%s", event, exc_info=True)
