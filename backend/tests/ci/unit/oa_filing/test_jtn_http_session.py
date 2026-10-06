"""jtn/http_session 共享会话基建单测（无网络）。

覆盖失效判定小件（登录 URL / 占位页 / 表单探测 / 错误文案 / 组合判定）、
缓存 cookies 两种形态（扁平 dict / 原样 playwright 格式）、
http_login_cookies 友好错误包装、resolve_session_cookies 缓存优先、
build_client 参数组合、to_context_cookie_list 域名兜底。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from apps.oa_filing.services.oa_scripts.jtn import http_session as hs


def _auth(load_cookies=None, http_login=None) -> MagicMock:
    auth = MagicMock()
    auth.load_cookies = MagicMock(return_value=load_cookies)
    auth.http_login = http_login or AsyncMock(return_value={"ASP.NET_SessionId": "fresh"})
    return auth


# ──────────── 失效判定小件 ────────────


class TestDetectionHelpers:
    def test_is_login_url(self):
        assert hs.is_login_url("https://ims.jtn.com/member/login.aspx?rurl=x") is True
        assert hs.is_login_url("https://ims.jtn.com/project/index.aspx") is False

    def test_is_session_placeholder(self):
        assert hs.is_session_placeholder("location.replace('...login...')") is True
        assert hs.is_session_placeholder("x" * 3000 + "location.replace(...)") is False
        assert hs.is_session_placeholder("<html>正常页面</html>") is False

    def test_has_login_form_head_window_only(self):
        assert hs.has_login_form('<input name="userid"><input name="password">') is True
        long_padding = "x" * 3000
        assert hs.has_login_form(long_padding + '<input name="userid"><input name="password">') is False
        assert hs.has_login_form('<input name="userid">') is False

    def test_has_login_error_text(self):
        assert hs.has_login_error_text("提示：账号或密码错误，请重试") is True
        assert hs.has_login_error_text("Invalid Password") is True
        assert hs.has_login_error_text("正常内容") is False

    def test_is_oa_login_page_combined(self):
        assert hs.is_oa_login_page("https://ims.jtn.com/member/login.aspx", "任意") is True
        assert hs.is_oa_login_page("https://ims.jtn.com/p", "location.replace(...)") is True
        assert hs.is_oa_login_page("https://ims.jtn.com/p", "账号或密码错误") is True
        assert hs.is_oa_login_page("https://ims.jtn.com/project/index.aspx", "<html>列表</html>") is False


# ──────────── 会话获取 ────────────


class TestSessionCookies:
    def test_cached_cookies_flat(self):
        auth = _auth(load_cookies=[{"name": "s", "value": "1", "domain": "ims.jtn.com", "path": "/"}])
        assert hs.cached_cookies(auth) == {"s": "1"}

    def test_cached_cookies_none(self):
        assert hs.cached_cookies(_auth(load_cookies=None)) is None

    def test_cached_cookies_raw_preserves_domain(self):
        raw = [{"name": "s", "value": "1", "domain": ".jtn.com", "path": "/", "expires": 1.0}]
        assert hs.cached_cookies_raw(_auth(load_cookies=raw)) == raw

    @pytest.mark.asyncio
    async def test_http_login_cookies_friendly_wrap(self):
        auth = _auth(http_login=AsyncMock(side_effect=RuntimeError("OA 登录失败，账号或密码错误: acc")))
        with pytest.raises(RuntimeError, match="扫码登录"):
            await hs.http_login_cookies(auth)

    @pytest.mark.asyncio
    async def test_http_login_cookies_passthrough(self):
        auth = _auth()
        assert await hs.http_login_cookies(auth) == {"ASP.NET_SessionId": "fresh"}

    @pytest.mark.asyncio
    async def test_resolve_session_cookies_prefers_cache(self):
        auth = _auth(load_cookies=[{"name": "s", "value": "cached", "domain": "ims.jtn.com", "path": "/"}])
        assert await hs.resolve_session_cookies(auth) == {"s": "cached"}
        auth.http_login.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_resolve_session_cookies_falls_back_to_login(self):
        auth = _auth(load_cookies=None)
        assert await hs.resolve_session_cookies(auth) == {"ASP.NET_SessionId": "fresh"}
        auth.http_login.assert_awaited_once()


# ──────────── 客户端构造 ────────────


class TestBuildClient:
    def test_default_settings(self):
        client = hs.build_client(cookies={"s": "1"})
        assert client.timeout == httpx.Timeout(20)
        assert client.headers.get("user-agent", "").startswith("Mozilla/5.0")
        assert client.headers.get("connection") != "close"
        assert client.trust_env is False

    def test_connection_close(self):
        client = hs.build_client(cookies={"s": "1"}, connection_close=True)
        assert client.headers.get("connection") == "close"

    def test_custom_timeout(self):
        client = hs.build_client(timeout=5)
        assert client.timeout == httpx.Timeout(5)


class TestToContextCookieList:
    def test_default_domain(self):
        result = hs.to_context_cookie_list({"s": "1", "t": "2"})
        assert result == [
            {"name": "s", "value": "1", "domain": "ims.jtn.com", "path": "/"},
            {"name": "t", "value": "2", "domain": "ims.jtn.com", "path": "/"},
        ]

    def test_empty(self):
        assert hs.to_context_cookie_list({}) == []


# ──────────── auth.http_login 强判定（升级后语义） ────────────


class TestAuthHttpLoginDetection:
    def _fake_client_cls(self, *, post_url: str, post_text: str, jar: dict[str, str] | None = None) -> type:
        """构造假 AsyncClient：GET 返回带 CSRF 的登录页，POST 返回指定响应。"""

        class _FakeClient:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self.cookies = httpx.Cookies(jar or {})

            async def __aenter__(self) -> _FakeClient:
                return self

            async def __aexit__(self, *exc: Any) -> None:
                return None

            async def get(self, url: str) -> MagicMock:
                resp = MagicMock()
                resp.text = '<input type="hidden" name="CSRFToken" value="c">'
                return resp

            async def post(self, url: str, data: Any) -> MagicMock:
                resp = MagicMock()
                resp.url = post_url
                resp.text = post_text
                return resp

        return _FakeClient

    @pytest.mark.asyncio
    async def test_login_url_without_form_is_not_failure(self):
        """停在登录页但无表单（如跳转中间页）不算账密错误。"""
        from apps.oa_filing.services.oa_scripts.jtn.auth.service import JtnAuthService

        auth = JtnAuthService("acc", "p")
        fake_cls = self._fake_client_cls(
            post_url="https://ims.jtn.com/member/login.aspx?ok=1",
            post_text='<input name="csrf">登录成功，正在跳转',
            jar={"ASP.NET_SessionId": "s"},
        )
        with patch("apps.oa_filing.services.oa_scripts.jtn.auth.service.httpx.AsyncClient", fake_cls):
            cookies = await auth.http_login()
        assert cookies == {"ASP.NET_SessionId": "s"}

    @pytest.mark.asyncio
    async def test_stayed_on_login_with_form_raises(self):
        """账密错误：停在登录页且带账密表单。"""
        from apps.oa_filing.services.oa_scripts.jtn.auth.service import JtnAuthService

        auth = JtnAuthService("acc", "bad")
        fake_cls = self._fake_client_cls(
            post_url="https://ims.jtn.com/member/login.aspx",
            post_text='<input name="userid"><input name="password">登录页',
        )
        with patch("apps.oa_filing.services.oa_scripts.jtn.auth.service.httpx.AsyncClient", fake_cls):
            with pytest.raises(RuntimeError, match="账号或密码错误"):
                await auth.http_login()

    @pytest.mark.asyncio
    async def test_login_error_text_raises(self):
        """同页渲染失败文案也判失败。"""
        from apps.oa_filing.services.oa_scripts.jtn.auth.service import JtnAuthService

        auth = JtnAuthService("acc", "bad")
        fake_cls = self._fake_client_cls(
            post_url="https://ims.jtn.com/main",
            post_text="<html>账号或密码错误</html>",
        )
        with patch("apps.oa_filing.services.oa_scripts.jtn.auth.service.httpx.AsyncClient", fake_cls):
            with pytest.raises(RuntimeError, match="账号或密码错误"):
                await auth.http_login()
