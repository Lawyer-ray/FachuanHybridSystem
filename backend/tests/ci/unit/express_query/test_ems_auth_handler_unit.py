"""ems_auth_handler.py 单元测试。"""

from __future__ import annotations

import pytest


class TestIsEmsLoginWindow:

    @pytest.mark.asyncio
    async def test_login_url(self):
        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window
        page = type("Page", (), {
            "url": property(lambda self: "https://www.ems.com.cn/login"),
        })()
        assert await is_ems_login_window(page, "some body") is True

    @pytest.mark.asyncio
    async def test_scan_body_text(self):
        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window
        page = type("Page", (), {
            "url": property(lambda self: "https://www.ems.com.cn/"),
        })()
        assert await is_ems_login_window(page, "请使用微信扫码登录") is True

    @pytest.mark.asyncio
    async def test_normal_page(self):
        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window
        page = type("Page", (), {
            "url": property(lambda self: "https://www.ems.com.cn/query"),
        })()
        assert await is_ems_login_window(page, "邮件号查询") is False


class TestEmsConstants:

    def test_xpath_constants_defined(self):
        from apps.express_query.services.browser_query.ems_auth_handler import (
            EMS_LOGIN_AGREE_CHECKBOX_XPATH,
            EMS_AGREEMENT_MODAL_XPATH,
            EMS_AGREEMENT_ACCEPT_BUTTON_XPATH,
        )
        assert EMS_LOGIN_AGREE_CHECKBOX_XPATH
        assert EMS_AGREEMENT_MODAL_XPATH
        assert EMS_AGREEMENT_ACCEPT_BUTTON_XPATH


class TestEmsClickLoginButton:

    @pytest.mark.asyncio
    async def test_returns_false_when_no_element(self):
        from apps.express_query.services.browser_query.ems_auth_handler import ems_click_login_button
        page = type("MockPage", (), {
            "locator": lambda self, sel: type("Loc", (), {
                "count": lambda self: 0,
                "nth": lambda self, i: None,
            })(),
            "evaluate": lambda self, js: False,
        })()
        result = await ems_click_login_button(page)
        assert result is False
