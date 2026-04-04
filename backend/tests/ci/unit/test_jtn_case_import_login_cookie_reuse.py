from __future__ import annotations

from typing import Any

import httpx
import pytest

import apps.oa_filing.services.oa_scripts.jtn_case_import as jtn_case_import_module
from apps.oa_filing.services.oa_scripts.jtn_case_import import JtnCaseImportScript


def test_login_prefers_cached_http_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    script = JtnCaseImportScript(account="demo", password="demo", headless=True)

    class _FakeContext:
        def __init__(self) -> None:
            self.cookie_batches: list[list[dict[str, str]]] = []

        def add_cookies(self, cookies: list[dict[str, str]]) -> None:
            self.cookie_batches.append(cookies)

    class _ShouldNotCreateClient:  # pragma: no cover
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            _ = args
            _ = kwargs
            raise AssertionError("reuse cached cookies path should not create httpx.Client")

    fake_context = _FakeContext()
    script._context = fake_context  # type: ignore[assignment]
    script._http_cookies_cache = {"ASP.NET_SessionId": "cookie-1", "CSRFToken": "csrf-1"}
    monkeypatch.setattr(jtn_case_import_module.httpx, "Client", _ShouldNotCreateClient)

    script._login()

    assert len(fake_context.cookie_batches) == 1
    names = {item["name"] for item in fake_context.cookie_batches[0]}
    assert names == {"ASP.NET_SessionId", "CSRFToken"}


def test_http_login_disables_env_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    script = JtnCaseImportScript(account="demo", password="demo", headless=True)
    captured: dict[str, Any] = {}

    class _FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            _ = args
            captured.update(kwargs)
            self.cookies = httpx.Cookies({"ASP.NET_SessionId": "cookie-1"})

        def __enter__(self) -> _FakeClient:
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            _ = exc_type
            _ = exc
            _ = tb

        def get(self, url: str) -> httpx.Response:
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                text="<input name='CSRFToken' value='csrf-1' />",
            )

        def post(self, url: str, data: dict[str, str]) -> httpx.Response:
            _ = data
            _ = url
            return httpx.Response(
                200,
                request=httpx.Request("POST", "https://ims.jtn.com/project/index.aspx"),
                text="ok",
            )

    monkeypatch.setattr(jtn_case_import_module.httpx, "Client", _FakeClient)

    cookies = script._http_login_and_get_cookies()

    assert captured["trust_env"] is False
    assert cookies == {"ASP.NET_SessionId": "cookie-1"}


def test_name_search_http_session_disables_env_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    script = JtnCaseImportScript(account="demo", password="demo", headless=True)
    captured: dict[str, Any] = {}

    class _FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            _ = args
            captured.update(kwargs)

        def close(self) -> None:
            return

    monkeypatch.setattr(script, "_get_or_login_http_cookies", lambda: {"ASP.NET_SessionId": "cookie-1"})
    monkeypatch.setattr(
        script,
        "_load_case_list_form_state",
        lambda client: jtn_case_import_module.CaseListFormState(action_url="https://ims.jtn.com/project/index.aspx", payload={}),
    )
    monkeypatch.setattr(jtn_case_import_module.httpx, "Client", _FakeClient)

    script._ensure_name_search_http_session()

    assert captured["trust_env"] is False


def test_is_login_failed_response_detects_login_form_page() -> None:
    script = JtnCaseImportScript(account="demo", password="demo", headless=True)
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://ims.jtn.com/member/login.aspx"),
        text='<form><input name="userid" /><input name="password" /></form>',
    )

    assert script._is_login_failed_response(response) is True


def test_is_login_failed_response_accepts_logout_success_page() -> None:
    script = JtnCaseImportScript(account="demo", password="demo", headless=True)
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://ims.jtn.com/project/index.aspx"),
        text='<a href="/member/logout.aspx">logout</a>',
    )

    assert script._is_login_failed_response(response) is False
