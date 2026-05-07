"""公众号登录状态管理（扫码 + Cookie 持久化）"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page

logger = logging.getLogger(__name__)

# Cookie 存储目录
COOKIE_DIR = Path(getattr(settings, "BASE_DIR", ".")) / "data" / "wechat_mp_cookies"


def _get_cookie_path(account_id: int) -> Path:
    """获取指定账号的 Cookie 文件路径"""
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    return COOKIE_DIR / f"account_{account_id}.json"


def load_cookies(context: BrowserContext, account_id: int) -> bool:
    """加载已保存的 Cookie 到浏览器上下文。

    Returns:
        True 如果成功加载了 Cookie，False 如果没有保存的 Cookie
    """
    cookie_path = _get_cookie_path(account_id)
    if not cookie_path.exists():
        logger.info("No saved cookies for account %d", account_id)
        return False

    try:
        cookies = json.loads(cookie_path.read_text(encoding="utf-8"))
        if cookies:
            context.add_cookies(cookies)
            logger.info("Loaded %d cookies for account %d", len(cookies), account_id)
            return True
    except (json.JSONDecodeError, Exception):
        logger.warning("Failed to load cookies for account %d", account_id, exc_info=True)

    return False


def save_cookies(context: BrowserContext, account_id: int) -> None:
    """保存当前浏览器上下文的 Cookie。"""
    cookie_path = _get_cookie_path(account_id)
    cookie_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        cookies = context.cookies()
        cookie_path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Saved %d cookies for account %d", len(cookies), account_id)
    except Exception:
        logger.warning("Failed to save cookies for account %d", account_id, exc_info=True)


def check_login_status(page: Page) -> bool:
    """检查当前页面是否已登录公众号后台。

    通过检测页面元素判断登录状态。
    """
    try:
        # 公众号后台登录后会有特定元素
        # 检查是否跳转到了登录页
        current_url = page.url
        if "mp.weixin.qq.com/cgi-bin/loginpage" in current_url:
            return False

        # 检查是否有用户信息区域（已登录标志）
        user_info = page.query_selector(".user_info, .main_hd, .weui-desktop-account__nickname")
        return user_info is not None
    except Exception:
        logger.warning("Failed to check login status", exc_info=True)
        return False


def wait_for_qr_scan(page: Page, timeout_seconds: int = 120) -> bool:
    """等待用户扫码登录。

    Args:
        page: Playwright 页面对象
        timeout_seconds: 超时时间（秒）

    Returns:
        True 如果登录成功，False 如果超时
    """
    import time

    start_time = time.time()
    check_interval = 2  # 每 2 秒检查一次

    while time.time() - start_time < timeout_seconds:
        if check_login_status(page):
            logger.info("QR scan login successful")
            return True
        time.sleep(check_interval)

    logger.warning("QR scan login timeout after %d seconds", timeout_seconds)
    return False


def capture_qr_code(page: Page) -> bytes | None:
    """截取登录二维码区域的截图。

    Returns:
        二维码图片的 bytes，如果未找到返回 None
    """
    try:
        # 尝试定位二维码区域
        qr_selectors = [
            ".login__type__container__scan",
            ".qrcode",
            "#loginQrCode",
            "img[src*='qrcode']",
            ".login_box",
        ]

        for selector in qr_selectors:
            qr_element = page.query_selector(selector)
            if qr_element:
                return qr_element.screenshot()

        # 如果找不到特定元素，截取整个页面
        logger.warning("QR code element not found, capturing full page")
        return page.screenshot()
    except Exception:
        logger.warning("Failed to capture QR code", exc_info=True)
        return None
