"""Business logic services."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from playwright.sync_api import Page

from apps.core.path import Path

from .court_zxfw_selectors import CourtZxfwSelectors
from .court_zxfw_token_extractors import extract_login_token_from_json, is_jwt_like

logger = logging.getLogger("apps.automation")


class CaptchaRecognizerLike(Protocol):
    def recognize_from_element(self, page: Page, selector: str) -> str | None: ...


def check_login_success(page: Page) -> bool:
    try:
        current_url = page.url
        if "login" not in (current_url or "").lower():
            return True

        try:
            error_selectors: list[Any] = [
                "text=验证码错误",
                "text=账号或密码错误",
                "text=登录失败",
                ".error-message",
                ".login-error",
            ]
            for selector in error_selectors:
                error_elem = page.locator(selector)
                if error_elem.count() > 0 and error_elem.first.is_visible():
                    return False
        except Exception:
            logger.debug("check_login_error_selectors_failed", exc_info=True)

        try:
            user_info_selectors: list[Any] = [
                "text=退出登录",
                "text=个人中心",
                ".user-info",
                ".user-avatar",
            ]
            for selector in user_info_selectors:
                elem = page.locator(selector)
                if elem.count() > 0:
                    return True
        except Exception:
            logger.debug("check_login_user_info_selectors_failed", exc_info=True)

        return "login" not in (current_url or "").lower()
    except Exception:
        logger.debug("check_login_success_failed", exc_info=True)
        return False


def refresh_captcha(page: Page, random_wait: Callable[[float, float], None]) -> None:
    try:
        captcha_img = page.locator(f"xpath={CourtZxfwSelectors.CAPTCHA_IMAGE_XPATH}")
        captcha_img.click()
        random_wait(1, 2)
    except Exception:
        logger.debug("refresh_captcha_failed", exc_info=True)


def recognize_captcha(
    *,
    page: Page,
    captcha_recognizer: CaptchaRecognizerLike,
    random_wait: Callable[[float, float], None],
    save_debug: bool,
) -> str | None:
    try:
        captcha_img = page.locator(f"xpath={CourtZxfwSelectors.CAPTCHA_IMAGE_XPATH}")
        captcha_img.wait_for(state="visible", timeout=10000)
        random_wait(0.5, 1)

        if save_debug:
            from apps.core.config import get_config

            captcha_screenshot = captcha_img.screenshot()
            media_root = get_config("django.media_root", None)
            if not media_root:
                raise RuntimeError("django.media_root 未配置")
            debug_dir = Path(str(media_root)) / "automation" / "debug"
            debug_dir.makedirs_p()
            captcha_path = debug_dir / f"captcha_{int(time.time())}.png"
            with open(captcha_path, "wb") as f:
                f.write(captcha_screenshot)
            logger.info("captcha_saved", extra={"captcha_path": str(captcha_path)})

        captcha_text = captcha_recognizer.recognize_from_element(
            page,
            f"xpath={CourtZxfwSelectors.CAPTCHA_IMAGE_XPATH}",
        )
        if captcha_text:
            return captcha_text
        return None
    except Exception:
        logger.debug("recognize_captcha_failed", exc_info=True)
        return None


@dataclass
class LoginResult:
    success: bool
    token: str | None
    url: str


class LoginTokenCapture:
    def __init__(self, page: Page) -> None:
        self._page = page
        self._token: str | None = None
        self._success: bool = False

        def handle_response(response) -> None:
            try:
                url = (response.url or "").lower()
                if "login" not in url or response.status != 200:
                    return

                content_type = (response.headers.get("content-type", "") or "").lower()
                if not ("application/json" in content_type or "text/" in content_type):
                    return

                response_text = response.text()
                import json

                response_body = json.loads(response_text)
                token = extract_login_token_from_json(response_body)
                if token and is_jwt_like(token):
                    self._token = token
                    self._success = True
            except Exception:
                logger.debug("login_token_capture_handle_failed", exc_info=True)

        self._handler = handle_response

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def success(self) -> bool:
        return self._success

    def reset(self) -> None:
        self._token = None
        self._success = False

    def start(self) -> None:
        if hasattr(self._page, "on"):
            self._page.on("response", self._handler)

    def stop(self) -> None:
        try:
            self._page.remove_listener("response", self._handler)
        except Exception:
            logger.debug("login_token_capture_stop_failed", exc_info=True)


class CourtZxfwLoginFlow:
    def __init__(
        self,
        *,
        page: Page,
        login_url: str,
        captcha_recognizer: CaptchaRecognizerLike,
        random_wait: Callable[[float, float], None],
        save_screenshot: Callable[[str], str] | None = None,
    ) -> None:
        self._page = page
        self._login_url = login_url
        self._captcha_recognizer = captcha_recognizer
        self._random_wait = random_wait
        self._save_screenshot = save_screenshot
        self._token_capture = LoginTokenCapture(page)

    def login(self, *, account: str, password: str, max_captcha_retries: int, save_debug: bool) -> LoginResult:
        self._token_capture.start()
        try:
            self._page.goto(self._login_url, timeout=30000, wait_until="networkidle")
            self._random_wait(2, 3)
            if save_debug and self._save_screenshot:
                self._save_screenshot("01_login_page")

            self._try_select_password_tab()
            if save_debug and self._save_screenshot:
                self._save_screenshot("02_password_tab_clicked")
            self._fill_credentials(account=account, password=password)
            if save_debug and self._save_screenshot:
                self._save_screenshot("03_credentials_filled")

            for attempt in range(1, max_captcha_retries + 1):
                result = self._check_already_logged_in()
                if result:
                    return result

                result = self._attempt_captcha_login(attempt, max_captcha_retries, save_debug)
                if result:
                    return result

            raise ValueError("登录失败")
        finally:
            self._token_capture.stop()

    def _check_already_logged_in(self) -> Optional[LoginResult | None]:
        """检查是否已经登录成功(通过 URL 或 token 判断)"""
        if "/pages/pc/home/index" in (self._page.url or ""):
            return LoginResult(success=True, token=self._token_capture.token, url=self._page.url)
        return None

    def _attempt_captcha_login(
        self, attempt: int, max_captcha_retries: int, save_debug: bool
    ) -> Optional[LoginResult | None]:
        """执行一次验证码识别 + 登录尝试,成功返回 LoginResult,需重试返回 None"""
        captcha_text = recognize_captcha(
            page=self._page,
            captcha_recognizer=self._captcha_recognizer,
            random_wait=self._random_wait,
            save_debug=save_debug,
        )
        if not captcha_text:
            if attempt >= max_captcha_retries:
                raise ValueError("验证码识别失败,已达最大重试次数")
            refresh_captcha(self._page, self._random_wait)
            return None

        self._submit_captcha_and_click_login(captcha_text, attempt, save_debug)

        result = self._check_login_result()
        if result:
            return result

        if attempt < max_captcha_retries:
            captcha_input = self._page.locator(f"xpath={CourtZxfwSelectors.CAPTCHA_INPUT_XPATH}")
            captcha_input.fill("")
            refresh_captcha(self._page, self._random_wait)
            return None

        raise ValueError("登录失败,已达最大重试次数")

    def _submit_captcha_and_click_login(self, captcha_text: str, attempt: int, save_debug: bool) -> None:
        """填写验证码并点击登录按钮"""
        captcha_input = self._page.locator(f"xpath={CourtZxfwSelectors.CAPTCHA_INPUT_XPATH}")
        captcha_input.wait_for(state="visible", timeout=10000)
        captcha_input.fill(captcha_text)
        self._random_wait(0.5, 1)
        if save_debug and self._save_screenshot:
            self._save_screenshot(f"04_captcha_filled_attempt_{attempt}")

        self._token_capture.reset()
        login_button = self._page.locator(f"xpath={CourtZxfwSelectors.LOGIN_BUTTON_XPATH}")
        login_button.wait_for(state="visible", timeout=10000)
        login_button.click()

        self._random_wait(3, 5)
        if save_debug and self._save_screenshot:
            self._save_screenshot(f"05_after_login_attempt_{attempt}")

    def _check_login_result(self) -> Optional[LoginResult | None]:
        """检查登录是否成功(URL / token / 页面元素)"""
        if "/pages/pc/home/index" in (self._page.url or ""):
            return LoginResult(success=True, token=self._token_capture.token, url=self._page.url)

        if self._token_capture.token:
            return LoginResult(success=True, token=self._token_capture.token, url=self._page.url)

        if check_login_success(self._page):
            return LoginResult(success=True, token=self._token_capture.token, url=self._page.url)

        return None

    def _try_select_password_tab(self) -> None:
        try:
            password_tab = self._page.locator(f"xpath={CourtZxfwSelectors.PASSWORD_LOGIN_TAB_XPATH}")
            password_tab.wait_for(state="visible", timeout=10000)
            password_tab.click()
            self._random_wait(1, 2)
        except Exception:
            logger.debug("select_password_tab_failed", exc_info=True)

    def _fill_credentials(self, *, account: str, password: str) -> None:
        account_input = self._page.locator(f"xpath={CourtZxfwSelectors.ACCOUNT_INPUT_XPATH}")
        account_input.wait_for(state="visible", timeout=10000)
        account_input.fill(account)
        self._random_wait(0.5, 1)

        password_input = self._page.locator(f"xpath={CourtZxfwSelectors.PASSWORD_INPUT_XPATH}")
        password_input.wait_for(state="visible", timeout=10000)
        password_input.fill(password)
        self._random_wait(0.5, 1)
