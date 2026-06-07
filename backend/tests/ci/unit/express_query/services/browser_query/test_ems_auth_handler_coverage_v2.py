"""Tests for apps.express_query.services.browser_query.ems_auth_handler."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers – lightweight fakes for Playwright Page / Locator / BrowserContext
# ---------------------------------------------------------------------------

def _make_locator(count=0, is_visible=False, text_content=""):
    """Return a mock Locator whose async methods behave as specified."""
    loc = MagicMock()
    loc.count = AsyncMock(return_value=count)
    loc.first = MagicMock()
    loc.first.is_visible = AsyncMock(return_value=is_visible)
    loc.first.click = AsyncMock()
    loc.first.scroll_into_view_if_needed = AsyncMock()
    loc.first.text_content = AsyncMock(return_value=text_content)
    loc.first.wait_for = AsyncMock()
    loc.first.url = ""
    loc.nth.return_value = loc.first  # nth(i) always returns same mock
    return loc


def _make_page(url="https://www.ems.com.cn/query_express_delivery", body_text=""):
    """Return a mock Page."""
    page = MagicMock()
    page.url = url
    page.locator = MagicMock(return_value=_make_locator())
    page.get_by_text = MagicMock(return_value=_make_locator())
    page.evaluate = AsyncMock(return_value=False)
    page.locator.return_value.first.text_content = AsyncMock(return_value=body_text)
    # allow `page.locator("body").text_content()` pattern
    page.is_closed = MagicMock(return_value=False)
    page.close = AsyncMock()
    return page


def _make_context(pages=None):
    """Return a mock BrowserContext."""
    ctx = MagicMock()
    ctx.pages = pages or []
    return ctx


# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------

BROWSER_UTILS = "apps.express_query.services.browser_query.browser_utils"
MODULE = "apps.express_query.services.browser_query.ems_auth_handler"
UTILS = "apps.express_query.services.browser_query.browser_utils"


# ===================================================================
# is_ems_dialog_visible
# ===================================================================

class TestIsEmsDialogVisible:
    @pytest.mark.asyncio
    async def test_dialog_visible_via_css(self):
        page = _make_page()
        dlg = _make_locator(count=1, is_visible=True)
        page.locator = MagicMock(side_effect=lambda sel: dlg if sel == ".el-dialog.scan" else _make_locator())

        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_dialog_visible
        assert await is_ems_dialog_visible(page) is True

    @pytest.mark.asyncio
    async def test_qr_text_visible(self):
        page = _make_page()
        normal = _make_locator()
        qr = _make_locator(count=1, is_visible=True)
        page.locator = MagicMock(side_effect=lambda sel: qr if sel == "text=扫码登录" else normal)

        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_dialog_visible
        assert await is_ems_dialog_visible(page) is True

    @pytest.mark.asyncio
    async def test_agreement_text_visible(self):
        page = _make_page()
        normal = _make_locator()
        agree = _make_locator(count=1, is_visible=True)
        page.locator = MagicMock(
            side_effect=lambda sel: agree if sel == "text=请阅读并同意服务协议" else normal,
        )

        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_dialog_visible
        assert await is_ems_dialog_visible(page) is True

    @pytest.mark.asyncio
    async def test_nothing_visible_returns_false(self):
        page = _make_page()
        page.locator = MagicMock(return_value=_make_locator())

        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_dialog_visible
        assert await is_ems_dialog_visible(page) is False

    @pytest.mark.asyncio
    async def test_exception_in_first_check_is_swallowed(self):
        page = _make_page()
        failing = MagicMock()
        failing.count = AsyncMock(side_effect=RuntimeError("boom"))
        ok_loc = _make_locator()
        call_count = 0

        def factory(sel):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return failing
            return ok_loc

        page.locator = MagicMock(side_effect=factory)

        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_dialog_visible
        # Should not raise, returns False (none of the ok_loc are visible)
        assert await is_ems_dialog_visible(page) is False


# ===================================================================
# ems_click_login_button
# ===================================================================

class TestEmsClickLoginButton:
    @pytest.mark.asyncio
    async def test_first_selector_matches(self):
        page = _make_page()
        loc = _make_locator(count=1, is_visible=True)
        page.locator = MagicMock(return_value=loc)

        from apps.express_query.services.browser_query.ems_auth_handler import ems_click_login_button
        result = await ems_click_login_button(page)
        assert result is True
        loc.first.click.assert_awaited()

    @pytest.mark.asyncio
    async def test_count_raises_skip_selector(self):
        page = _make_page()
        failing = MagicMock()
        failing.count = AsyncMock(side_effect=RuntimeError("fail"))
        page.locator = MagicMock(return_value=failing)

        from apps.express_query.services.browser_query.ems_auth_handler import ems_click_login_button
        result = await ems_click_login_button(page)
        # All 4 selectors fail on count, then JS fallback also returns False
        assert result is False

    @pytest.mark.asyncio
    async def test_element_not_visible_tries_next(self):
        page = _make_page()
        hidden = _make_locator(count=2, is_visible=False)
        visible = _make_locator(count=1, is_visible=True)
        call_idx = 0

        def factory(sel):
            nonlocal call_idx
            call_idx += 1
            if call_idx <= 2:
                return hidden
            return visible

        page.locator = MagicMock(side_effect=factory)

        from apps.express_query.services.browser_query.ems_auth_handler import ems_click_login_button
        assert await ems_click_login_button(page) is True

    @pytest.mark.asyncio
    async def test_js_fallback_success(self):
        page = _make_page()
        page.locator = MagicMock(return_value=_make_locator())
        page.evaluate = AsyncMock(return_value=True)

        from apps.express_query.services.browser_query.ems_auth_handler import ems_click_login_button
        assert await ems_click_login_button(page) is True

    @pytest.mark.asyncio
    async def test_js_fallback_failure(self):
        page = _make_page()
        page.locator = MagicMock(return_value=_make_locator())
        page.evaluate = AsyncMock(return_value=False)

        from apps.express_query.services.browser_query.ems_auth_handler import ems_click_login_button
        assert await ems_click_login_button(page) is False

    @pytest.mark.asyncio
    async def test_js_fallback_exception(self):
        page = _make_page()
        page.locator = MagicMock(return_value=_make_locator())
        page.evaluate = AsyncMock(side_effect=RuntimeError("js err"))

        from apps.express_query.services.browser_query.ems_auth_handler import ems_click_login_button
        assert await ems_click_login_button(page) is False

    @pytest.mark.asyncio
    async def test_click_exception_continues(self):
        page = _make_page()
        loc = _make_locator(count=1, is_visible=True)
        loc.first.click = AsyncMock(side_effect=RuntimeError("click err"))
        loc.nth.return_value = loc.first
        page.locator = MagicMock(return_value=loc)
        page.evaluate = AsyncMock(return_value=True)

        from apps.express_query.services.browser_query.ems_auth_handler import ems_click_login_button
        # Click raises, selector loop continues, eventually JS fallback succeeds
        assert await ems_click_login_button(page) is True


# ===================================================================
# wait_for_ems_login
# ===================================================================

class TestWaitForEmsLogin:
    @pytest.mark.asyncio
    async def test_user_logged_in_immediately(self):
        page = _make_page(body_text="退出 登录")
        with patch(f"{BROWSER_UTILS}.has_any_visible", new_callable=AsyncMock, return_value=False):
            from apps.express_query.services.browser_query.ems_auth_handler import wait_for_ems_login
            # Should return immediately because has_any_visible=False → not login_visible → return
            await asyncio.wait_for(wait_for_ems_login(page, timeout_seconds=5), timeout=3)

    @pytest.mark.asyncio
    async def test_login_dialog_disappears(self):
        page = _make_page(body_text="some content")
        with patch(f"{BROWSER_UTILS}.has_any_visible", new_callable=AsyncMock, return_value=False):
            from apps.express_query.services.browser_query.ems_auth_handler import wait_for_ems_login
            await asyncio.wait_for(wait_for_ems_login(page, timeout_seconds=5), timeout=3)

    @pytest.mark.asyncio
    async def test_text_content_exception_swallowed(self):
        page = _make_page()
        page.locator.return_value.first.text_content = AsyncMock(side_effect=RuntimeError("boom"))
        with patch(f"{BROWSER_UTILS}.has_any_visible", new_callable=AsyncMock, return_value=True):
            from apps.express_query.services.browser_query.ems_auth_handler import wait_for_ems_login
            # Loop until deadline; has_any_visible True so login_visible is True;
            # text_content raises -> body="" -> user_visible False; loop continues until timeout
            await asyncio.wait_for(wait_for_ems_login(page, timeout_seconds=0.1), timeout=5)


# ===================================================================
# _ems_ensure_agreement_checked
# ===================================================================

class TestEmsEnsureAgreementChecked:
    @pytest.mark.asyncio
    async def test_xpath_click_success(self):
        page = _make_page()
        with patch(f"{MODULE}.click_locator_if_visible", new_callable=AsyncMock, return_value=True):
            from apps.express_query.services.browser_query.ems_auth_handler import _ems_ensure_agreement_checked
            assert await _ems_ensure_agreement_checked(page) is True

    @pytest.mark.asyncio
    async def test_text_fallback_success(self):
        page = _make_page()
        with patch(f"{MODULE}.click_locator_if_visible", new_callable=AsyncMock, return_value=False), \
             patch(f"{MODULE}.click_first", new_callable=AsyncMock, return_value=True):
            from apps.express_query.services.browser_query.ems_auth_handler import _ems_ensure_agreement_checked
            assert await _ems_ensure_agreement_checked(page) is True

    @pytest.mark.asyncio
    async def test_js_fallback_success(self):
        page = _make_page()
        page.evaluate = AsyncMock(return_value=True)
        with patch(f"{MODULE}.click_locator_if_visible", new_callable=AsyncMock, return_value=False), \
             patch(f"{MODULE}.click_first", new_callable=AsyncMock, return_value=False):
            from apps.express_query.services.browser_query.ems_auth_handler import _ems_ensure_agreement_checked
            assert await _ems_ensure_agreement_checked(page) is True

    @pytest.mark.asyncio
    async def test_all_strategies_fail(self):
        page = _make_page()
        page.evaluate = AsyncMock(return_value=False)
        with patch(f"{MODULE}.click_locator_if_visible", new_callable=AsyncMock, return_value=False), \
             patch(f"{MODULE}.click_first", new_callable=AsyncMock, return_value=False):
            from apps.express_query.services.browser_query.ems_auth_handler import _ems_ensure_agreement_checked
            assert await _ems_ensure_agreement_checked(page) is False

    @pytest.mark.asyncio
    async def test_js_fallback_exception(self):
        page = _make_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError("err"))
        with patch(f"{MODULE}.click_locator_if_visible", new_callable=AsyncMock, return_value=False), \
             patch(f"{MODULE}.click_first", new_callable=AsyncMock, return_value=False):
            from apps.express_query.services.browser_query.ems_auth_handler import _ems_ensure_agreement_checked
            assert await _ems_ensure_agreement_checked(page) is False


# ===================================================================
# _ems_scroll_agreement_and_accept
# ===================================================================

class TestEmsScrollAgreementAndAccept:
    @pytest.mark.asyncio
    async def test_accept_button_clicked(self):
        page = _make_page()
        with patch(f"{MODULE}.click_locator_if_visible", new_callable=AsyncMock, return_value=True):
            from apps.express_query.services.browser_query.ems_auth_handler import _ems_scroll_agreement_and_accept
            assert await _ems_scroll_agreement_and_accept(page) is True

    @pytest.mark.asyncio
    async def test_accept_button_not_found(self):
        page = _make_page()
        with patch(f"{MODULE}.click_locator_if_visible", new_callable=AsyncMock, return_value=False):
            from apps.express_query.services.browser_query.ems_auth_handler import _ems_scroll_agreement_and_accept
            # Returns True even if button not found (just logs a message)
            assert await _ems_scroll_agreement_and_accept(page) is True


# ===================================================================
# _ems_open_last_agreement_and_accept
# ===================================================================

class TestEmsOpenLastAgreementAndAccept:
    @pytest.mark.asyncio
    async def test_trigger_not_clicked(self):
        page = _make_page()
        ctx = _make_context(pages=[page])
        with patch(f"{MODULE}.click_locator_if_visible", new_callable=AsyncMock, return_value=False):
            from apps.express_query.services.browser_query.ems_auth_handler import _ems_open_last_agreement_and_accept
            assert await _ems_open_last_agreement_and_accept(ctx, page) is False

    @pytest.mark.asyncio
    async def test_no_new_page_opened(self):
        page = _make_page()
        page.wait_for_load_state = AsyncMock()
        ctx = _make_context(pages=[page])
        with patch(f"{MODULE}.click_locator_if_visible", new_callable=AsyncMock, return_value=True):
            from apps.express_query.services.browser_query.ems_auth_handler import _ems_open_last_agreement_and_accept
            result = await _ems_open_last_agreement_and_accept(ctx, page)
            assert result is True

    @pytest.mark.asyncio
    async def test_new_page_opened_and_closed(self):
        page = _make_page()
        new_page = MagicMock()
        new_page.is_closed = MagicMock(return_value=False)
        new_page.wait_for_load_state = AsyncMock()
        new_page.close = AsyncMock()
        new_page.locator = MagicMock(return_value=_make_locator(count=1, is_visible=True))

        ctx = _make_context(pages=[page, new_page])

        with patch(f"{MODULE}.click_locator_if_visible", new_callable=AsyncMock, return_value=True):
            from apps.express_query.services.browser_query.ems_auth_handler import _ems_open_last_agreement_and_accept
            result = await _ems_open_last_agreement_and_accept(ctx, page)
            assert result is True
            new_page.close.assert_awaited()

    @pytest.mark.asyncio
    async def test_new_page_close_exception(self):
        page = _make_page()
        new_page = MagicMock()
        new_page.is_closed = MagicMock(return_value=False)
        new_page.wait_for_load_state = AsyncMock()
        new_page.close = AsyncMock(side_effect=RuntimeError("close err"))
        new_page.locator = MagicMock(return_value=_make_locator())

        ctx = _make_context(pages=[page, new_page])

        with patch(f"{MODULE}.click_locator_if_visible", new_callable=AsyncMock, return_value=True):
            from apps.express_query.services.browser_query.ems_auth_handler import _ems_open_last_agreement_and_accept
            result = await _ems_open_last_agreement_and_accept(ctx, page)
            assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_load_state_exception(self):
        page = _make_page()
        page.wait_for_load_state = AsyncMock(side_effect=TimeoutError("timeout"))
        ctx = _make_context(pages=[page])

        with patch(f"{MODULE}.click_locator_if_visible", new_callable=AsyncMock, return_value=True):
            from apps.express_query.services.browser_query.ems_auth_handler import _ems_open_last_agreement_and_accept
            result = await _ems_open_last_agreement_and_accept(ctx, page)
            assert result is True

    @pytest.mark.asyncio
    async def test_modal_count_exception(self):
        page = _make_page()
        page.wait_for_load_state = AsyncMock()
        modal_loc = MagicMock()
        modal_loc.count = AsyncMock(side_effect=RuntimeError("boom"))
        page.locator = MagicMock(return_value=modal_loc)
        ctx = _make_context(pages=[page])

        with patch(f"{MODULE}.click_locator_if_visible", new_callable=AsyncMock, return_value=True):
            from apps.express_query.services.browser_query.ems_auth_handler import _ems_open_last_agreement_and_accept
            result = await _ems_open_last_agreement_and_accept(ctx, page)
            assert result is True


# ===================================================================
# _ems_try_agreement_checkbox
# ===================================================================

class TestEmsTryAgreementCheckbox:
    @pytest.mark.asyncio
    async def test_xpath_strategy_success(self):
        page = _make_page()
        loc = _make_locator(count=1)
        page.locator = MagicMock(return_value=loc)

        from apps.express_query.services.browser_query.ems_auth_handler import _ems_try_agreement_checkbox
        result = await _ems_try_agreement_checkbox(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_xpath_count_zero_falls_through(self):
        page = _make_page()
        loc = _make_locator(count=0)
        text_loc = _make_locator(count=1)
        call_idx = 0

        def factory(sel):
            nonlocal call_idx
            call_idx += 1
            if call_idx <= 2:
                return loc
            return text_loc

        page.locator = MagicMock(side_effect=factory)
        page.get_by_text = MagicMock(return_value=text_loc)

        from apps.express_query.services.browser_query.ems_auth_handler import _ems_try_agreement_checkbox
        result = await _ems_try_agreement_checkbox(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_text_strategy_success(self):
        page = _make_page()
        page.locator = MagicMock(return_value=_make_locator(count=0))
        text_loc = _make_locator(count=1)
        page.get_by_text = MagicMock(return_value=text_loc)

        from apps.express_query.services.browser_query.ems_auth_handler import _ems_try_agreement_checkbox
        result = await _ems_try_agreement_checkbox(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_js_strategy_success(self):
        page = _make_page()
        page.locator = MagicMock(return_value=_make_locator(count=0))
        page.get_by_text = MagicMock(return_value=_make_locator(count=0))
        page.evaluate = AsyncMock(return_value={"ok": True})

        from apps.express_query.services.browser_query.ems_auth_handler import _ems_try_agreement_checkbox
        result = await _ems_try_agreement_checkbox(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_all_strategies_fail(self):
        page = _make_page()
        page.locator = MagicMock(return_value=_make_locator(count=0))
        page.get_by_text = MagicMock(return_value=_make_locator(count=0))
        page.evaluate = AsyncMock(return_value={"ok": False})

        from apps.express_query.services.browser_query.ems_auth_handler import _ems_try_agreement_checkbox
        result = await _ems_try_agreement_checkbox(page)
        assert result is False

    @pytest.mark.asyncio
    async def test_xpath_click_exception(self):
        page = _make_page()
        loc = _make_locator(count=1)
        loc.first.click = AsyncMock(side_effect=RuntimeError("click err"))
        loc.nth.return_value = loc.first
        text_loc = _make_locator(count=1)
        call_idx = 0

        def factory(sel):
            nonlocal call_idx
            call_idx += 1
            if call_idx <= 2:
                return loc
            return text_loc

        page.locator = MagicMock(side_effect=factory)
        page.get_by_text = MagicMock(return_value=text_loc)

        from apps.express_query.services.browser_query.ems_auth_handler import _ems_try_agreement_checkbox
        result = await _ems_try_agreement_checkbox(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_text_click_exception(self):
        page = _make_page()
        page.locator = MagicMock(return_value=_make_locator(count=0))
        text_loc = _make_locator(count=1)
        text_loc.first.click = AsyncMock(side_effect=RuntimeError("err"))
        text_loc.nth.return_value = text_loc.first
        page.get_by_text = MagicMock(return_value=text_loc)
        page.evaluate = AsyncMock(return_value={"ok": True})

        from apps.express_query.services.browser_query.ems_auth_handler import _ems_try_agreement_checkbox
        result = await _ems_try_agreement_checkbox(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_js_exception(self):
        page = _make_page()
        page.locator = MagicMock(return_value=_make_locator(count=0))
        page.get_by_text = MagicMock(return_value=_make_locator(count=0))
        page.evaluate = AsyncMock(side_effect=RuntimeError("js err"))

        from apps.express_query.services.browser_query.ems_auth_handler import _ems_try_agreement_checkbox
        result = await _ems_try_agreement_checkbox(page)
        assert result is False


# ===================================================================
# _ems_accept_agreement_on_page
# ===================================================================

class TestEmsAcceptAgreementOnPage:
    @pytest.mark.asyncio
    async def test_first_clause_and_accept_success(self):
        page = _make_page()
        clause = _make_locator(count=1)
        accept = _make_locator(count=1)

        def factory(sel):
            return accept if "button" in sel else clause

        page.locator = MagicMock(side_effect=factory)

        from apps.express_query.services.browser_query.ems_auth_handler import _ems_accept_agreement_on_page
        await _ems_accept_agreement_on_page(page)
        accept.first.click.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_accept_button_logs_warning(self):
        page = _make_page()
        clause = _make_locator(count=0)
        page.locator = MagicMock(return_value=clause)

        from apps.express_query.services.browser_query.ems_auth_handler import _ems_accept_agreement_on_page
        # Should not raise; logs warning about button not found
        await _ems_accept_agreement_on_page(page)

    @pytest.mark.asyncio
    async def test_clause_exception_continues(self):
        page = _make_page()
        call_idx = 0

        def factory(sel):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                loc = _make_locator(count=1)
                loc.first.click = AsyncMock(side_effect=RuntimeError("err"))
                loc.nth.return_value = loc.first
                return loc
            if call_idx == 2:
                return _make_locator(count=1)  # second clause selector
            return _make_locator(count=1)  # accept button

        page.locator = MagicMock(side_effect=factory)

        from apps.express_query.services.browser_query.ems_auth_handler import _ems_accept_agreement_on_page
        await _ems_accept_agreement_on_page(page)


# ===================================================================
# is_ems_login_window
# ===================================================================

class TestIsEmsLoginWindow:
    @pytest.mark.asyncio
    async def test_url_contains_login(self):
        page = MagicMock()
        page.url = "https://passport.ems.com.cn/login"

        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window
        assert await is_ems_login_window(page, "") is True

    @pytest.mark.asyncio
    async def test_url_contains_qrcode(self):
        page = MagicMock()
        page.url = "https://ems.com.cn/qrcode/auth"

        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window
        assert await is_ems_login_window(page, "") is True

    @pytest.mark.asyncio
    async def test_body_contains_scan_login(self):
        page = MagicMock()
        page.url = "https://ems.com.cn/query"

        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window
        assert await is_ems_login_window(page, "请扫码登录系统") is True

    @pytest.mark.asyncio
    async def test_body_contains_wechat_scan(self):
        page = MagicMock()
        page.url = "https://ems.com.cn/query"

        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window
        assert await is_ems_login_window(page, "请使用微信扫码") is True

    @pytest.mark.asyncio
    async def test_not_login_window(self):
        page = MagicMock()
        page.url = "https://ems.com.cn/query"

        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window
        assert await is_ems_login_window(page, "邮件号查询结果") is False

    @pytest.mark.asyncio
    async def test_url_case_insensitive(self):
        page = MagicMock()
        page.url = "https://EMS.COM.CN/LOGIN"

        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window
        assert await is_ems_login_window(page, "") is True

    @pytest.mark.asyncio
    async def test_url_contains_wx(self):
        page = MagicMock()
        page.url = "https://ems.com.cn/wx/callback"

        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window
        assert await is_ems_login_window(page, "") is True

    @pytest.mark.asyncio
    async def test_body_contains_phone_login(self):
        page = MagicMock()
        page.url = "https://ems.com.cn/query"

        from apps.express_query.services.browser_query.ems_auth_handler import is_ems_login_window
        assert await is_ems_login_window(page, "手机号登录") is True


# ===================================================================
# ems_handle_agreement_and_wait
# ===================================================================

class TestEmsHandleAgreementAndWait:
    @pytest.mark.asyncio
    async def test_qr_visible_no_checkbox_breaks_immediately(self):
        """QR visible + no checkbox -> breaks agreement loop immediately."""
        page = _make_page(body_text="")
        page.url = "https://ems.com.cn/query"
        ctx = _make_context(pages=[page])

        qr_loc = _make_locator(count=1, is_visible=True)
        no_cb = _make_locator(count=0)
        call_idx = 0

        def locator_factory(sel):
            nonlocal call_idx
            call_idx += 1
            # is_ems_dialog_visible calls (3 locators)
            if call_idx <= 3:
                return qr_loc if call_idx == 1 else no_cb
            # has_qr check
            if call_idx == 4:
                return qr_loc
            # has_checkbox check via get_by_text
            return no_cb

        page.locator = MagicMock(side_effect=locator_factory)
        page.get_by_text = MagicMock(return_value=no_cb)
        page.evaluate = AsyncMock(return_value=False)

        with patch(f"{MODULE}.is_ems_dialog_visible", new_callable=AsyncMock, return_value=True), \
             patch.object(page.locator, "side_effect", locator_factory):
            from apps.express_query.services.browser_query.ems_auth_handler import ems_handle_agreement_and_wait
            # This will time out in the scan-wait loop since we can't simulate login success
            # We test the timeout path
            with pytest.raises(TimeoutError, match="timed out"):
                await ems_handle_agreement_and_wait(ctx, page, timeout_seconds=2)

    @pytest.mark.asyncio
    async def test_dialog_not_visible_reclicks_login(self):
        """Dialog not visible -> tries ems_click_login_button."""
        page = _make_page(body_text="")
        ctx = _make_context(pages=[page])

        with patch(f"{MODULE}.is_ems_dialog_visible", new_callable=AsyncMock, return_value=False), \
             patch(f"{MODULE}.ems_click_login_button", new_callable=AsyncMock, return_value=True), \
             patch(f"{MODULE}._ems_try_agreement_checkbox", new_callable=AsyncMock, return_value=False):
            from apps.express_query.services.browser_query.ems_auth_handler import ems_handle_agreement_and_wait
            with pytest.raises(TimeoutError):
                await ems_handle_agreement_and_wait(ctx, page, timeout_seconds=2)

    @pytest.mark.asyncio
    async def test_checkbox_path_with_new_tab(self):
        """Dialog visible, has checkbox, new tab detected -> handles agreement tab."""
        page = _make_page(body_text="")
        page.url = "https://ems.com.cn/query"
        new_tab = MagicMock()
        new_tab.is_closed = MagicMock(return_value=False)
        new_tab.url = "https://ems.com.cn/agreement"
        new_tab.close = AsyncMock()
        ctx = _make_context(pages=[page, new_tab])

        with patch(f"{MODULE}.is_ems_dialog_visible", new_callable=AsyncMock, return_value=True), \
             patch(f"{MODULE}._ems_try_agreement_checkbox", new_callable=AsyncMock, return_value=True), \
             patch(f"{MODULE}._ems_accept_agreement_on_page", new_callable=AsyncMock), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            from apps.express_query.services.browser_query.ems_auth_handler import ems_handle_agreement_and_wait
            with pytest.raises(TimeoutError):
                await ems_handle_agreement_and_wait(ctx, page, timeout_seconds=2)

    @pytest.mark.asyncio
    async def test_new_tab_handling_exception(self):
        """Exception in new tab handling is caught."""
        page = _make_page(body_text="")
        page.url = "https://ems.com.cn/query"
        new_tab = MagicMock()
        new_tab.is_closed = MagicMock(return_value=False)
        new_tab.url = "https://ems.com.cn/agreement"
        new_tab.close = AsyncMock()
        ctx = _make_context(pages=[page, new_tab])

        with patch(f"{MODULE}.is_ems_dialog_visible", new_callable=AsyncMock, return_value=True), \
             patch(f"{MODULE}._ems_try_agreement_checkbox", new_callable=AsyncMock, return_value=True), \
             patch(f"{MODULE}._ems_accept_agreement_on_page", new_callable=AsyncMock, side_effect=RuntimeError("fail")), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            from apps.express_query.services.browser_query.ems_auth_handler import ems_handle_agreement_and_wait
            with pytest.raises(TimeoutError):
                await ems_handle_agreement_and_wait(ctx, page, timeout_seconds=2)

    @pytest.mark.asyncio
    async def test_login_success_dialog_closed_on_query(self):
        """Login success: dialog closed + on query page + body has keywords."""
        page = _make_page(body_text="邮件号查询")
        page.url = "https://ems.com.cn/query_express_delivery"

        with patch(f"{MODULE}.is_ems_dialog_visible", new_callable=AsyncMock, return_value=False), \
             patch(f"{MODULE}.ems_click_login_button", new_callable=AsyncMock, return_value=True), \
             patch(f"{MODULE}._ems_try_agreement_checkbox", new_callable=AsyncMock, return_value=False), \
             patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock):
            ctx = _make_context(pages=[page])
            from apps.express_query.services.browser_query.ems_auth_handler import ems_handle_agreement_and_wait
            # Agreement loop: dialog not visible -> reclick 20 times (instant with mocked sleep)
            # Scan loop: still_dialog=False, on_query=True, body has "邮件号" -> return
            await asyncio.wait_for(
                ems_handle_agreement_and_wait(ctx, page, timeout_seconds=30),
                timeout=5,
            )

    @pytest.mark.asyncio
    async def test_login_success_personal_center_redirect(self):
        """Login success via personal_center redirect."""
        page = _make_page(body_text="")
        page.url = "https://ems.com.cn/personal_center"

        call_count = [0]
        async def mock_dialog_visible(p):
            call_count[0] += 1
            return call_count[0] <= 20

        with patch(f"{MODULE}.is_ems_dialog_visible", side_effect=mock_dialog_visible), \
             patch(f"{MODULE}._ems_try_agreement_checkbox", new_callable=AsyncMock, return_value=False), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            ctx = _make_context(pages=[page])
            from apps.express_query.services.browser_query.ems_auth_handler import ems_handle_agreement_and_wait
            await asyncio.wait_for(
                ems_handle_agreement_and_wait(ctx, page, timeout_seconds=30),
                timeout=5,
            )

    @pytest.mark.asyncio
    async def test_login_success_logged_in_indicators(self):
        """Login success via logged-in indicators (body has keywords)."""
        page = _make_page(body_text="退出登录")
        page.url = "https://ems.com.cn/other"

        with patch(f"{MODULE}.is_ems_dialog_visible", new_callable=AsyncMock, return_value=False), \
             patch(f"{MODULE}.ems_click_login_button", new_callable=AsyncMock, return_value=True), \
             patch(f"{MODULE}._ems_try_agreement_checkbox", new_callable=AsyncMock, return_value=False), \
             patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock):
            ctx = _make_context(pages=[page])
            from apps.express_query.services.browser_query.ems_auth_handler import ems_handle_agreement_and_wait
            # Agreement loop: dialog not visible -> reclick 20 times (instant with mocked sleep)
            # Scan loop: still_dialog=False, body has "退出" -> return
            await asyncio.wait_for(
                ems_handle_agreement_and_wait(ctx, page, timeout_seconds=30),
                timeout=5,
            )

    @pytest.mark.asyncio
    async def test_scan_loop_text_content_exception(self):
        """Exception in scan loop body text_content is caught."""
        page = _make_page()
        page.url = "https://ems.com.cn/personal_center"

        call_count = [0]
        async def mock_dialog_visible(p):
            call_count[0] += 1
            return call_count[0] <= 20

        # Make body text_content raise
        body_loc = MagicMock()
        body_loc.text_content = AsyncMock(side_effect=RuntimeError("boom"))
        original_locator = page.locator

        def locator_override(sel):
            if sel == "body":
                return body_loc
            return original_locator(sel)

        page.locator = MagicMock(side_effect=locator_override)

        with patch(f"{MODULE}.is_ems_dialog_visible", side_effect=mock_dialog_visible), \
             patch(f"{MODULE}._ems_try_agreement_checkbox", new_callable=AsyncMock, return_value=False), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            ctx = _make_context(pages=[page])
            from apps.express_query.services.browser_query.ems_auth_handler import ems_handle_agreement_and_wait
            # personal_center URL -> success
            await asyncio.wait_for(
                ems_handle_agreement_and_wait(ctx, page, timeout_seconds=30),
                timeout=5,
            )

    @pytest.mark.asyncio
    async def test_new_tab_is_current_page_ignored(self):
        """New tab that IS the current page is ignored."""
        page = _make_page(body_text="")
        page.url = "https://ems.com.cn/query"
        ctx = _make_context(pages=[page])  # only one page

        with patch(f"{MODULE}.is_ems_dialog_visible", new_callable=AsyncMock, return_value=True), \
             patch(f"{MODULE}._ems_try_agreement_checkbox", new_callable=AsyncMock, return_value=False), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            from apps.express_query.services.browser_query.ems_auth_handler import ems_handle_agreement_and_wait
            with pytest.raises(TimeoutError):
                await ems_handle_agreement_and_wait(ctx, page, timeout_seconds=2)

    @pytest.mark.asyncio
    async def test_closed_tab_is_ignored(self):
        """Closed tabs in context.pages are ignored."""
        page = _make_page(body_text="")
        closed_tab = MagicMock()
        closed_tab.is_closed = MagicMock(return_value=True)
        ctx = _make_context(pages=[page, closed_tab])

        with patch(f"{MODULE}.is_ems_dialog_visible", new_callable=AsyncMock, return_value=True), \
             patch(f"{MODULE}._ems_try_agreement_checkbox", new_callable=AsyncMock, return_value=False), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            from apps.express_query.services.browser_query.ems_auth_handler import ems_handle_agreement_and_wait
            with pytest.raises(TimeoutError):
                await ems_handle_agreement_and_wait(ctx, page, timeout_seconds=2)
