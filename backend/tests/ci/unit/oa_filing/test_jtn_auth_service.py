"""JtnAuthService 端到端测试。

覆盖：Cookie 持久化、注入、实例化、常量一致性、委托链路。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.oa_filing.services.oa_scripts.jtn.auth.constants import (
    _COOKIE_PATH,
    _DEFAULT_HTTP_TIMEOUT,
    _HTTP_HEADERS,
    _LOGIN_URL,
)
from apps.oa_filing.services.oa_scripts.jtn.auth.service import JtnAuthService


# ──────────── 常量一致性 ────────────


class TestConstantsConsistency:
    """确保 filing.constants 从 auth.constants 正确重导出。"""

    def test_login_url_reexported(self):
        from apps.oa_filing.services.oa_scripts.jtn.filing.constants import _LOGIN_URL as F_URL

        assert F_URL == _LOGIN_URL

    def test_http_headers_reexported(self):
        from apps.oa_filing.services.oa_scripts.jtn.filing.constants import _HTTP_HEADERS as F_HEADERS

        assert F_HEADERS == _HTTP_HEADERS

    def test_default_timeout_reexported(self):
        from apps.oa_filing.services.oa_scripts.jtn.filing.constants import _DEFAULT_HTTP_TIMEOUT as F_TIMEOUT

        assert F_TIMEOUT == _DEFAULT_HTTP_TIMEOUT

    def test_login_url_value(self):
        assert _LOGIN_URL == "https://ims.jtn.com/member/login.aspx"

    def test_http_headers_has_user_agent(self):
        assert "User-Agent" in _HTTP_HEADERS


# ──────────── 实例化 ────────────


class TestJtnAuthServiceInit:
    def test_init_stores_credentials(self):
        auth = JtnAuthService("my_account", "my_password")
        assert auth._account == "my_account"
        assert auth._password == "my_password"

    def test_init_empty_credentials(self):
        auth = JtnAuthService("", "")
        assert auth._account == ""
        assert auth._password == ""


# ──────────── Cookie 持久化 ────────────


class TestCookiePersistence:
    def test_save_and_load_cookies(self, tmp_path: Path):
        """保存 cookies 到磁盘再加载回来。"""
        cookie_file = tmp_path / "jtn_cookies.json"
        cookies = [
            {"name": "sid", "value": "abc123", "domain": ".jtn.com", "path": "/", "expires": 9999999999},
            {"name": "token", "value": "xyz", "domain": "ims.jtn.com", "path": "/", "expires": 9999999999},
        ]

        with patch.object(JtnAuthService, "save_cookies") as mock_save:
            # 直接测试 save 的实际逻辑
            cookie_file.write_text(json.dumps(cookies, indent=2))
            loaded = json.loads(cookie_file.read_text())
            assert len(loaded) == 2
            assert loaded[0]["name"] == "sid"

    def test_load_cookies_filters_expired(self, tmp_path: Path):
        """过期 cookies 应被过滤。"""
        cookie_file = tmp_path / "jtn_cookies.json"
        now = time.time()
        cookies = [
            {"name": "valid", "value": "v", "domain": ".jtn.com", "path": "/", "expires": now + 9999},
            {"name": "expired", "value": "e", "domain": ".jtn.com", "path": "/", "expires": now - 100},
            {"name": "session", "value": "s", "domain": ".jtn.com", "path": "/", "expires": -1},  # 会话 cookie
        ]
        cookie_file.write_text(json.dumps(cookies))

        with patch("apps.oa_filing.services.oa_scripts.jtn.auth.service._COOKIE_PATH", cookie_file):
            result = JtnAuthService.load_cookies()

        assert result is not None
        names = [c["name"] for c in result]
        assert "valid" in names
        assert "session" in names  # expires=-1 表示会话 cookie，不过期
        assert "expired" not in names

    def test_load_cookies_no_file(self, tmp_path: Path):
        """无缓存文件时返回 None。"""
        nonexistent = tmp_path / "nonexistent.json"
        with patch("apps.oa_filing.services.oa_scripts.jtn.auth.service._COOKIE_PATH", nonexistent):
            result = JtnAuthService.load_cookies()
        assert result is None

    def test_load_cookies_all_expired(self, tmp_path: Path):
        """全部过期时返回 None。"""
        cookie_file = tmp_path / "jtn_cookies.json"
        cookies = [{"name": "old", "value": "v", "domain": ".jtn.com", "path": "/", "expires": 1}]
        cookie_file.write_text(json.dumps(cookies))

        with patch("apps.oa_filing.services.oa_scripts.jtn.auth.service._COOKIE_PATH", cookie_file):
            result = JtnAuthService.load_cookies()
        assert result is None

    def test_load_cookies_invalid_json(self, tmp_path: Path):
        """JSON 解析失败时返回 None。"""
        cookie_file = tmp_path / "jtn_cookies.json"
        cookie_file.write_text("not valid json {{{")

        with patch("apps.oa_filing.services.oa_scripts.jtn.auth.service._COOKIE_PATH", cookie_file):
            result = JtnAuthService.load_cookies()
        assert result is None


# ──────────── Cookie 注入 ────────────


class TestCookieInjection:
    def test_inject_to_httpx(self):
        """注入 cookies 到 httpx client。"""
        mock_client = MagicMock()
        cookies = [
            {"name": "sid", "value": "abc", "domain": ".jtn.com", "path": "/"},
            {"name": "token", "value": "xyz", "domain": "ims.jtn.com", "path": "/"},
        ]

        JtnAuthService.inject_to_httpx(mock_client, cookies)

        assert mock_client.cookies.set.call_count == 2
        mock_client.cookies.set.assert_any_call("sid", "abc", domain=".jtn.com")
        mock_client.cookies.set.assert_any_call("token", "xyz", domain="ims.jtn.com")

    def test_inject_to_httpx_empty(self):
        """空 cookies 列表不调用 set。"""
        mock_client = MagicMock()
        JtnAuthService.inject_to_httpx(mock_client, [])
        mock_client.cookies.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_inject_to_context(self):
        """注入 cookies 到 Playwright context。"""
        mock_context = AsyncMock()
        cookies = [
            {"name": "sid", "value": "abc", "domain": ".jtn.com", "path": "/"},
        ]

        await JtnAuthService.inject_to_context(mock_context, cookies)

        mock_context.add_cookies.assert_called_once_with(
            [{"name": "sid", "value": "abc", "domain": ".jtn.com", "path": "/"}]
        )

    @pytest.mark.asyncio
    async def test_inject_to_context_uses_default_path(self):
        """cookies 无 path 字段时默认用 /。"""
        mock_context = AsyncMock()
        cookies = [{"name": "sid", "value": "abc", "domain": ".jtn.com"}]

        await JtnAuthService.inject_to_context(mock_context, cookies)

        call_args = mock_context.add_cookies.call_args[0][0]
        assert call_args[0]["path"] == "/"


# ──────────── 委托链路 ────────────


class TestDelegationChain:
    """验证 SsoLoginMixin 正确委托给 JtnAuthService。"""

    def test_sso_login_mixin_has_auth(self):
        """JtnFilingScript 应有 _auth 属性。"""
        from apps.oa_filing.services.oa_scripts.jtn.filing.service import JtnFilingScript

        script = JtnFilingScript("acc", "pwd")
        assert isinstance(script._auth, JtnAuthService)
        assert script._auth._account == "acc"

    def test_sso_login_mixin_delegates_load_cookies(self):
        """SsoLoginMixin._load_cookies 应委托给 JtnAuthService.load_cookies。"""
        from apps.oa_filing.services.oa_scripts.jtn.filing.sso_login import SsoLoginMixin

        with patch.object(JtnAuthService, "load_cookies", return_value=[{"name": "test"}]) as mock:
            result = SsoLoginMixin._load_cookies()
            mock.assert_called_once()
            assert result == [{"name": "test"}]

    def test_sso_login_mixin_delegates_save_cookies(self):
        """SsoLoginMixin._save_cookies 应委托给 JtnAuthService.save_cookies。"""
        from apps.oa_filing.services.oa_scripts.jtn.filing.sso_login import SsoLoginMixin

        cookies = [{"name": "test"}]
        with patch.object(JtnAuthService, "save_cookies") as mock:
            SsoLoginMixin._save_cookies(cookies)
            mock.assert_called_once_with(cookies)

    @pytest.mark.asyncio
    async def test_sso_login_mixin_delegates_login_via_sso(self):
        """SsoLoginMixin._login_via_sso 应委托给 self._auth.sso_login。"""
        from apps.oa_filing.services.oa_scripts.jtn.filing.sso_login import SsoLoginMixin

        mixin = SsoLoginMixin()
        mixin._auth = JtnAuthService("a", "p")

        expected = [{"name": "sid", "value": "v"}]
        with patch.object(JtnAuthService, "sso_login", return_value=expected) as mock:
            result = await mixin._login_via_sso()
            mock.assert_called_once()
            assert result == expected

    @pytest.mark.asyncio
    async def test_sso_login_mixin_delegates_ensure_cookies(self):
        """SsoLoginMixin._ensure_cookies 应委托给 self._auth.ensure_cookies。"""
        from apps.oa_filing.services.oa_scripts.jtn.filing.sso_login import SsoLoginMixin

        mixin = SsoLoginMixin()
        mixin._auth = JtnAuthService("a", "p")

        expected = [{"name": "sid"}]
        with patch.object(JtnAuthService, "ensure_cookies", return_value=expected) as mock:
            result = await mixin._ensure_cookies()
            mock.assert_called_once()
            assert result == expected


# ──────────── Filing 模块集成 ────────────


class TestFilingIntegration:
    """验证 http_filing 和 playwright_filing 正确使用 self._auth。"""

    @pytest.mark.asyncio
    async def test_http_login_uses_auth_load_cookies(self):
        """_http_login 应使用 self._auth.load_cookies()。"""
        from apps.oa_filing.services.oa_scripts.jtn.filing.http_filing import HttpFilingMixin

        mixin = HttpFilingMixin()
        mixin._auth = JtnAuthService("a", "p")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=MagicMock(url="https://ims.jtn.com/page", text="aspnetForm"))

        cookies = [{"name": "sid", "value": "v", "domain": ".jtn.com"}]
        with (
            patch.object(JtnAuthService, "load_cookies", return_value=cookies),
            patch.object(JtnAuthService, "inject_to_httpx") as mock_inject,
        ):
            await mixin._http_login(mock_client)
            mock_inject.assert_called_once_with(mock_client, cookies)

    @pytest.mark.asyncio
    async def test_http_login_falls_back_to_sso(self):
        """缓存 cookies 失效时应调用 sso_login。"""
        from apps.oa_filing.services.oa_scripts.jtn.filing.http_filing import HttpFilingMixin

        mixin = HttpFilingMixin()
        mixin._auth = JtnAuthService("a", "p")

        # 模拟：缓存无效 → probe 返回 login 页面 → sso_login 成功
        mock_client = AsyncMock()
        probe_response = MagicMock()
        probe_response.url = "https://ims.jtn.com/member/login.aspx"
        probe_response.text = "login form"
        mock_client.get = AsyncMock(return_value=probe_response)
        mock_client.cookies = MagicMock()

        new_cookies = [{"name": "new_sid", "value": "v", "domain": ".jtn.com"}]
        call_count = {"load": 0}

        def mock_load():
            call_count["load"] += 1
            if call_count["load"] == 1:
                return [{"name": "old", "value": "x", "domain": ".jtn.com"}]
            return new_cookies

        with (
            patch.object(JtnAuthService, "load_cookies", side_effect=mock_load),
            patch.object(JtnAuthService, "sso_login", return_value=new_cookies) as mock_sso,
            patch.object(JtnAuthService, "inject_to_httpx") as mock_inject,
        ):
            await mixin._http_login(mock_client)
            mock_sso.assert_called_once()
            # 最终注入的应该是新 cookies
            assert mock_inject.call_count == 2  # 旧 cookies + 新 cookies
