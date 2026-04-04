from __future__ import annotations

from typing import Any

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
