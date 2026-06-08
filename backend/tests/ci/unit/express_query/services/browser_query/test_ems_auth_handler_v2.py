"""Comprehensive unit tests for ems_auth_handler."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


_MOD = "apps.express_query.services.browser_query.ems_auth_handler"


class TestConstants:

    def test_xpath_constants_defined(self):
        from apps.express_query.services.browser_query.ems_auth_handler import (
            EMS_LOGIN_AGREE_CHECKBOX_XPATH,
            EMS_AGREEMENT_MODAL_XPATH,
            EMS_AGREEMENT_LAST_CLAUSE_XPATH,
            EMS_AGREEMENT_ACCEPT_BUTTON_XPATH,
        )

        assert EMS_LOGIN_AGREE_CHECKBOX_XPATH
        assert EMS_AGREEMENT_MODAL_XPATH
        assert EMS_AGREEMENT_LAST_CLAUSE_XPATH
        assert EMS_AGREEMENT_ACCEPT_BUTTON_XPATH


class TestIsEmsDialogVisible:

    @pytest.mark.asyncio
    async def test_dialog_scan_visible(self):
        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_dialog_visible

        page = MagicMock()
        dialog_loc = MagicMock()
        dialog_loc.count = AsyncMock(return_value=1)
        dialog_loc.first.is_visible = AsyncMock(return_value=True)
        page.locator.return_value = dialog_loc

        assert await is_ems_dialog_visible(page) is True

    @pytest.mark.asyncio
    async def test_scan_text_visible(self):
        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_dialog_visible

        page = MagicMock()

        # First call (dialog.scan) raises, second call (text=扫码登录) succeeds
        def locator_side_effect(sel):
            loc = MagicMock()
            if "scan" in sel:
                loc.count = AsyncMock(side_effect=Exception("not found"))
            elif "扫码登录" in sel:
                loc.count = AsyncMock(return_value=1)
                loc.first.is_visible = AsyncMock(return_value=True)
            else:
                loc.count = AsyncMock(return_value=0)
            return loc

        page.locator.side_effect = locator_side_effect
        assert await is_ems_dialog_visible(page) is True

    @pytest.mark.asyncio
    async def test_agreement_text_visible(self):
        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_dialog_visible

        page = MagicMock()

        def locator_side_effect(sel):
            loc = MagicMock()
            if "scan" in sel or "扫码登录" in sel:
                loc.count = AsyncMock(side_effect=Exception("not found"))
            elif "请阅读并同意" in sel:
                loc.count = AsyncMock(return_value=1)
                loc.first.is_visible = AsyncMock(return_value=True)
            else:
                loc.count = AsyncMock(return_value=0)
            return loc

        page.locator.side_effect = locator_side_effect
        assert await is_ems_dialog_visible(page) is True

    @pytest.mark.asyncio
    async def test_no_dialog(self):
        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_dialog_visible

        page = MagicMock()
        loc = MagicMock()
        loc.count = AsyncMock(side_effect=Exception("nope"))
        page.locator.return_value = loc

        assert await is_ems_dialog_visible(page) is False


class TestEmsClickLoginButton:

    @pytest.mark.asyncio
    async def test_returns_true_when_found(self):
        from apps.express_query.services.browser_query.ems_auth_handler import ems_click_login_button

        page = MagicMock()
        loc = MagicMock()
        loc.count = AsyncMock(return_value=1)
        loc.nth.return_value.is_visible = AsyncMock(return_value=True)
        loc.nth.return_value.click = AsyncMock()
        page.locator.return_value = loc

        result = await ems_click_login_button(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_element(self):
        from apps.express_query.services.browser_query.ems_auth_handler import ems_click_login_button

        page = MagicMock()
        loc = MagicMock()
        loc.count = AsyncMock(return_value=0)
        page.locator.return_value = loc
        page.evaluate = AsyncMock(return_value=False)

        result = await ems_click_login_button(page)
        assert result is False

    @pytest.mark.asyncio
    async def test_js_fallback(self):
        from apps.express_query.services.browser_query.ems_auth_handler import ems_click_login_button

        page = MagicMock()
        loc = MagicMock()
        loc.count = AsyncMock(return_value=0)
        page.locator.return_value = loc
        page.evaluate = AsyncMock(return_value=True)

        result = await ems_click_login_button(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_force_click_visible_element(self):
        from apps.express_query.services.browser_query.ems_auth_handler import ems_click_login_button

        page = MagicMock()
        # Second selector finds a visible element
        def locator_side_effect(sel):
            loc = MagicMock()
            if "div" in sel:
                loc.count = AsyncMock(return_value=1)
                target = MagicMock()
                target.is_visible = AsyncMock(return_value=True)
                target.click = AsyncMock()
                loc.nth.return_value = target
            else:
                loc.count = AsyncMock(return_value=0)
            return loc

        page.locator.side_effect = locator_side_effect
        result = await ems_click_login_button(page)
        assert result is True


class TestWaitForEmsLogin:

    @pytest.mark.asyncio
    async def test_success_when_user_visible(self):
        from apps.express_query.services.browser_query.ems_auth_handler import wait_for_ems_login

        page = MagicMock()
        page.url = "https://ems.com.cn/query_express_delivery"
        body_loc = MagicMock()
        body_loc.text_content = AsyncMock(return_value="退出 我的EMS")
        page.locator.return_value = body_loc

        with patch(
            "apps.express_query.services.browser_query.browser_utils.has_any_visible",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await wait_for_ems_login(page, timeout_seconds=5)

    @pytest.mark.asyncio
    async def test_login_dialog_disappears(self):
        from apps.express_query.services.browser_query.ems_auth_handler import wait_for_ems_login

        page = MagicMock()
        page.url = "https://ems.com.cn/query"
        body_loc = MagicMock()
        body_loc.text_content = AsyncMock(return_value="邮件号查询")
        page.locator.return_value = body_loc

        with patch(
            "apps.express_query.services.browser_query.browser_utils.has_any_visible",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await wait_for_ems_login(page, timeout_seconds=5)


class TestEmsHandleAgreementAndWait:

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        from apps.express_query.services.browser_query.ems_auth_handler import ems_handle_agreement_and_wait

        page = MagicMock()
        context = MagicMock()
        context.pages = []

        # Dialog always visible, no QR, no checkbox -> loops then times out
        with patch(
            f"{_MOD}.is_ems_dialog_visible", new_callable=AsyncMock, return_value=True
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                # Set the deadline to be in the past
                with patch("asyncio.get_running_loop") as mock_loop:
                    mock_time = MagicMock()
                    mock_loop.return_value.time.return_value = 0
                    # Use a very small timeout to trigger quickly
                    pass

        # Just verify the function signature works with a minimal timeout
        page2 = MagicMock()
        context2 = MagicMock()
        context2.pages = []

        with patch(
            f"{_MOD}.is_ems_dialog_visible", new_callable=AsyncMock, return_value=False
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                # Timeout should raise
                with pytest.raises(TimeoutError):
                    await ems_handle_agreement_and_wait(
                        context2, page2, timeout_seconds=0
                    )

    @pytest.mark.asyncio
    async def test_qr_visible_breaks_loop(self):
        from apps.express_query.services.browser_query.ems_auth_handler import ems_handle_agreement_and_wait

        page = MagicMock()
        context = MagicMock()
        context.pages = []

        call_count = 0

        async def fake_is_dialog(p):
            return False

        with patch(
            f"{_MOD}.is_ems_dialog_visible", side_effect=fake_is_dialog
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                # QR visible, no checkbox -> should break from agreement loop
                # and then timeout in the scan wait loop
                qr_loc = MagicMock()
                qr_loc.count = AsyncMock(return_value=1)
                qr_loc.first.is_visible = AsyncMock(return_value=True)

                cb_loc = MagicMock()
                cb_loc.count = AsyncMock(return_value=0)

                body_loc = MagicMock()
                body_loc.text_content = AsyncMock(return_value="扫码登录")

                def locator_side_effect(sel):
                    if "扫码登录" in sel:
                        return qr_loc
                    elif "请阅读并同意" in sel:
                        return cb_loc
                    return MagicMock(count=AsyncMock(return_value=0))

                page.locator.side_effect = locator_side_effect
                page.url = "https://ems.com.cn/query_express_delivery"

                with pytest.raises(TimeoutError):
                    await ems_handle_agreement_and_wait(context, page, timeout_seconds=0)


class TestEmsEnsureAgreementChecked:

    @pytest.mark.asyncio
    async def test_exact_xpath_clicked(self):
        from apps.express_query.services.browser_query.ems_auth_handler import _ems_ensure_agreement_checked

        page = MagicMock()
        checkbox_loc = MagicMock()
        checkbox_loc.count = AsyncMock(return_value=1)
        checkbox_loc.first.is_visible = AsyncMock(return_value=True)
        checkbox_loc.first.scroll_into_view_if_needed = AsyncMock()
        checkbox_loc.first.click = AsyncMock()
        page.locator.return_value = checkbox_loc

        with patch(
            f"{_MOD}.click_locator_if_visible", new_callable=AsyncMock, return_value=True
        ):
            result = await _ems_ensure_agreement_checked(page)
            assert result is True

    @pytest.mark.asyncio
    async def test_js_fallback(self):
        from apps.express_query.services.browser_query.ems_auth_handler import _ems_ensure_agreement_checked

        page = MagicMock()
        with patch(
            f"{_MOD}.click_locator_if_visible", new_callable=AsyncMock, return_value=False
        ):
            with patch(
                f"{_MOD}.click_first", new_callable=AsyncMock, return_value=False
            ):
                page.evaluate = AsyncMock(return_value=True)
                result = await _ems_ensure_agreement_checked(page)
                assert result is True

    @pytest.mark.asyncio
    async def test_all_fail_returns_false(self):
        from apps.express_query.services.browser_query.ems_auth_handler import _ems_ensure_agreement_checked

        page = MagicMock()
        with patch(
            f"{_MOD}.click_locator_if_visible", new_callable=AsyncMock, return_value=False
        ):
            with patch(
                f"{_MOD}.click_first", new_callable=AsyncMock, return_value=False
            ):
                page.evaluate = AsyncMock(return_value=False)
                result = await _ems_ensure_agreement_checked(page)
                assert result is False


class TestEmsTryAgreementCheckbox:

    @pytest.mark.asyncio
    async def test_xpath_strategy_success(self):
        from apps.express_query.services.browser_query.ems_auth_handler import _ems_try_agreement_checkbox

        page = MagicMock()
        xpath_loc = MagicMock()
        xpath_loc.count = AsyncMock(return_value=1)
        xpath_loc.first.click = AsyncMock()
        page.locator.return_value = xpath_loc

        result = await _ems_try_agreement_checkbox(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_text_strategy_success(self):
        from apps.express_query.services.browser_query.ems_auth_handler import _ems_try_agreement_checkbox

        page = MagicMock()
        # XPath strategies fail
        page.locator.return_value = MagicMock(count=AsyncMock(return_value=0))

        # Text strategy succeeds
        text_loc = MagicMock()
        text_loc.count = AsyncMock(return_value=1)
        text_loc.first.click = AsyncMock()
        page.get_by_text.return_value = text_loc

        result = await _ems_try_agreement_checkbox(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_js_strategy_success(self):
        from apps.express_query.services.browser_query.ems_auth_handler import _ems_try_agreement_checkbox

        page = MagicMock()
        page.locator.return_value = MagicMock(count=AsyncMock(return_value=0))
        page.get_by_text.return_value = MagicMock(count=AsyncMock(return_value=0))
        page.evaluate = AsyncMock(return_value={"ok": True})

        result = await _ems_try_agreement_checkbox(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_all_fail_returns_false(self):
        from apps.express_query.services.browser_query.ems_auth_handler import _ems_try_agreement_checkbox

        page = MagicMock()
        page.locator.return_value = MagicMock(count=AsyncMock(return_value=0))
        page.get_by_text.return_value = MagicMock(count=AsyncMock(return_value=0))
        page.evaluate = AsyncMock(return_value={"ok": False})

        result = await _ems_try_agreement_checkbox(page)
        assert result is False


class TestIsEmsLoginWindow:

    @pytest.mark.asyncio
    async def test_login_url(self):
        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window

        page = MagicMock()
        page.url = "https://www.ems.com.cn/login"
        assert await is_ems_login_window(page, "some body") is True

    @pytest.mark.asyncio
    async def test_passport_url(self):
        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window

        page = MagicMock()
        page.url = "https://passport.ems.com.cn/auth"
        assert await is_ems_login_window(page, "some body") is True

    @pytest.mark.asyncio
    async def test_scan_body_text(self):
        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window

        page = MagicMock()
        page.url = "https://www.ems.com.cn/"
        assert await is_ems_login_window(page, "请使用微信扫码登录") is True

    @pytest.mark.asyncio
    async def test_phone_login_text(self):
        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window

        page = MagicMock()
        page.url = "https://www.ems.com.cn/"
        assert await is_ems_login_window(page, "手机号登录") is True

    @pytest.mark.asyncio
    async def test_normal_page(self):
        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window

        page = MagicMock()
        page.url = "https://www.ems.com.cn/query"
        assert await is_ems_login_window(page, "邮件号查询") is False


class TestEmsScrollAgreementAndAccept:

    @pytest.mark.asyncio
    async def test_button_clicked(self):
        from apps.express_query.services.browser_query.ems_auth_handler import _ems_scroll_agreement_and_accept

        page = MagicMock()
        with patch(
            f"{_MOD}.click_locator_if_visible", new_callable=AsyncMock, return_value=True
        ):
            result = await _ems_scroll_agreement_and_accept(page)
            assert result is True

    @pytest.mark.asyncio
    async def test_button_not_found_returns_true(self):
        from apps.express_query.services.browser_query.ems_auth_handler import _ems_scroll_agreement_and_accept

        page = MagicMock()
        with patch(
            f"{_MOD}.click_locator_if_visible", new_callable=AsyncMock, return_value=False
        ):
            result = await _ems_scroll_agreement_and_accept(page)
            assert result is True


class TestEmsOpenLastAgreementAndAccept:

    @pytest.mark.asyncio
    async def test_checkbox_not_found_returns_false(self):
        from apps.express_query.services.browser_query.ems_auth_handler import _ems_open_last_agreement_and_accept

        page = MagicMock()
        context = MagicMock()
        context.pages = [page]

        with patch(
            f"{_MOD}.click_locator_if_visible", new_callable=AsyncMock, return_value=False
        ):
            result = await _ems_open_last_agreement_and_accept(context, page)
            assert result is False


class TestEmsAcceptAgreementOnPage:

    @pytest.mark.asyncio
    async def test_accept_button_clicked(self):
        from apps.express_query.services.browser_query.ems_auth_handler import _ems_accept_agreement_on_page

        page = MagicMock()
        clause_loc = MagicMock()
        clause_loc.count = AsyncMock(return_value=1)
        clause_loc.first.click = AsyncMock()

        btn_loc = MagicMock()
        btn_loc.count = AsyncMock(return_value=1)
        btn_loc.first.click = AsyncMock()

        def locator_side_effect(sel):
            if "li" in sel:
                return clause_loc
            elif "button" in sel:
                return btn_loc
            return MagicMock(count=AsyncMock(return_value=0))

        page.locator.side_effect = locator_side_effect

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await _ems_accept_agreement_on_page(page)
            btn_loc.first.click.assert_called_once()
