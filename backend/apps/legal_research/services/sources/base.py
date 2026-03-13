from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CaseSearchItem(Protocol):
    doc_id_raw: str
    doc_id_unquoted: str
    detail_url: str
    title_hint: str
    search_id: str
    module: str


@runtime_checkable
class CaseDetail(Protocol):
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


@runtime_checkable
class CaseSourceSession(Protocol):
    def close(self) -> None: ...


@runtime_checkable
class CaseSourceClient(Protocol):
    def open_session(
        self,
        *,
        username: str,
        password: str,
        login_url: str | None = None,
    ) -> CaseSourceSession: ...

    def search_cases(
        self,
        *,
        session: CaseSourceSession,
        keyword: str,
        max_candidates: int,
        max_pages: int = 10,
        offset: int = 0,
    ) -> list[CaseSearchItem]: ...

    def fetch_case_detail(self, *, session: CaseSourceSession, item: CaseSearchItem) -> CaseDetail: ...

    def download_pdf(self, *, session: CaseSourceSession, detail: CaseDetail) -> tuple[bytes, str] | None: ...
