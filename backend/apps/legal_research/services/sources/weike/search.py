from __future__ import annotations

import logging
import re
import time
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from playwright.sync_api import Page

from apps.legal_research.services.task_event_service import LegalResearchTaskEventService

from . import api_optional
from .types import WeikeSearchItem, WeikeSession

logger = logging.getLogger(__name__)


class WeikeSearchMixin:
    LAW_LOGIN_REQUIRED_TEXT = "抱歉，此功能需要登录后操作"
    LAW_LOGIN_MODAL_USERNAME_SELECTOR = "#login-username"
    LAW_LOGIN_BUTTON_SELECTOR = "button.wk-banner-action-bar-item.wkb-btn-green:has-text('登录')"

    def search_cases(
        self,
        *,
        session: WeikeSession,
        keyword: str,
        max_candidates: int,
        max_pages: int = 10,
        offset: int = 0,
    ) -> list[WeikeSearchItem]:
        if session.search_via_api_enabled:
            if self._is_search_api_degraded(session=session):
                wait_seconds = self._search_api_degraded_wait_seconds(session=session)
                self._record_search_event(
                    session=session,
                    source="system",
                    interface_name="search_api_degraded",
                    success=True,
                    request_summary={"keyword": keyword, "offset": offset},
                    response_summary={"wait_seconds": wait_seconds},
                )
                logger.info(
                    "私有wk API检索熔断冷却中，直接走DOM检索（keyword=%s, offset=%s, wait=%ss）",
                    keyword,
                    offset,
                    wait_seconds,
                    extra={"keyword": keyword, "offset": offset, "wait_seconds": wait_seconds},
                )
            else:
                private_api = api_optional.get_private_weike_api()
                if private_api is not None:
                    try:
                        items = private_api.search_cases_via_api(
                            client=self,
                            session=session,
                            keyword=keyword,
                            max_candidates=max_candidates,
                            max_pages=max_pages,
                            offset=offset,
                        )
                        if items:
                            self._reset_search_api_health(session=session)
                            return items
                        try:
                            doc_count = max(0, int(getattr(session, "last_search_doc_count", 0) or 0))
                        except (TypeError, ValueError):
                            doc_count = 0
                        if offset > 0:
                            self._reset_search_api_health(session=session)
                            logger.info(
                                "私有wk API分页结果为空，视为翻页结束（keyword=%s, offset=%s, docCount=%s）",
                                keyword,
                                offset,
                                doc_count,
                                extra={"keyword": keyword, "offset": offset, "doc_count": doc_count},
                            )
                            return []
                        self._mark_search_api_empty(
                            session=session,
                            keyword=keyword,
                            offset=offset,
                            doc_count=doc_count,
                        )
                        self._record_search_event(
                            session=session,
                            source="system",
                            interface_name="search_fallback_dom",
                            success=True,
                            request_summary={"keyword": keyword, "offset": offset},
                            response_summary={"reason": "api_empty_result", "doc_count": doc_count},
                        )
                        logger.warning(
                            "私有wk API检索返回空结果，回退DOM检索（keyword=%s, offset=%s, docCount=%s）",
                            keyword,
                            offset,
                            doc_count,
                            extra={"keyword": keyword, "offset": offset, "doc_count": doc_count},
                        )
                    except Exception:
                        self._mark_search_api_error(session=session, keyword=keyword, offset=offset)
                        self._record_search_event(
                            session=session,
                            source="system",
                            interface_name="search_fallback_dom",
                            success=False,
                            error_code="API_EXCEPTION",
                            error_message="私有wk API检索失败",
                            request_summary={"keyword": keyword, "offset": offset},
                        )
                        logger.exception(
                            "私有wk API检索失败，回退DOM检索", extra={"keyword": keyword, "offset": offset}
                        )

        self._ensure_playwright_session(session)
        return self._search_cases_via_dom(
            session=session,
            keyword=keyword,
            max_candidates=max_candidates,
            max_pages=max_pages,
            offset=offset,
        )

    def _search_cases_via_dom(
        self,
        *,
        session: WeikeSession,
        keyword: str,
        max_candidates: int,
        max_pages: int,
        offset: int = 0,
    ) -> list[WeikeSearchItem]:
        started = time.monotonic()
        if session.page is None:
            self._record_search_event(
                session=session,
                source="dom",
                interface_name="dom_search",
                success=False,
                error_code="DOM_PAGE_NOT_READY",
                error_message="Playwright页面未就绪",
                request_summary={"keyword": keyword, "offset": offset, "max_candidates": max_candidates},
            )
            raise RuntimeError("Playwright页面未就绪")
        page = session.page
        try:
            page.goto(self.LAW_LIST_URL, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_selector("input[name='keyword']", timeout=60000)
            page.fill("input[name='keyword']", keyword)
            page.locator("button.wk-banner-action-bar-item.wkb-btn-green:has-text('搜索')").first.click(timeout=10000)
            page.wait_for_timeout(3500)
            self._raise_if_login_required(page)

            items: list[WeikeSearchItem] = []
            seen: set[str] = set()
            skipped = 0

            for _ in range(max_pages):
                anchors: list[dict[str, str]] = page.eval_on_selector_all(
                    "a[href*='/judgment-documents/detail/']",
                    """
                    els => els.map(el => ({
                      href: el.href || '',
                      text: (el.textContent || '').trim()
                    }))
                    """,
                )

                for anchor in anchors:
                    href = (anchor.get("href") or "").strip()
                    if not href:
                        continue

                    parsed = self._parse_detail_url(href)
                    if not parsed:
                        continue

                    if parsed.doc_id_raw in seen:
                        continue

                    seen.add(parsed.doc_id_raw)
                    if skipped < offset:
                        skipped += 1
                        continue

                    items.append(
                        WeikeSearchItem(
                            doc_id_raw=parsed.doc_id_raw,
                            doc_id_unquoted=parsed.doc_id_unquoted,
                            detail_url=href,
                            title_hint=(anchor.get("text") or "").strip(),
                            search_id=parsed.search_id,
                            module=parsed.module,
                        )
                    )
                    if len(items) >= max_candidates:
                        self._record_search_event(
                            session=session,
                            source="dom",
                            interface_name="dom_search",
                            method="GET",
                            url=self.LAW_LIST_URL,
                            status_code=200,
                            duration_ms=int((time.monotonic() - started) * 1000),
                            success=True,
                            request_summary={"keyword": keyword, "offset": offset, "max_candidates": max_candidates},
                            response_summary={"returned_count": len(items), "max_pages": max_pages},
                        )
                        return items

                if not self._go_next_page(page):
                    break

            self._record_search_event(
                session=session,
                source="dom",
                interface_name="dom_search",
                method="GET",
                url=self.LAW_LIST_URL,
                status_code=200,
                duration_ms=int((time.monotonic() - started) * 1000),
                success=True,
                request_summary={"keyword": keyword, "offset": offset, "max_candidates": max_candidates},
                response_summary={"returned_count": len(items), "max_pages": max_pages},
            )
            return items
        except Exception as exc:
            self._record_search_event(
                session=session,
                source="dom",
                interface_name="dom_search",
                method="GET",
                url=self.LAW_LIST_URL,
                duration_ms=int((time.monotonic() - started) * 1000),
                success=False,
                error_code="DOM_SEARCH_ERROR",
                error_message=self._compact_error_message(exc),
                request_summary={"keyword": keyword, "offset": offset, "max_candidates": max_candidates},
            )
            raise

    @classmethod
    def _raise_if_login_required(cls, page: Page) -> None:
        body_text = page.locator("body").inner_text(timeout=30000)
        if cls.LAW_LOGIN_REQUIRED_TEXT in body_text:
            raise RuntimeError("wk登录态失效或账号未登录，请检查账号密码")

        modal_locator = page.locator(cls.LAW_LOGIN_MODAL_USERNAME_SELECTOR)
        if modal_locator.count() > 0 and modal_locator.first.is_visible():
            raise RuntimeError("wk登录态失效或账号未登录，请检查账号密码")

        login_btn = page.locator(cls.LAW_LOGIN_BUTTON_SELECTOR)
        if login_btn.count() > 0 and login_btn.first.is_visible() and "账户登录" in body_text:
            raise RuntimeError("wk登录态失效或账号未登录，请检查账号密码")

    @staticmethod
    def _parse_detail_url(url: str) -> WeikeSearchItem | None:
        parsed_url = urlparse(url)
        path_match = re.search(r"/judgment-documents/detail/([^/?#]+)", parsed_url.path)
        if not path_match:
            return None

        doc_id_raw = path_match.group(1)
        query = parse_qs(parsed_url.query)
        search_id = (query.get("searchId") or [""])[0]
        module = (query.get("module") or [""])[0]

        return WeikeSearchItem(
            doc_id_raw=doc_id_raw,
            doc_id_unquoted=unquote(doc_id_raw),
            detail_url=urljoin("https://law.wkinfo.com.cn", url),
            title_hint="",
            search_id=search_id,
            module=module,
        )

    @staticmethod
    def _go_next_page(page: Page) -> bool:
        selectors = [
            "li.ant-pagination-next:not(.ant-pagination-disabled) button",
            "li.ant-pagination-next:not(.ant-pagination-disabled)",
            "a[rel='next']",
            "button:has-text('下一页')",
            "a:has-text('下一页')",
        ]
        for sel in selectors:
            locator = page.locator(sel)
            if locator.count() == 0:
                continue
            try:
                locator.first.click(timeout=5000)
                page.wait_for_timeout(2500)
                return True
            except Exception:
                continue
        return False

    def _is_search_api_degraded(self, *, session: WeikeSession) -> bool:
        degraded_until = float(getattr(session, "search_api_degraded_until_epoch", 0.0) or 0.0)
        if degraded_until <= 0:
            return False
        if degraded_until <= time.time():
            self._reset_search_api_health(session=session)
            return False
        return True

    @staticmethod
    def _search_api_degraded_wait_seconds(*, session: WeikeSession) -> int:
        degraded_until = float(getattr(session, "search_api_degraded_until_epoch", 0.0) or 0.0)
        remaining = degraded_until - time.time()
        return max(1, int(remaining)) if remaining > 0 else 0

    def _mark_search_api_empty(
        self,
        *,
        session: WeikeSession,
        keyword: str,
        offset: int,
        doc_count: int,
    ) -> None:
        session.search_api_empty_streak = int(getattr(session, "search_api_empty_streak", 0) or 0) + 1
        session.search_api_error_streak = 0
        threshold = self._resolve_search_api_degrade_streak_threshold()
        if session.search_api_empty_streak < threshold:
            return
        self._mark_search_api_degraded(
            session=session,
            reason="empty_result",
            keyword=keyword,
            offset=offset,
            doc_count=doc_count,
        )

    def _mark_search_api_error(self, *, session: WeikeSession, keyword: str, offset: int) -> None:
        session.search_api_error_streak = int(getattr(session, "search_api_error_streak", 0) or 0) + 1
        session.search_api_empty_streak = 0
        threshold = self._resolve_search_api_degrade_streak_threshold()
        if session.search_api_error_streak < threshold:
            return
        self._mark_search_api_degraded(
            session=session,
            reason="request_error",
            keyword=keyword,
            offset=offset,
            doc_count=int(getattr(session, "last_search_doc_count", 0) or 0),
        )

    def _mark_search_api_degraded(
        self,
        *,
        session: WeikeSession,
        reason: str,
        keyword: str,
        offset: int,
        doc_count: int,
    ) -> None:
        cooldown_seconds = self._resolve_search_api_degrade_cooldown_seconds()
        session.search_api_degraded_until_epoch = time.time() + cooldown_seconds
        logger.warning(
            (
                "私有wk API检索触发会话熔断（reason=%s, cooldown=%ss, keyword=%s, offset=%s, docCount=%s, "
                "empty_streak=%s, error_streak=%s）"
            ),
            reason,
            cooldown_seconds,
            keyword,
            offset,
            doc_count,
            session.search_api_empty_streak,
            session.search_api_error_streak,
            extra={
                "reason": reason,
                "cooldown_seconds": cooldown_seconds,
                "keyword": keyword,
                "offset": offset,
                "doc_count": doc_count,
                "empty_streak": session.search_api_empty_streak,
                "error_streak": session.search_api_error_streak,
            },
        )

    @staticmethod
    def _reset_search_api_health(*, session: WeikeSession) -> None:
        session.search_api_empty_streak = 0
        session.search_api_error_streak = 0
        session.search_api_degraded_until_epoch = 0.0

    def _resolve_search_api_degrade_streak_threshold(self) -> int:
        raw = getattr(self, "_search_api_degrade_streak_threshold", 2)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 2
        return max(1, value)

    def _resolve_search_api_degrade_cooldown_seconds(self) -> int:
        raw = getattr(self, "_search_api_degrade_cooldown_seconds", 180)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 180
        return max(30, value)

    @staticmethod
    def _compact_error_message(exc: Exception, *, max_len: int = 200) -> str:
        text = str(exc or "").strip() or exc.__class__.__name__
        if len(text) <= max_len:
            return text
        return f"{text[: max_len - 3]}..."

    @staticmethod
    def _record_search_event(
        *,
        session: WeikeSession,
        source: str,
        interface_name: str,
        method: str = "",
        url: str = "",
        status_code: int | None = None,
        duration_ms: int = 0,
        success: bool,
        error_code: str = "",
        error_message: str = "",
        request_summary: object = None,
        response_summary: object = None,
    ) -> None:
        LegalResearchTaskEventService.record_event(
            task_id=getattr(session, "task_id", ""),
            stage="search",
            source=source,
            interface_name=interface_name,
            method=method,
            url=url,
            status_code=status_code,
            duration_ms=duration_ms,
            success=success,
            error_code=error_code,
            error_message=error_message,
            request_summary=request_summary,
            response_summary=response_summary,
        )
