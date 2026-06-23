"""金诚同达 OA 立案脚本 —— SSO 扫码登录 + Cookie 持久化。"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from .constants import _HTTP_HEADERS, _LOGIN_URL

logger = logging.getLogger("apps.oa_filing.jtn")

_COOKIE_PATH = Path.home() / ".fachuan" / "jtn_cookies.json"


class SsoLoginMixin:  # pragma: no cover
    """SSO 扫码登录 + Cookie 管理。"""

    _account: str
    _password: str

    # ------------------------------------------------------------------
    # Cookie 持久化
    # ------------------------------------------------------------------

    @staticmethod
    def _save_cookies(cookies: list[dict[str, Any]]) -> None:  # pragma: no cover
        """保存 cookies 到磁盘。"""
        _COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _COOKIE_PATH.write_text(json.dumps(cookies, indent=2, ensure_ascii=False))
        logger.info("已保存 %d 个 cookies 到 %s", len(cookies), _COOKIE_PATH)

    @staticmethod
    def _load_cookies() -> list[dict[str, Any]] | None:  # pragma: no cover
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

    async def _login_via_sso(self) -> list[dict[str, Any]]:  # pragma: no cover
        """完整的 SSO 扫码 + 凭证登录流程。

        打开有头浏览器 → 点击扫码图标 → 等待用户扫码 →
        填写账号密码 → 捕获 cookies → 关闭浏览器。
        """
        from apps.core.services.browser import create_browser_async

        async with create_browser_async("default", headless=False) as (page, context):
            # 1. 打开 OA 登录页（会重定向到 SSO）
            logger.info("SSO 登录: 打开 %s", _LOGIN_URL)
            await page.goto(_LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(3)

            # 2. 尝试点击扫码图标（失败不阻塞，用户可手动点击）
            try:
                await self._click_qr_icon(page)
                await asyncio.sleep(2)
            except RuntimeError:
                logger.warning("未自动找到扫码图标，请在浏览器中手动点击扫码")
            logger.info("SSO 登录: 请用企业微信扫码（等待 180 秒）")

            # 3. 等待扫码完成，跳转回 OA 登录页
            await page.wait_for_url("**/ims.jtn.com/**", timeout=180_000)
            await asyncio.sleep(3)
            logger.info("SSO 登录: 扫码完成，回到 OA 登录页")

            # 4. 填写账号密码并登录
            await page.fill('input[name="userid"]', self._account)
            await page.fill('input[name="password"]', self._password)
            await asyncio.sleep(0.5)
            await page.click("button.input_btn")
            await asyncio.sleep(5)

            # 5. 验证登录结果
            if "login" in page.url.lower():
                raise RuntimeError("OA 登录失败，请检查账号密码")

            logger.info("SSO 登录成功，当前页面: %s", page.url)

            # 6. 捕获 cookies 并转为可序列化的 dict 列表
            raw_cookies: list[Any] = await context.cookies()
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

    @staticmethod
    async def _click_qr_icon(page: Any) -> None:  # pragma: no cover
        """点击 SSO 页面右上角的扫码图标。

        按优先级尝试多种选择器策略，坐标匹配仅作最后兜底。
        """
        # 策略 1: CSS 选择器（按 src/class/id 匹配常见扫码图标）
        selectors = [
            'img[src*="scan"]',
            'img[src*="qr"]',
            'img[src*="ewm"]',  # 二维码的拼音
            'img[src*="code"]',
            'img[class*="scan"]',
            'img[class*="qr"]',
            'a[class*="scan"] img',
            'a[class*="qr"] img',
            '#scanIcon',
            '#qrIcon',
            '.scan-icon img',
            '.qr-code-icon',
        ]
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    logger.info("SSO 登录: 通过选择器 '%s' 找到扫码图标", sel)
                    return
            except Exception:
                continue

        # 策略 2: 宽松坐标匹配（页面右侧区域的小图标）
        all_els = await page.query_selector_all("img, svg, i[class*='icon'], span[class*='icon']")
        for el in all_els:
            try:
                box = await el.bounding_box()
                if box and box["x"] > 600 and box["y"] < 350 and box["width"] < 80 and box["height"] < 80:
                    await el.click()
                    logger.info("SSO 登录: 通过坐标匹配找到扫码图标 (x=%.0f, y=%.0f)", box["x"], box["y"])
                    return
            except Exception:
                continue

        raise RuntimeError("未找到 SSO 扫码图标")

    # ------------------------------------------------------------------
    # 获取有效 cookies（优先缓存，过期则重新登录）
    # ------------------------------------------------------------------

    async def _ensure_cookies(self) -> list[dict[str, Any]]:
        """确保有有效的 cookies，优先使用缓存。"""
        cached = self._load_cookies()
        if cached is not None:
            return cached
        return await self._login_via_sso()
