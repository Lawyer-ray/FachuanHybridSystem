from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from playwright.sync_api import BrowserContext, Page


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
    page: Page | None = None
    context: BrowserContext | None = None
    context_manager: Any | None = field(default=None, repr=False)
    http_client: Any | None = None
    username: str = ""
    password: str = ""
    login_url: str | None = None
    task_id: str = ""
    search_via_api_enabled: bool = False
    restricted_until_epoch: float = 0.0
    last_search_doc_count: int = 0
    search_api_empty_streak: int = 0
    search_api_error_streak: int = 0
    search_api_degraded_until_epoch: float = 0.0
    intercepted_payload: dict[str, Any] | None = None

    def close(self) -> None:  # pragma: no cover
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
            if self.context_manager is not None:
                self.context_manager.__exit__(None, None, None)
        except Exception:
            pass
        try:
            close_http = getattr(self.http_client, "close", None)
            if callable(close_http):
                close_http()
        except Exception:
            pass
