from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright


@dataclass
class WeikeSearchItem:
    doc_id_raw: str
    doc_id_unquoted: str
    detail_url: str
    title_hint: str
    search_id: str
    module: str


@dataclass
class WeikeCaseDetail:
    doc_id_raw: str
    doc_id_unquoted: str
    detail_url: str
    search_id: str
    module: str
    title: str
    court_text: str
    document_number: str
    judgment_date: str
    case_digest: str
    content_text: str
    raw_meta: dict[str, Any]


@dataclass
class WeikeSession:
    playwright: Playwright | None = None
    browser: Browser | None = None
    context: BrowserContext | None = None
    page: Page | None = None
    http_client: Any | None = None
    username: str = ""
    password: str = ""
    login_url: str | None = None
    search_via_api_enabled: bool = False

    def close(self) -> None:
        try:
            if self.page is not None:
                self.page.close()
        except Exception:
            pass
        try:
            if self.context is not None:
                self.context.close()
        except Exception:
            pass
        try:
            if self.browser is not None:
                self.browser.close()
        except Exception:
            pass
        try:
            if self.playwright is not None:
                self.playwright.stop()
        except Exception:
            pass
        try:
            close_http = getattr(self.http_client, "close", None)
            if callable(close_http):
                close_http()
        except Exception:
            pass
