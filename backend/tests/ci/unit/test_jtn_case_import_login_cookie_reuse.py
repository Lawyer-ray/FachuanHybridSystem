from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

import apps.oa_filing.services.oa_scripts.jtn.case_import.http_client as jtn_http_client
import apps.oa_filing.services.oa_scripts.jtn.case_import.playwright_browser as jtn_playwright_browser
from apps.oa_filing.services.oa_scripts.jtn.case_import import CaseListFormState, JtnCaseImportScript


@pytest.mark.asyncio
async def test_login_prefers_cached_http_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    script = JtnCaseImportScript(account="example", password="example", headless=True)

    class _FakeContext:
        def __init__(self) -> None:
            self.cookie_batches: list[list[dict[str, str]]] = []

        async def add_cookies(self, cookies: list[dict[str, str]]) -> None:
            self.cookie_batches.append(cookies)

    class _ShouldNotCreateClient:  # pragma: no cover
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            _ = args
            _ = kwargs
            raise AssertionError("reuse cached cookies path should not create httpx.AsyncClient")

    fake_context = _FakeContext()
    script._context = fake_context  # type: ignore[assignment]
    script._http_cookies_cache = {"ASP.NET_SessionId": "cookie-1", "CSRFToken": "csrf-1"}
    monkeypatch.setattr(jtn_playwright_browser.httpx, "AsyncClient", _ShouldNotCreateClient)

    await script._login()

    assert len(fake_context.cookie_batches) == 1
    names = {item["name"] for item in fake_context.cookie_batches[0]}
    assert names == {"ASP.NET_SessionId", "CSRFToken"}


@pytest.mark.asyncio
async def test_http_login_disables_env_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    script = JtnCaseImportScript(account="example", password="example", headless=True)
    captured: dict[str, Any] = {}

    class _FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            _ = args
            captured.update(kwargs)
            self.cookies = httpx.Cookies({"ASP.NET_SessionId": "cookie-1"})

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            _ = exc_type
            _ = exc
            _ = tb

        async def get(self, url: str) -> httpx.Response:
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                text="<input name='CSRFToken' value='csrf-1' />",
            )

        async def post(self, url: str, data: dict[str, str]) -> httpx.Response:
            _ = data
            _ = url
            return httpx.Response(
                200,
                request=httpx.Request("POST", "https://ims.jtn.com/project/index.aspx"),
                text="ok",
            )

    monkeypatch.setattr("apps.oa_filing.services.oa_scripts.jtn.auth.service.httpx.AsyncClient", _FakeClient)

    cookies = await script._auth.http_login()

    assert captured["trust_env"] is False
    assert cookies == {"ASP.NET_SessionId": "cookie-1"}


@pytest.mark.asyncio
async def test_name_search_http_session_disables_env_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    script = JtnCaseImportScript(account="example", password="example", headless=True)
    captured: dict[str, Any] = {}

    class _FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            _ = args
            captured.update(kwargs)

        async def aclose(self) -> None:
            return

    async def _mock_get_or_login() -> dict[str, str]:
        return {"ASP.NET_SessionId": "cookie-1"}

    async def _mock_load_form(client: Any) -> CaseListFormState:
        return CaseListFormState(action_url="https://ims.jtn.com/project/index.aspx", payload={})

    monkeypatch.setattr(script, "_get_or_login_http_cookies", _mock_get_or_login)
    monkeypatch.setattr(script, "_load_case_list_form_state", _mock_load_form)
    monkeypatch.setattr(jtn_http_client.httpx, "AsyncClient", _FakeClient)

    await script._ensure_name_search_http_session()

    assert captured["trust_env"] is False


def test_login_page_with_form_matches_shared_detection() -> None:
    """登录失败判定已收敛至 http_session：登录页 + 账密表单即失败。"""
    from apps.oa_filing.services.oa_scripts.jtn.http_session import has_login_form, is_login_url

    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://ims.jtn.com/member/login.aspx"),
        text='<form><input name="userid" /><input name="password" /></form>',
    )

    assert is_login_url(response.url) and has_login_form(response.text) is True


def test_logout_success_page_not_matched_by_shared_detection() -> None:
    """登出链接的正常页面不是登录失败。"""
    from apps.oa_filing.services.oa_scripts.jtn.http_session import has_login_form, is_login_url

    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://ims.jtn.com/project/index.aspx"),
        text='<a href="/member/logout.aspx">logout</a>',
    )

    assert (is_login_url(response.url) or has_login_form(response.text)) is False
