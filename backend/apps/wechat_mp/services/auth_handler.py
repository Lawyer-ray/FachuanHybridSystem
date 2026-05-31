"""公众号登录状态管理（账号密码 + 扫码检测）"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger(__name__)

async def fetch_wechat_mp_credentials() -> tuple[str, str] | None:
    """从 AccountCredential 获取公众号后台账号密码。

    Returns:
        (account, password) 元组，未找到返回 None
    """
    from asgiref.sync import sync_to_async

    from apps.organization.models import AccountCredential

    def _query() -> tuple[str, str] | None:
        cred = AccountCredential.objects.filter(
            site_name="微信公众号后台",
        ).first()
        if cred:
            return str(cred.account), str(cred.password)
        return None

    result = await sync_to_async(_query)()
    return result

async def check_login_status(page: Page) -> bool:
    """检查当前页面是否已登录公众号后台。"""
    try:
        current_url = page.url
        if "mp.weixin.qq.com/cgi-bin/loginpage" in current_url:
            return False

        # 实际 DOM 中的登录状态标识
        login_indicators = [
            ".mp_account_box",
            ".acount_box-nickname",
            ".weui-desktop-account__info",
        ]
        for selector in login_indicators:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                return True
        return False
    except Exception as exc:
        if "Execution context was destroyed" in str(exc):
            return False
        logger.warning("Failed to check login status: %s", exc)
        return False

async def login_with_credentials(page: Page, account: str, password: str) -> bool:
    """使用账号密码登录公众号后台。

    流程：导航到登录页 → 切换到账号密码模式 → 填写账号密码 → 提交。
    登录后可能需要扫码二次验证，调用方需配合 wait_for_qr_scan。

    Returns:
        True 如果直接登录成功（无需扫码），False 如果需要扫码或失败
    """
    try:
        # 导航到登录页
        await page.goto(
            "https://mp.weixin.qq.com/cgi-bin/loginpage",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await asyncio.sleep(2)

        # 如果已经登录了，直接返回
        if await check_login_status(page):
            logger.info("Already logged in")
            return True

        # 尝试切换到账号密码登录模式
        # 公众号后台登录页可能有 "使用邮箱登录" / "账号登录" 等切换入口
        switch_selectors = [
            "text=使用邮箱登录",
            "text=使用账号登录",
            "text=账号登录",
            "text=邮箱登录",
            "text=使用其他方式登录",
            ".login__type__switch",
            "a:has-text('邮箱')",
            "a:has-text('账号')",
            "span:has-text('邮箱')",
        ]

        switched = False
        for selector in switch_selectors:
            try:
                switch_btn = await page.query_selector(selector)
                if switch_btn and await switch_btn.is_visible():
                    await switch_btn.click()
                    await asyncio.sleep(1)
                    switched = True
                    logger.info("Switched to account/password login: %s", selector)
                    break
            except Exception:
                continue

        if not switched:
            logger.warning("Could not find account/password login switch, trying direct fill")

        # 填写账号
        account_selectors = [
            "input[placeholder*='邮箱']",
            "input[placeholder*='账号']",
            "input[placeholder*='微信号']",
            "input[placeholder*='QQ号']",
            "input[name='account']",
            "input[type='text']",
            "#account",
        ]

        account_filled = False
        for selector in account_selectors:
            try:
                account_input = await page.query_selector(selector)
                if account_input and await account_input.is_visible():
                    await account_input.click()
                    await account_input.fill(account)
                    account_filled = True
                    logger.info("Account filled with selector: %s", selector)
                    break
            except Exception:
                continue

        if not account_filled:
            logger.warning("Could not find account input field")
            return False

        # 填写密码
        password_selectors = [
            "input[type='password']",
            "input[placeholder*='密码']",
            "input[name='password']",
            "#password",
        ]

        password_filled = False
        for selector in password_selectors:
            try:
                password_input = await page.query_selector(selector)
                if password_input and await password_input.is_visible():
                    await password_input.click()
                    await password_input.fill(password)
                    password_filled = True
                    logger.info("Password filled with selector: %s", selector)
                    break
            except Exception:
                continue

        if not password_filled:
            logger.warning("Could not find password input field")
            return False

        # 点击登录按钮
        login_selectors = [
            "button:has-text('登录')",
            "button:has-text('登 录')",
            "input[type='submit']",
            ".btn_login",
            "button[type='submit']",
            "a:has-text('登录')",
        ]

        for selector in login_selectors:
            try:
                login_btn = await page.query_selector(selector)
                if login_btn and await login_btn.is_visible():
                    await login_btn.click()
                    await asyncio.sleep(3)
                    logger.info("Login button clicked: %s", selector)
                    break
            except Exception:
                continue

        # 检查是否直接登录成功
        if await check_login_status(page):
            logger.info("Login successful with account/password")
            return True

        # 没有直接成功，可能需要扫码二次验证
        logger.info("Account/password submitted, may need QR verification")
        return False

    except Exception as exc:
        logger.error("Login with credentials failed: %s", exc, exc_info=True)
        return False

async def wait_for_qr_scan(page: Page, timeout_seconds: int = 120) -> bool:
    """等待用户扫码登录。

    Args:
        page: Playwright 页面对象
        timeout_seconds: 超时时间（秒）

    Returns:
        True 如果登录成功，False 如果超时
    """
    start_time = time.time()
    check_interval = 2

    while time.time() - start_time < timeout_seconds:
        if await check_login_status(page):
            logger.info("QR scan login successful")
            return True
        await asyncio.sleep(check_interval)

    logger.warning("QR scan login timeout after %d seconds", timeout_seconds)
    return False

async def capture_qr_code(page: Page) -> bytes | None:
    """截取登录二维码区域的截图。

    Returns:
        二维码图片的 bytes，如果未找到返回 None
    """
    try:
        qr_selectors = [
            ".login__type__container__scan",
            ".qrcode",
            "#loginQrCode",
            "img[src*='qrcode']",
            ".login_box",
        ]

        for selector in qr_selectors:
            qr_element = await page.query_selector(selector)
            if qr_element:
                return await qr_element.screenshot()

        logger.warning("QR code element not found, capturing full page")
        return await page.screenshot()
    except Exception:
        logger.warning("Failed to capture QR code", exc_info=True)
        return None
