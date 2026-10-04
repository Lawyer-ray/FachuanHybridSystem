"""PlaywrightInvoiceMixin._open_page 编排单测（不起真浏览器）。

mock create_browser_async_manual 与 page/context/auth，断言：
- 登录分支（缓存 cookie 有效 / 失效 / 无缓存 SSO）的调用序列
- 案件编号注入 evaluate 的选择器参数与取值
- 查找按钮 / 目标行 / 申请入口的 XPath 定位与点击
- 行级定位未命中时不点「申请对外开票」；异常路径回收会话
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.oa_filing.services.oa_scripts.jtn.invoice import playwright_invoice as pi_mod
from apps.oa_filing.services.oa_scripts.jtn.invoice.playwright_invoice import PlaywrightInvoiceMixin

_INVOICE_PAGE_URL = "https://ims.jtn.com/invoice/ProjectFapiaoRequest.aspx?x=1"
_LOGIN_PAGE_URL = "https://ims.jtn.com/member/login.aspx"


class _PageFactory:
    """按 selector 记录 locator 调用并允许逐 selector 配置 count。"""

    def __init__(self, url: str, counts: dict[str, int] | None = None) -> None:
        self.url = url
        self.counts = counts or {}
        self.selectors: list[str] = []
        self.locators: dict[str, MagicMock] = {}
        self.context = MagicMock()
        self.page = MagicMock()
        self.page.url = url
        self.page.goto = AsyncMock()
        self.page.evaluate = AsyncMock()
        self.page.wait_for_url = AsyncMock()

        def locator(selector: str) -> MagicMock:
            cached = self.locators.get(selector)
            if cached is not None:
                return cached
            self.selectors.append(selector)
            loc = MagicMock()
            loc.count = AsyncMock(return_value=self.counts.get(selector, 1))
            loc.click = AsyncMock()
            first = MagicMock()
            first.click = AsyncMock()
            loc.first = first
            self.locators[selector] = loc
            return loc

        self.page.locator = locator

    def apply_to(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
        """把工厂页面挂到 create_browser_async_manual，返回可断言的 close hook。"""
        session = SimpleNamespace(page=self.page, context=self.context)
        closes: dict[str, AsyncMock] = {"close": AsyncMock()}
        monkeypatch.setattr(pi_mod, "create_browser_async_manual", AsyncMock(return_value=session))
        monkeypatch.setattr(pi_mod, "close_browser_session", closes["close"])
        return closes


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    sleep = AsyncMock()
    monkeypatch.setattr(pi_mod, "asyncio", SimpleNamespace(sleep=sleep))
    return sleep


def _make_script(page_url: str = _INVOICE_PAGE_URL, cached_cookies: Any = None) -> tuple[Any, MagicMock]:
    auth = MagicMock()
    auth.load_cookies = MagicMock(return_value=cached_cookies)
    auth.inject_to_context = AsyncMock()
    auth.perform_sso_login = AsyncMock(return_value=[{"name": "fresh"}])
    script = PlaywrightInvoiceMixin()
    script._account = "acc"
    script._password = "p"
    script._auth = auth
    return script, auth


class TestOpenPageLoginBranches:
    @pytest.mark.asyncio
    async def test_cached_cookies_valid_skips_sso(self, no_sleep, monkeypatch):
        factory = _PageFactory(_INVOICE_PAGE_URL)
        closes = factory.apply_to(monkeypatch)
        script, auth = _make_script(cached_cookies=[{"name": "sid"}])

        session = await script._open_page("OA-2026-001")

        assert session.page is factory.page
        assert session.context is factory.context
        auth.load_cookies.assert_called_once()
        auth.inject_to_context.assert_awaited_once_with(factory.context, [{"name": "sid"}])
        auth.perform_sso_login.assert_not_awaited()
        closes["close"].assert_not_awaited()
        # 登录预检 + 正式导航各一次
        assert factory.page.goto.await_count == 2
        factory.page.goto.assert_any_await(pi_mod._INVOICE_URL, wait_until="domcontentloaded", timeout=60_000)
        factory.page.wait_for_url.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_cached_cookies_performs_sso(self, no_sleep, monkeypatch):
        factory = _PageFactory(_INVOICE_PAGE_URL)
        factory.apply_to(monkeypatch)
        script, auth = _make_script(cached_cookies=None)

        result_session = await script._open_page("OA-2026-001")

        auth.perform_sso_login.assert_awaited_once_with(factory.page, factory.context)
        auth.inject_to_context.assert_awaited_once_with(factory.context, [{"name": "fresh"}])
        assert result_session.page is factory.page
        factory.page.evaluate.assert_awaited()

    @pytest.mark.asyncio
    async def test_stale_cookies_fall_back_to_sso_then_wait_redirect(self, no_sleep, monkeypatch):
        # 页面 URL 一直停在登录页：缓存失效 → SSO；导航后仍在登录页 → wait_for_url
        factory = _PageFactory(_LOGIN_PAGE_URL)
        factory.apply_to(monkeypatch)
        script, auth = _make_script(cached_cookies=[{"name": "expired"}])

        await script._open_page("")

        auth.perform_sso_login.assert_awaited_once_with(factory.page, factory.context)
        inject_calls = auth.inject_to_context.await_args_list
        # 失效缓存先注入一次，SSO 后再注入新 cookies
        assert inject_calls[0].args == (factory.context, [{"name": "expired"}])
        assert inject_calls[1].args == (factory.context, [{"name": "fresh"}])
        factory.page.wait_for_url.assert_awaited_once_with("**/ims.jtn.com/invoice/**", timeout=180_000)
        # 空案件编号 → 不注入、不定位
        factory.page.evaluate.assert_not_awaited()
        assert factory.selectors == []


class TestOpenPageCaseNumberInput:
    @pytest.mark.asyncio
    async def test_input_search_and_apply_click_sequence(self, no_sleep, monkeypatch):
        factory = _PageFactory(_INVOICE_PAGE_URL)
        factory.apply_to(monkeypatch)
        script, _ = _make_script(cached_cookies=[{"name": "sid"}])

        await script._open_page("OA-2026-001")

        # 案件编号通过 evaluate 注入（去掉 # 的 input id）
        evaluate_call = factory.page.evaluate.await_args
        assert evaluate_call.args[0].startswith("({ inputId, value })")
        assert evaluate_call.args[1] == {
            "inputId": "ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_no",
            "value": "OA-2026-001",
        }
        # 查找按钮 → 目标行 → 行内申请链接
        search_selector = f"xpath={pi_mod._SEARCH_BTN_XP}"
        row_selector = 'xpath=//tr[contains(., "OA-2026-001")]'
        apply_selector = row_selector + '//a[contains(., "申请") or contains(., "开票")]'
        assert search_selector in factory.selectors
        assert row_selector in factory.selectors
        assert apply_selector in factory.selectors
        assert factory.selectors.index(search_selector) < factory.selectors.index(row_selector)

        # 通过 page.locator 重新拿 locator mock 校验点击
        search_btn = factory.page.locator(search_selector)
        search_btn.click.assert_awaited_once_with(timeout=10_000)
        apply_link = factory.page.locator(apply_selector)
        apply_link.first.click.assert_awaited_once_with(timeout=10_000)

    @pytest.mark.asyncio
    async def test_search_button_missing_skips_click(self, no_sleep, monkeypatch):
        search_selector = f"xpath={pi_mod._SEARCH_BTN_XP}"
        row_selector = 'xpath=//tr[contains(., "OA-X")]'
        apply_selector = row_selector + '//a[contains(., "申请") or contains(., "开票")]'
        factory = _PageFactory(_INVOICE_PAGE_URL, counts={search_selector: 0, row_selector: 1, apply_selector: 1})
        factory.apply_to(monkeypatch)
        script, _ = _make_script(cached_cookies=[{"name": "sid"}])

        session = await script._open_page("OA-X")

        # 查找按钮缺失只跳过按钮点击，目标行与申请入口仍正常处理
        factory.page.locator(search_selector).click.assert_not_awaited()
        apply_link = factory.page.locator(apply_selector)
        apply_link.first.click.assert_awaited_once_with(timeout=10_000)
        assert session is not None

    @pytest.mark.asyncio
    async def test_row_not_found_never_clicks_apply(self, no_sleep, monkeypatch):
        row_selector = 'xpath=//tr[contains(., "OA-MISSING")]'
        apply_selector = row_selector + '//a[contains(., "申请") or contains(., "开票")]'
        factory = _PageFactory(_INVOICE_PAGE_URL, counts={row_selector: 0, apply_selector: 0})
        factory.apply_to(monkeypatch)
        script, _ = _make_script(cached_cookies=[{"name": "sid"}])

        session = await script._open_page("OA-MISSING")

        # 重试 10 次仍未出现目标行 → 不点申请入口，浏览器保持打开
        assert no_sleep.await_count >= 10
        factory.page.locator(apply_selector).first.click.assert_not_awaited()
        assert session is not None

    @pytest.mark.asyncio
    async def test_row_found_but_no_apply_link(self, no_sleep, monkeypatch):
        row_selector = 'xpath=//tr[contains(., "OA-9")]'
        apply_selector = row_selector + '//a[contains(., "申请") or contains(., "开票")]'
        factory = _PageFactory(_INVOICE_PAGE_URL, counts={row_selector: 1, apply_selector: 0})
        factory.apply_to(monkeypatch)
        script, _ = _make_script(cached_cookies=[{"name": "sid"}])

        session = await script._open_page("OA-9")

        factory.page.locator(apply_selector).first.click.assert_not_awaited()
        assert session is not None


class TestOpenPageErrorPath:
    @pytest.mark.asyncio
    async def test_exception_reclaims_session_and_reraises(self, no_sleep, monkeypatch):
        factory = _PageFactory(_INVOICE_PAGE_URL)
        closes = factory.apply_to(monkeypatch)
        factory.page.goto = AsyncMock(side_effect=RuntimeError("goto failed"))
        script, _ = _make_script(cached_cookies=[{"name": "sid"}])

        with pytest.raises(RuntimeError, match="goto failed"):
            await script._open_page("OA-1")

        closes["close"].assert_awaited_once()
