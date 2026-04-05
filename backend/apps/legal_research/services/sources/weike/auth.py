from __future__ import annotations

import logging
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright

from .types import WeikeSession

logger = logging.getLogger(__name__)


class WeikeAuthMixin:
    LAW_LOGIN_BUTTON_SELECTOR = "button.wk-banner-action-bar-item.wkb-btn-green:has-text('登录')"
    LAW_LOGIN_MODAL_USERNAME_SELECTOR = "#login-username"
    LAW_LOGIN_MODAL_PASSWORD_SELECTOR = "#login-password"
    LAW_LOGIN_MODAL_SUBMIT_SELECTOR = "button.login-submit-btn"
    LAW_LOGIN_REQUIRED_TEXT = "抱歉，此功能需要登录后操作"
    LAW_LIST_URL: str  # defined in subclass
    LOGIN_URL: str  # defined in subclass

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

        # 应用 playwright-stealth 反检测
        try:
            from playwright_stealth import Stealth
            stealth = Stealth()
            stealth.apply_stealth_sync(context)
            logger.debug("已应用 playwright-stealth 反检测")
        except ImportError:
            logger.warning("playwright-stealth 未安装，跳过反检测")

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
        self._login_via_legacy_home(page=page, username=username, password=password, login_url=login_url)
        page.goto(self.LAW_LIST_URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_selector("input[name='keyword']", timeout=60000)

        if self._contains_invalid_credential_hint(page):
            raise RuntimeError("wk登录失败：账号或密码错误")

        if not self._is_law_authenticated(page):
            self._login_via_law_modal(page=page, username=username, password=password)
            page.goto(self.LAW_LIST_URL, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_selector("input[name='keyword']", timeout=60000)

        if not self._is_law_authenticated(page):
            raise RuntimeError("wk登录失败：账号未进入已登录状态")

    def _login_via_legacy_home(self, *, page: Page, username: str, password: str, login_url: str | None) -> None:
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

        if self._contains_invalid_credential_hint(page):
            raise RuntimeError("wk登录失败：账号或密码错误")

    def _login_via_law_modal(self, *, page: Page, username: str, password: str) -> None:
        if not self._has_visible_locator(page, self.LAW_LOGIN_BUTTON_SELECTOR):
            return

        page.locator(self.LAW_LOGIN_BUTTON_SELECTOR).first.click(timeout=10000)
        page.wait_for_selector(self.LAW_LOGIN_MODAL_USERNAME_SELECTOR, timeout=20000)
        page.fill(self.LAW_LOGIN_MODAL_USERNAME_SELECTOR, username)
        page.fill(self.LAW_LOGIN_MODAL_PASSWORD_SELECTOR, password)
        self._check_law_login_agreement(page)
        page.locator(self.LAW_LOGIN_MODAL_SUBMIT_SELECTOR).first.click(timeout=10000, force=True)
        page.wait_for_timeout(3500)

    @staticmethod
    def _check_law_login_agreement(page: Page) -> None:
        page.evaluate(
            """
            (() => {
              const cb = document.querySelector('input.wk-field-choice');
              if (!cb) return false;
              cb.checked = true;
              cb.dispatchEvent(new Event('input', {bubbles: true}));
              cb.dispatchEvent(new Event('change', {bubbles: true}));
              return cb.checked;
            })();
            """
        )

    def _contains_invalid_credential_hint(self, page: Page) -> bool:
        body_text = page.locator("body").inner_text(timeout=30000)
        hints = (
            "用户名或密码输入错误",
            "账号或密码错误",
            "用户名或密码错误",
            "login.validateerror",
        )
        if any(h in body_text for h in hints):
            return True
        return "message=login.validateerror" in page.url

    def _is_law_authenticated(self, page: Page) -> bool:
        body_text = page.locator("body").inner_text(timeout=30000)
        if self.LAW_LOGIN_REQUIRED_TEXT in body_text:
            return False

        if self._has_visible_locator(page, self.LAW_LOGIN_MODAL_USERNAME_SELECTOR):
            return False

        if self._has_visible_locator(page, self.LAW_LOGIN_BUTTON_SELECTOR):
            return False

        return True

    @staticmethod
    def _has_visible_locator(page: Page, selector: str) -> bool:
        locator = page.locator(selector)
        count = locator.count()
        for i in range(min(count, 5)):
            if locator.nth(i).is_visible():
                return True
        return False
