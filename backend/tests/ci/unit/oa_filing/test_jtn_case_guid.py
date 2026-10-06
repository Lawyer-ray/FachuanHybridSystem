"""JtnCaseGuidScript（案号查 GUID，方法一）可测单元单测（无网络）。

覆盖：VIEWSTATE 提取、登录页判定、GUID 提取（行解析 + 正则兜底）、
完整查询编排（命中/多命中/0 命中/会话失效重试/登录失败）、
ScriptExecutorService.lookup_oa_case_guid 装配与错误映射。
HTTP 全部走 httpx.MockTransport 或实例打桩。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from apps.oa_filing.services.oa_scripts.jtn.case_guid.service import (
    JtnCaseGuidScript,
    extract_case_guids,
    extract_viewstate_fields,
)
from apps.oa_filing.services.oa_scripts.jtn.http_session import is_oa_login_page

_GUID_A = "b0219b56-3968-48a8-8e12-3ca86bf160ce"
_GUID_B = "0f2b7a11-1111-2222-3333-444455556666"

_CASE_NO = "2026TEST0001"


def _list_page_html() -> str:
    return (
        "<html><body><form id='aspnetForm'>"
        f'<input type="hidden" id="__VIEWSTATE" value="VS-{_CASE_NO}" />'
        '<input type="hidden" id="__VIEWSTATEGENERATOR" value="134513E2" />'
        "</form></body></html>"
    )


def _result_page_html(*guids: str, case_no: str = _CASE_NO) -> str:
    rows = "".join(
        f"<tr><td>{case_no} 案件</td>"
        f"<td><a href='../project/projectView.aspx?keyid={g}&FirstModel=PROJECT'>查看</a></td></tr>"
        for g in guids
    )
    return f"<html><body><table>{rows}</table></body></html>"


def _login_page_html() -> str:
    return "<html><body>location.replace('https://ims.jtn.com/member/login.aspx?rurl=x')</body></html>"


def _make_script(handler: Any, *, http_login: Any = None, cached_cookies: Any = None) -> tuple[JtnCaseGuidScript, Any]:
    """构造脚本实例：http_login/load_cookies 打桩 + MockTransport 客户端，返回 (script, http_login mock)。"""
    script = JtnCaseGuidScript(account="acc", password="p")
    transport = httpx.MockTransport(handler)
    if http_login is None:
        http_login = AsyncMock(return_value={"ASP.NET_SessionId": "s1"})
    auth: Any = MagicMock()
    auth.http_login = http_login
    auth.load_cookies = MagicMock(return_value=cached_cookies)
    script._auth = auth

    def _build_client(*, cookies: dict[str, str]) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": "test"},
            follow_redirects=True,
            timeout=5,
            cookies=cookies,
            trust_env=False,
            transport=transport,
        )

    script._build_client = _build_client  # type: ignore[method-assign]
    return script, http_login


# ──────────── VIEWSTATE 提取 ────────────


class TestExtractViewstateFields:
    def test_present(self):
        fields = extract_viewstate_fields(_list_page_html())
        assert fields == {"__VIEWSTATE": f"VS-{_CASE_NO}", "__VIEWSTATEGENERATOR": "134513E2"}

    def test_absent(self):
        assert extract_viewstate_fields("<html><body>登录页</body></html>") == {}


# ──────────── 登录页判定 ────────────


class TestIsOaLoginPage:
    def test_login_url(self):
        assert is_oa_login_page("https://ims.jtn.com/member/login.aspx?rurl=x", "任意内容") is True

    def test_location_replace_placeholder(self):
        assert is_oa_login_page("https://ims.jtn.com/project/index.aspx", _login_page_html()) is True

    def test_normal_page(self):
        assert is_oa_login_page("https://ims.jtn.com/project/index.aspx", _list_page_html()) is False

    def test_marker_in_long_page_is_not_login(self):
        long_page = "x" * 3000 + "location.replace(...)"
        assert is_oa_login_page("https://ims.jtn.com/project/index.aspx", long_page) is False


# ──────────── GUID 提取 ────────────


class TestExtractCaseGuids:
    def test_row_parse_single(self):
        html = _result_page_html(_GUID_A)
        assert extract_case_guids(html, _CASE_NO) == [_GUID_A]

    def test_row_parse_multi_keeps_order_and_dedupes(self):
        html = _result_page_html(_GUID_B, _GUID_A, _GUID_B)
        assert extract_case_guids(html, _CASE_NO) == [_GUID_B, _GUID_A]

    def test_no_rows_found_returns_empty(self):
        # lxml 可解析但无命中行：视为真 0 命中，不整页捞回（防误提页面其他区域的 keyid）
        html = f"<div>杂乱文本</div><a href='/p?keyid={_GUID_A}&x=1'>链接</a>"
        assert extract_case_guids(html, _CASE_NO) == []

    def test_unparseable_html_falls_back_to_regex(self):
        # lxml 解析失败（非法 HTML 触发异常的构造）→ 回退文档同款整页正则
        broken = f"<a href='/p?keyid={_GUID_A}&x=1'>链接"
        with patch(
            "apps.oa_filing.services.oa_scripts.jtn.case_guid.service.lxml_html.fromstring",
            side_effect=ValueError("boom"),
        ):
            assert extract_case_guids(broken, _CASE_NO) == [_GUID_A]

    def test_rows_without_case_no_excluded(self):
        html = _result_page_html(_GUID_A, case_no="2099ZZZ0001")
        assert extract_case_guids(html, _CASE_NO) == []

    def test_no_hit_returns_empty(self):
        assert extract_case_guids(_list_page_html(), _CASE_NO) == []


# ──────────── 查询编排 ────────────


class TestLookupCaseGuids:
    @pytest.mark.asyncio
    async def test_empty_keyword_skips_network(self):
        called = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["n"] += 1
            return httpx.Response(200, text=_list_page_html())

        script, http_login = _make_script(handler)
        assert await script.lookup_case_guids("   ") == []
        assert called["n"] == 0
        http_login.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_single_hit(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(200, text=_list_page_html())
            body = request.content.decode()
            assert f"__VIEWSTATE=VS-{_CASE_NO}" in body or f"VS-{_CASE_NO}" in body
            assert _CASE_NO in body
            return httpx.Response(200, text=_result_page_html(_GUID_A))

        script, http_login = _make_script(handler)
        assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]
        http_login.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_hit_returns_empty_list(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(200, text=_list_page_html())
            return httpx.Response(200, text=_result_page_html(_GUID_A, case_no="2099ZZZ0001"))

        script, _ = _make_script(handler)
        assert await script.lookup_case_guids(_CASE_NO) == []

    @pytest.mark.asyncio
    async def test_expired_session_on_get_retries_with_fresh_login(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(200, text=_login_page_html())
            if request.method == "GET":
                return httpx.Response(200, text=_list_page_html())
            return httpx.Response(200, text=_result_page_html(_GUID_A))

        script, http_login = _make_script(handler)
        assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]
        assert http_login.await_count == 2

    @pytest.mark.asyncio
    async def test_expired_session_on_post_retries(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] <= 2:
                if calls["n"] == 2:
                    return httpx.Response(200, text=_login_page_html())
                return httpx.Response(200, text=_list_page_html())
            if request.method == "GET":
                return httpx.Response(200, text=_list_page_html())
            return httpx.Response(200, text=_result_page_html(_GUID_B))

        script, _ = _make_script(handler)
        assert await script.lookup_case_guids(_CASE_NO) == [_GUID_B]

    @pytest.mark.asyncio
    async def test_always_expired_raises_runtime_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_login_page_html())

        script, _ = _make_script(handler)
        with pytest.raises(RuntimeError):
            await script.lookup_case_guids(_CASE_NO)

    @pytest.mark.asyncio
    async def test_missing_viewstate_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html><body><form id='aspnetForm'></form></body></html>")

        script, _ = _make_script(handler)
        with pytest.raises(RuntimeError, match="__VIEWSTATE"):
            await script.lookup_case_guids(_CASE_NO)

    @pytest.mark.asyncio
    async def test_login_failure_propagates(self):
        failing_login = AsyncMock(side_effect=RuntimeError("OA 登录失败，账号或密码错误: acc"))
        script, http_login = _make_script(lambda request: httpx.Response(200, text="unused"), http_login=failing_login)
        with pytest.raises(RuntimeError, match="扫码登录"):
            await script.lookup_case_guids(_CASE_NO)
        assert http_login.await_count == 1

    @pytest.mark.asyncio
    async def test_cached_cookies_used_without_login(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(200, text=_list_page_html())
            return httpx.Response(200, text=_result_page_html(_GUID_A))

        cached = [{"name": "ASP.NET_SessionId", "value": "cached", "domain": "ims.jtn.com", "path": "/"}]
        script, http_login = _make_script(handler, cached_cookies=cached)
        assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]
        http_login.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_expired_cache_falls_back_to_http_login(self):
        fresh_calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if "cached" in request.headers.get("cookie", ""):
                return httpx.Response(200, text=_login_page_html())
            fresh_calls["n"] += 1
            if fresh_calls["n"] == 1:
                return httpx.Response(200, text=_list_page_html())
            return httpx.Response(200, text=_result_page_html(_GUID_A))

        cached = [{"name": "ASP.NET_SessionId", "value": "cached", "domain": "ims.jtn.com", "path": "/"}]
        script, http_login = _make_script(handler, cached_cookies=cached)
        assert await script.lookup_case_guids(_CASE_NO) == [_GUID_A]
        http_login.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_invalid_and_login_fails_friendly_error(self):
        failing_login = AsyncMock(side_effect=RuntimeError("OA 登录失败，账号或密码错误: acc"))
        cached = [{"name": "ASP.NET_SessionId", "value": "cached", "domain": "ims.jtn.com", "path": "/"}]
        script, _ = _make_script(
            lambda request: httpx.Response(200, text=_login_page_html()),
            http_login=failing_login,
            cached_cookies=cached,
        )
        with pytest.raises(RuntimeError, match="扫码登录"):
            await script.lookup_case_guids(_CASE_NO)


# ──────────── 调度器装配 ────────────


class TestLookupOaCaseGuidExecutor:
    def _make_user(self) -> MagicMock:
        return MagicMock(id=1)

    def test_missing_credential_raises(self):
        from apps.oa_filing.services import script_executor_service as mod

        service = mod.ScriptExecutorService()
        with patch.object(mod.ScriptExecutorService, "_find_credential", return_value=None):
            with pytest.raises(RuntimeError, match="未找到匹配凭证"):
                service.lookup_oa_case_guid(case_no=_CASE_NO, user=self._make_user())

    def test_success_returns_guids(self):
        import asyncio

        from apps.oa_filing.services import script_executor_service as mod

        adapter = MagicMock()
        captured: dict[str, Any] = {}

        async def fake_lookup(case_no: str, credential: Any) -> list[str]:
            captured["case_no"] = case_no
            captured["credential"] = credential
            return [_GUID_A]

        adapter.lookup_case_guid = fake_lookup
        credential = MagicMock(account="acc", password="p")

        with (
            patch.object(mod.ScriptExecutorService, "_find_credential", return_value=credential),
            patch.object(mod, "create_adapter", return_value=adapter) as mock_create,
            patch.object(mod, "run_coro_sync", side_effect=lambda coro, **kw: asyncio.run(coro)),
        ):
            result = mod.ScriptExecutorService().lookup_oa_case_guid(case_no=f"  {_CASE_NO}  ", user=self._make_user())

        assert result == [_GUID_A]
        assert captured["case_no"] == _CASE_NO  # strip 生效
        assert captured["credential"] is credential
        mock_create.assert_called_once_with("金诚同达OA", "acc", "p")

    def test_error_mapped_to_friendly_message(self):
        import asyncio

        from apps.oa_filing.services import script_executor_service as mod

        adapter = MagicMock()

        async def fake_lookup(case_no: str, credential: Any) -> list[str]:
            raise RuntimeError("Read timed out")

        adapter.lookup_case_guid = fake_lookup
        credential = MagicMock(account="acc", password="p")

        with (
            patch.object(mod.ScriptExecutorService, "_find_credential", return_value=credential),
            patch.object(mod, "create_adapter", return_value=adapter),
            patch.object(mod, "run_coro_sync", side_effect=lambda coro, **kw: asyncio.run(coro)),
        ):
            with pytest.raises(RuntimeError, match="VPN"):
                mod.ScriptExecutorService().lookup_oa_case_guid(case_no=_CASE_NO, user=self._make_user())

    @pytest.mark.django_db
    def test_query_uses_requesting_users_own_credential(self):
        """谁登录就用谁的 JTN 账号发起查询：两位律师各配各的凭证，请求者 A 不得用到 B 的。"""
        import asyncio

        from apps.oa_filing.services import script_executor_service as mod
        from apps.organization.models import AccountCredential, Lawyer

        lawyer_a = Lawyer.objects.create_user(username="guid_user_a", real_name="甲律师")
        lawyer_b = Lawyer.objects.create_user(username="guid_user_b", real_name="乙律师")
        AccountCredential.objects.create(
            lawyer=lawyer_a,
            site_name="金诚同达OA",
            account="acct_a",
            password="pa-not-secret",  # pragma: allowlist secret
        )
        AccountCredential.objects.create(
            lawyer=lawyer_b,
            site_name="金诚同达OA",
            account="acct_b",
            password="pb-not-secret",  # pragma: allowlist secret
        )

        captured: dict[str, Any] = {}

        class _FakeAdapter:
            async def lookup_case_guid(self, case_no: str, credential: Any) -> list[str]:
                captured["credential_account"] = str(credential.account)
                return []

        def fake_create_adapter(site_name: str, account: str, password: str) -> _FakeAdapter:
            captured["adapter_account"] = account
            return _FakeAdapter()

        with (
            patch.object(mod, "create_adapter", side_effect=fake_create_adapter),
            patch.object(mod, "run_coro_sync", side_effect=lambda coro, **kw: asyncio.run(coro)),
        ):
            mod.ScriptExecutorService().lookup_oa_case_guid(case_no=_CASE_NO, user=lawyer_a)

        assert captured["adapter_account"] == "acct_a"
        assert captured["credential_account"] == "acct_a"
