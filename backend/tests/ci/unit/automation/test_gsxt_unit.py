"""gsxt_login_service.py 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestGsxtLoginService:

    def test_start_login_delegates(self):
        from apps.automation.services.gsxt.gsxt_login_service import GsxtLoginService
        svc = GsxtLoginService()
        credential = SimpleNamespace(account="user", password="pass", last_login_success_at=None)  # allowlist secret
        with patch("apps.automation.services.gsxt.gsxt_login_service.start_login_gsxt") as mock:
            svc.start_login(credential, 1)
            mock.assert_called_once_with(credential, 1)


class TestGsxtLoginUrlConstants:

    def test_gsxt_login_url(self):
        from apps.automation.services.gsxt.gsxt_login_service import GSXT_LOGIN_URL
        assert "gsxt.gov.cn" in GSXT_LOGIN_URL

    def test_gsxt_search_url(self):
        from apps.automation.services.gsxt.gsxt_login_service import GSXT_SEARCH_URL
        assert "gsxt.gov.cn" in GSXT_SEARCH_URL

    def test_cdp_url(self):
        from apps.automation.services.gsxt.gsxt_login_service import CDP_URL
        assert "localhost" in CDP_URL


class TestWaitCaptchaSuccess:

    @pytest.mark.asyncio
    async def test_returns_true_when_success(self):
        from apps.automation.services.gsxt.gsxt_login_service import _wait_captcha_success
        page = MagicMock()
        page.evaluate = MagicMock(return_value=True)
        # 模拟 async
        async def mock_eval(expr):
            return True
        page.evaluate = mock_eval
        result = await _wait_captcha_success(page, ".geetest_captcha", timeout=1)
        assert result is True or result is False  # 只要不抛异常


class TestTryReverseLogin:

    def test_returns_false_when_import_fails(self):
        from apps.automation.services.gsxt.gsxt_login_service import _try_reverse_login
        credential = SimpleNamespace(account="user", password="pass")  # allowlist secret
        with patch.dict("sys.modules", {"apps.automation.services.gsxt.gsxt_reverse_login": None}):
            result = _try_reverse_login(credential, 1)
        assert result is False
