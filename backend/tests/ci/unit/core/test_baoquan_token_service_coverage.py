"""apps/core/services/court_tokens/baoquan_token_service.py 单元测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.exceptions import TokenError
from apps.core.services.court_tokens.baoquan_token_service import BaoquanTokenService


class TestBaoquanTokenServiceConstants:
    """测试类常量。"""

    def test_court_site_name(self) -> None:
        assert BaoquanTokenService.COURT_SITE_NAME == "court_zxfw"

    def test_baoquan_site_name(self) -> None:
        assert BaoquanTokenService.BAOQUAN_SITE_NAME == "court_baoquan"

    def test_baoquan_token_prefix(self) -> None:
        assert BaoquanTokenService._BAOQUAN_TOKEN_PREFIX == "eyJhbGciOiJIUzUxMiJ9"


class TestGetValidBaoquanToken:
    """测试 get_valid_baoquan_token。"""

    @pytest.mark.asyncio
    async def test_raises_when_no_lawyer_id(self) -> None:
        """未指定用户时应抛出 TokenError。"""
        svc = BaoquanTokenService()

        with (
            patch("apps.core.services.wiring.get_organization_service", return_value=MagicMock()),
            patch("apps.core.services.wiring.get_court_token_store_service", return_value=MagicMock()),
        ):
            with pytest.raises(TokenError, match="未指定当前用户"):
                await svc.get_valid_baoquan_token()

    @pytest.mark.asyncio
    async def test_returns_cached_token_when_valid(self) -> None:
        """存在有效缓存 Token 时直接返回。"""
        svc = BaoquanTokenService()
        mock_credential = MagicMock()
        mock_credential.account = "test_account"
        mock_credential.url = "https://zxfw.court.gov.cn"

        mock_org = MagicMock()
        mock_org.get_credential_for_lawyer = MagicMock(return_value=mock_credential)

        mock_token_info = MagicMock()
        mock_token_info.token = "eyJhbGciOiJIUzUxMiJ9.cached_token"  # allowlist secret
        mock_token_info.account = "test_account"

        mock_token_store = MagicMock()
        mock_token_store.get_latest_valid_token_internal = MagicMock(return_value=mock_token_info)

        async def mock_sync(fn, **kw):  # type: ignore[no-untyped-def]
            return fn()

        with (
            patch("apps.core.services.wiring.get_organization_service", return_value=mock_org),
            patch("apps.core.services.wiring.get_court_token_store_service", return_value=mock_token_store),
            patch("asgiref.sync.sync_to_async", side_effect=mock_sync),
        ):
            result = await svc.get_valid_baoquan_token(lawyer_id=1)

        assert result == "eyJhbGciOiJIUzUxMiJ9.cached_token"


class TestTryHttpBaoquanToken:
    """测试 _try_http_baoquan_token。"""

    @pytest.mark.asyncio
    async def test_returns_none_when_plugin_unavailable(self) -> None:
        """插件不可用时返回 None。"""
        svc = BaoquanTokenService()

        mock_module = MagicMock()
        mock_module.is_available.return_value = False

        with patch.dict("sys.modules", {
            "apps.automation.services.scraper.sites.court_zxfw_login_private": mock_module,
        }):
            result = await svc._try_http_baoquan_token("account", "password")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_bad_token_format(self) -> None:
        """Token 格式不正确时返回 None。"""
        svc = BaoquanTokenService()

        mock_svc_instance = MagicMock()
        mock_svc_instance.fetch_baoquan_token.return_value = {
            "success": True,
            "token": "bad_format_token",
        }
        mock_module = MagicMock()
        mock_module.is_available.return_value = True
        mock_module.CourtZxfwHttpLoginService.return_value = mock_svc_instance

        mock_loop = MagicMock()
        mock_loop.run_in_executor = AsyncMock(side_effect=lambda executor, fn: fn())

        with (
            patch.dict("sys.modules", {
                "apps.automation.services.scraper.sites.court_zxfw_login_private": mock_module,
            }),
            patch("asyncio.get_running_loop", return_value=mock_loop),
        ):
            result = await svc._try_http_baoquan_token("account", "password")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_import_error(self) -> None:
        """插件模块不存在时返回 None。"""
        svc = BaoquanTokenService()

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name == "apps.automation.services.scraper.sites.court_zxfw_login_private":
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = await svc._try_http_baoquan_token("account", "password")

        assert result is None
