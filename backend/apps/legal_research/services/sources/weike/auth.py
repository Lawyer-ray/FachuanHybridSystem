from __future__ import annotations

import logging
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright

from .types import WeikeSession

logger = logging.getLogger(__name__)


class WeikeAuthMixin:
    def _normalize_login_url(self, login_url: str | None) -> str | None:
        if not login_url:
            return None

        parsed = urlparse(login_url)
        host = (parsed.hostname or "").lower()
        if host.endswith("wkinfo.com.cn"):
            return login_url

        logger.warning(
            "检测到非wk登录URL，自动回退到默认登录页",
            extra={"login_url": login_url},
        )
        return None

    def _ensure_playwright_session(self, session: WeikeSession) -> None:
        if session.page is not None:
            return

        if not session.username or not session.password:
            raise RuntimeError("wk会话缺少账号信息，无法回退Playwright")

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        try:
            self._login_and_enter_law(
                page=page,
                username=session.username,
                password=session.password,
                login_url=session.login_url,
            )
            session.playwright = playwright
            session.browser = browser
            session.context = context
            session.page = page
        except Exception:
            try:
                page.close()
                context.close()
                browser.close()
                playwright.stop()
            except Exception:
                pass
            raise

    def _login_and_enter_law(self, *, page: Page, username: str, password: str, login_url: str | None) -> None:
        page.goto(login_url or self.LOGIN_URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_selector("#firstname", timeout=60000)
        page.fill("#firstname", username)
        page.fill("#lastname", password)

        clicked = False
        selectors = [
            "input[type='submit'][value='Login']",
            "button:has-text('Login')",
            "button:has-text('登录')",
            "input[type='submit'][value='提交']",
            ".btn.btn-sign[type='submit']",
        ]
        for sel in selectors:
            locator = page.locator(sel)
            if locator.count() == 0:
                continue
            try:
                locator.first.click(timeout=8000)
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            page.keyboard.press("Enter")

        page.wait_for_timeout(2500)

        page.evaluate(
            """
            (() => {
              if (typeof getlaw === 'function') {
                getlaw();
                return;
              }
              const form = document.querySelector('#laws');
              if (form) {
                form.submit();
              }
            })();
            """
        )

        page.wait_for_timeout(2500)
        page.goto(self.LAW_LIST_URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_selector("input[name='keyword']", timeout=60000)

        body_text = page.locator("body").inner_text(timeout=30000)
        if "抱歉，此功能需要登录后操作" in body_text:
            raise RuntimeError("wk登录失败：账号未进入已登录状态")
