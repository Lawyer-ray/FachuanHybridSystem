from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from playwright.sync_api import Page

from . import api_optional
from .types import WeikeSearchItem, WeikeSession

logger = logging.getLogger(__name__)


class WeikeSearchMixin:
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
                        return items
                    if offset > 0:
                        return []
                    logger.warning("私有wk API检索返回空结果，回退DOM检索", extra={"keyword": keyword})
                except Exception:
                    logger.exception("私有wk API检索失败，回退DOM检索", extra={"keyword": keyword})

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
        if session.page is None:
            raise RuntimeError("Playwright页面未就绪")
        page = session.page
        page.goto(self.LAW_LIST_URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_selector("input[name='keyword']", timeout=60000)
        page.fill("input[name='keyword'][placeholder='在裁判文书中搜索...']", keyword)
        page.get_by_role("button", name="搜索", exact=True).click()
        page.wait_for_timeout(3500)

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
                    return items

            if not self._go_next_page(page):
                break

        return items

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
