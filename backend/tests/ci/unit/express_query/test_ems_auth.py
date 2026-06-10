"""EMS auth handler tests with mocked Playwright."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.express_query.services.browser_query.ems_auth_handler import (
    EMS_AGREEMENT_ACCEPT_BUTTON_XPATH,
    EMS_AGREEMENT_LAST_CLAUSE_XPATH,
    EMS_AGREEMENT_MODAL_XPATH,
    EMS_LOGIN_AGREE_CHECKBOX_XPATH,
    ems_click_login_button,
    ems_handle_agreement_and_wait,
    is_ems_dialog_visible,
    is_ems_login_window,
    wait_for_ems_login,
)


def _make_page(**kwargs):
    """Create a mock Playwright page with sync locator() and async methods."""
    page = MagicMock()
    page.url = kwargs.get("url", "https://ems.com/home")
    return page


class TestIsEmsDialogVisible:
    def test_dialog_visible(self):
        page = _make_page()
        dialog = MagicMock()
        dialog.count = AsyncMock(return_value=1)
        dialog.first = MagicMock()
        dialog.first.is_visible = AsyncMock(return_value=True)
        page.locator.return_value = dialog
        result = asyncio.run(is_ems_dialog_visible(page))
        assert result is True

    def test_dialog_not_visible(self):
        page = _make_page()
        locator = MagicMock()
        locator.count = AsyncMock(return_value=0)
        page.locator.return_value = locator
        result = asyncio.run(is_ems_dialog_visible(page))
        assert result is False


class TestEmsClickLoginButton:
    def test_click_success(self):
        page = _make_page()
        locator = MagicMock()
        locator.count = AsyncMock(return_value=1)
        target = MagicMock()
        target.is_visible = AsyncMock(return_value=True)
        target.click = AsyncMock(return_value=True)
        locator.nth.return_value = target
        page.locator.return_value = locator
        result = asyncio.run(ems_click_login_button(page))
        assert result is True

    def test_click_not_found(self):
        page = _make_page()
        locator = MagicMock()
        locator.count = AsyncMock(return_value=0)
        page.locator.return_value = locator
        page.evaluate = AsyncMock(return_value=False)
        result = asyncio.run(ems_click_login_button(page))
        assert result is False


class TestIsEmsLoginWindow:
    def test_login_url(self):
        page = _make_page(url="https://ems.com/login")
        assert asyncio.run(is_ems_login_window(page, "")) is True

    def test_scan_login_text(self):
        page = _make_page(url="https://ems.com/home")
        assert asyncio.run(is_ems_login_window(page, "请使用微信扫码登录")) is True

    def test_normal_page(self):
        page = _make_page(url="https://ems.com/query")
        assert asyncio.run(is_ems_login_window(page, "查询快递")) is False


class TestConstants:
    def test_xpath_constants_exist(self):
        assert EMS_LOGIN_AGREE_CHECKBOX_XPATH
        assert EMS_AGREEMENT_MODAL_XPATH
        assert EMS_AGREEMENT_LAST_CLAUSE_XPATH
        assert EMS_AGREEMENT_ACCEPT_BUTTON_XPATH
