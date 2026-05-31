"""金诚同达 OA 立案脚本 —— SSO 扫码登录 + Cookie 持久化。"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from .constants import _HTTP_HEADERS, _LOGIN_URL

logger = logging.getLogger("apps.oa_filing.jtn")

_COOKIE_PATH = Path.home() / ".fachuan" / "jtn_cookies.json"

class SsoLoginMixin:
    """SSO 扫码登录 + Cookie 管理。"""

    _account: str
    _password: str

    # ------------------------------------------------------------------
    # Cookie 持久化
    # ------------------------------------------------------------------

    @staticmethod
    def _save_cookies(cookies: list[dict[str, Any]]) -> None:
        """保存 cookies 到磁盘。"""
        _COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _COOKIE_PATH.write_text(json.dumps(cookies, indent=2, ensure_ascii=False))
        logger.info("已保存 %d 个 cookies 到 %s", len(cookies), _COOKIE_PATH)

    @staticmethod
    def _load_cookies() -> list[dict[str, Any]] | None:
        """从磁盘加载 cookies，过滤已过期的。"""
        if not _COOKIE_PATH.exists():
            return None
        try:
            cookies = json.loads(_COOKIE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        import time as _time

        now = _time.time()
        valid = []
        for c in cookies:
            expires = c.get("expires", -1)
            if expires == -1 or expires > now:
                valid.append(c)
        if not valid:
            logger.info("缓存 cookies 已全部过期")
            return None
        logger.info("加载了 %d 个有效 cookies", len(valid))
        return valid

    # ------------------------------------------------------------------
    # SSO 扫码登录（Playwright 有头模式）
    # ------------------------------------------------------------------

    def _login_via_sso(self) -> list[dict[str, Any]]:
        """完整的 SSO 扫码 + 凭证登录流程。

        打开有头浏览器 → 点击扫码图标 → 等待用户扫码 →
        填写账号密码 → 捕获 cookies → 关闭浏览器。
        """
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        browser = None
        try:
            browser = pw.chromium.launch(headless=False)
            context = browser.new_context()
            context.set_default_timeout(30_000)
            page = context.new_page()

            # 1. 打开 OA 登录页（会重定向到 SSO）
            logger.info("SSO 登录: 打开 %s", _LOGIN_URL)
            page.goto(_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
            time.sleep(3)

            # 2. 点击扫码图标
            self._click_qr_icon(page)
            time.sleep(2)
            logger.info("SSO 登录: 二维码已显示，请用企业微信扫码")

            # 3. 等待扫码完成，跳转回 OA 登录页
            page.wait_for_url("**/ims.jtn.com/**", timeout=120_000)
            time.sleep(3)
            logger.info("SSO 登录: 扫码完成，回到 OA 登录页")

            # 4. 填写账号密码并登录
            page.fill('input[name="userid"]', self._account)
            page.fill('input[name="password"]', self._password)
            time.sleep(0.5)
            page.click("button.input_btn")
            time.sleep(5)

            # 5. 验证登录结果
            if "login" in page.url.lower():
                raise RuntimeError("OA 登录失败，请检查账号密码")

            logger.info("SSO 登录成功，当前页面: %s", page.url)

            # 6. 捕获 cookies 并转为可序列化的 dict 列表
            raw_cookies: list[Any] = context.cookies()
            cookies = [
                {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c["domain"],
                    "path": c["path"],
                    "expires": c.get("expires"),
                }
                for c in raw_cookies
            ]
            self._save_cookies(cookies)
            return cookies
        finally:
            if browser is not None:
                browser.close()
            pw.stop()

    @staticmethod
    def _click_qr_icon(page: Any) -> None:
        """点击 SSO 页面右上角的扫码图标。"""
        all_els = page.query_selector_all("img, svg")
        for el in all_els:
            box = el.bounding_box()
            if box and 750 < box["x"] < 800 and 220 < box["y"] < 280:
                el.click()
                return
        raise RuntimeError("未找到 SSO 扫码图标")

    # ------------------------------------------------------------------
    # 获取有效 cookies（优先缓存，过期则重新登录）
    # ------------------------------------------------------------------

    def _ensure_cookies(self) -> list[dict[str, Any]]:
        """确保有有效的 cookies，优先使用缓存。"""
        cached = self._load_cookies()
        if cached is not None:
            return cached
        return self._login_via_sso()
