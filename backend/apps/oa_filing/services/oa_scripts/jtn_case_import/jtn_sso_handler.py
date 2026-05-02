"""SSO/飞连/企微登录处理。"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

from django.utils.translation import gettext_lazy as _
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from .jtn_http_client import _CASE_LIST_URL, _HTTP_HEADERS

logger = logging.getLogger("apps.oa_filing.jtn_case_import")


class JtnSsoHandlerMixin:
    """SSO/飞连/企微登录处理。"""

    # --- 由 facade 或其他 mixin 提供 ---
    _account: str
    _password: str
    _http_cookies_cache: dict[str, str] | None
    _context: BrowserContext | None

    # ------------------------------------------------------------------
    # SSO 检测
    # ------------------------------------------------------------------
    def _is_sso_login_page(self: Any, *, url: str, html_text: str) -> bool:
        url_text = str(url or "").strip()
        parsed = urlparse(url_text)
        host = str(parsed.hostname or "").lower()
        if host == "access.jtn.com" or host.endswith(".access.jtn.com"):
            return True

        text_lower = str(html_text or "").lower()
        markers = (
            "企业微信 quick login",
            "please scan the qr code above in wechat work",
            "multiple-pages/qrcode-login",
            "access.jtn.com/login",
            "access.jtn.com/multiple-pages",
        )
        return any(marker in text_lower for marker in markers)

    def _build_sso_blocking_message(self: Any, *, stage: str, login_url: str) -> str:
        return str(
            _(
                "%(stage)s 触发飞连/企微单点登录（二维码），当前自动化无法完成无交互登录。"
                "请先在可见浏览器完成扫码登录后重试：%(login_url)s"
            )
            % {"stage": stage, "login_url": login_url}
        )

    def _raise_if_sso_blocking(self: Any, *, url: str, html_text: str, stage: str) -> None:
        if not self._is_sso_login_page(url=url, html_text=html_text):
            return
        login_url = str(url or "").strip()
        message = self._build_sso_blocking_message(stage=stage, login_url=login_url)
        logger.warning("%s", message)
        raise RuntimeError(message)

    def _is_sso_blocking_error(self: Any, exc: Exception) -> bool:
        text = str(exc or "")
        return "飞连/企微单点登录（二维码）" in text

    def _extract_sso_login_url_from_text(self: Any, text: str) -> str:
        message = str(text or "")
        matched = re.search(r"https://access\.jtn\.com/[^\s\"'<>]+", message)
        if matched:
            return str(matched.group(0)).strip()
        return "https://access.jtn.com/login"

    # ------------------------------------------------------------------
    # 飞连/企微交互登录
    # ------------------------------------------------------------------
    def _complete_sso_interactive_login(self: Any, *, login_url: str) -> dict[str, str]:
        target_url = str(login_url or "").strip() or "https://access.jtn.com/login"
        logger.warning("请在弹出的浏览器完成飞连/企微扫码登录（系统将自动检测登录成功），最多等待 180 秒")

        pw = sync_playwright().start()
        browser: Browser | None = None
        try:
            # Docker/NAS 环境通常没有 XServer，缺少 DISPLAY 时自动走无头模式。
            _headless = not bool(os.environ.get("DISPLAY"))
            browser = pw.chromium.launch(headless=_headless)
            context = browser.new_context()
            page = context.new_page()
            page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)

            deadline = time.time() + 180
            merged_cookies = dict(self._http_cookies_cache or {})
            has_triggered_case_list_navigation = False
            while time.time() < deadline:
                if any(self._is_ims_case_list_url(str(candidate_page.url or "")) for candidate_page in context.pages):
                    logger.info("检测到浏览器已进入 OA 列表页，判定交互登录完成")
                    break

                ims_cookies = self._collect_ims_cookies_from_browser_context(context)
                if ims_cookies:
                    merged_cookies.update(ims_cookies)
                    if self._can_access_case_list_with_cookies(merged_cookies):
                        logger.info("检测到 OA 会话可用，判定交互登录完成")
                        break

                if not has_triggered_case_list_navigation and self._is_access_portal_logged_in(page):
                    has_triggered_case_list_navigation = True
                    logger.info("检测到已登录飞连门户，自动跳转 OA 列表进行会话校验")
                    try:
                        page.goto(_CASE_LIST_URL, wait_until="domcontentloaded", timeout=60_000)
                        continue
                    except Exception:
                        logger.debug("门户跳转 OA 列表失败，等待用户继续操作", exc_info=True)

                time.sleep(1)
            else:
                raise RuntimeError(str(_("等待扫码登录超时，请完成扫码后重试")))

            if not merged_cookies:
                raise RuntimeError(str(_("扫码登录完成，但未获取到 OA 会话，请重试")))

            self._http_cookies_cache = dict(merged_cookies)
            logger.info("交互登录成功，已回灌 cookie=%d", len(merged_cookies))
            return dict(merged_cookies)
        finally:
            if browser is not None:
                browser.close()
            pw.stop()

    def _is_ims_case_list_url(self: Any, url: str) -> bool:
        parsed = urlparse(str(url or "").strip())
        host = (parsed.netloc or "").lower()
        path = (parsed.path or "").lower()
        if host != "ims.jtn.com":
            return False
        if path == "/member/login.aspx":
            return False
        return path.startswith("/project/")

    def _is_access_portal_logged_in(self: Any, page: Page) -> bool:
        current_url = str(page.url or "").lower()
        if "access.jtn.com" not in current_url:
            return False
        if "/login" in current_url:
            return False
        try:
            content_text = str(page.content() or "")
        except Exception:
            return False
        markers = ("推荐应用", "搜索应用/平台名称", "IMS", "aijagent")
        return any(marker in content_text for marker in markers)

    def _collect_ims_cookies_from_browser_context(self: Any, context: BrowserContext) -> dict[str, str]:
        return {
            str(item.get("name") or ""): str(item.get("value") or "")
            for item in context.cookies("https://ims.jtn.com")
            if str(item.get("name") or "").strip()
        }

    def _can_access_case_list_with_cookies(self: Any, cookies: dict[str, str]) -> bool:
        import httpx

        if not cookies:
            return False
        try:
            with httpx.Client(
                headers=_HTTP_HEADERS,
                follow_redirects=True,
                timeout=10,
                cookies=cookies,
                trust_env=False,
            ) as client:
                response = client.get(_CASE_LIST_URL)
                response.raise_for_status()
                return not self._is_sso_login_page(url=str(response.url), html_text=response.text)
        except Exception:
            return False
