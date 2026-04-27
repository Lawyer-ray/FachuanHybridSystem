"""国家企业信用信息公示系统登录服务（手动验证码介入模式）。"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Protocol

from django.utils import timezone

logger = logging.getLogger("apps.automation")

GSXT_LOGIN_URL = "https://shiming.gsxt.gov.cn/socialuser-use-rllogin.html"
CAPTCHA_TIMEOUT = 120  # 等待用户手动完成验证码的最长时间（秒）


class GsxtCredentialProtocol(Protocol):
    account: str
    password: str
    last_login_success_at: Any

    def save(self, *, update_fields: list[str]) -> None: ...


class GsxtLoginError(Exception):
    """登录失败异常。"""


async def _do_login_and_wait(credential: GsxtCredentialProtocol, task_id: int) -> None:
    """启动 Chrome，填账号密码，等待用户完成验证码，检测登录成功后更新任务状态。"""
    from asgiref.sync import sync_to_async
    from playwright.async_api import async_playwright

    from apps.automation.models.gsxt_report import GsxtReportStatus, GsxtReportTask

    get_task = sync_to_async(GsxtReportTask.objects.get)

    def _save_cred() -> None:
        credential.last_login_success_at = timezone.now()
        credential.save(update_fields=["last_login_success_at"])

    def _save_task(t: GsxtReportTask, fields: list[str]) -> None:
        t.save(update_fields=fields)

    async with async_playwright() as p:
        # 使用 launch(channel='chrome') 而非 connect_over_cdp
        # Chrome 147+ 不支持 CDP 的 Browser.setDownloadBehavior，
        # connect_over_cdp 会报 "Browser context management is not supported"
        browser = await p.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--no-first-run"],
        )
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await page.goto(GSXT_LOGIN_URL, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            await page.fill("#UserName", credential.account)
            await page.fill("#gsxtp", credential.password)
            await asyncio.sleep(0.5)
            await page.click("button:has-text('登录')")

            logger.info("已点击登录，等待用户完成验证码（最多 %d 秒）...", CAPTCHA_TIMEOUT)

            deadline = asyncio.get_event_loop().time() + CAPTCHA_TIMEOUT
            success = False
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(2)
                if "rllogin" not in page.url:
                    success = True
                    break

            task = await get_task(pk=task_id)
            if success:
                logger.info("登录成功，URL: %s", page.url)
                await sync_to_async(_save_cred)()
                task.status = GsxtReportStatus.PENDING
                await sync_to_async(_save_task)(task, ["status"])

                from apps.automation.services.gsxt.gsxt_report_service import start_report_flow

                start_report_flow(task_id)
            else:
                task.status = GsxtReportStatus.FAILED
                task.error_message = f"等待验证码超时（{CAPTCHA_TIMEOUT}秒）"
                await sync_to_async(_save_task)(task, ["status", "error_message"])
                logger.warning("等待验证码超时，任务 %d 失败", task_id)

        finally:
            # 不关闭浏览器，让用户可以看到验证码页面
            # 浏览器会在后续 report_flow 中复用或由用户手动关闭
            pass


def _run_in_thread(credential: GsxtCredentialProtocol, task_id: int) -> None:
    """在独立线程中运行异步登录流程（避免阻塞 Django 请求）。"""
    asyncio.run(_do_login_and_wait(credential, task_id))


class GsxtLoginService:
    """Class-based facade for GSXT login workflow."""

    def start_login(self, credential: GsxtCredentialProtocol, task_id: int) -> None:
        start_login_gsxt(credential, task_id)


def _try_reverse_login(credential: GsxtCredentialProtocol, task_id: int) -> bool:
    """尝试使用逆向登录，成功返回 True，不可用或失败返回 False。"""
    try:
        from apps.automation.services.gsxt.gsxt_reverse_login import reverse_login
    except ImportError:
        return False

    from apps.automation.models.gsxt_report import GsxtReportStatus, GsxtReportTask

    try:
        reverse_login(credential.account, credential.password)
    except NotImplementedError:
        logger.info("逆向登录模块存在但未配置打码平台，回退到 Playwright 模式")
        return False
    except Exception:
        logger.exception("逆向登录失败，回退到 Playwright 模式")
        return False

    # 登录成功，更新状态
    credential.last_login_success_at = timezone.now()
    credential.save(update_fields=["last_login_success_at"])

    task = GsxtReportTask.objects.get(pk=task_id)
    task.status = GsxtReportStatus.PENDING
    task.save(update_fields=["status"])
    logger.info("逆向登录成功，task_id=%d", task_id)

    from apps.automation.services.gsxt.gsxt_report_service import start_report_flow

    start_report_flow(task_id)
    return True


def start_login_gsxt(credential: GsxtCredentialProtocol, task_id: int) -> None:
    """
    非阻塞入口：优先尝试 HTTP 逆向登录，失败则回退到 Playwright 模式。

    Raises:
        GsxtLoginError: Chrome 启动失败（仅 Playwright 模式）。
    """
    # 优先尝试逆向登录（无需浏览器）
    if _try_reverse_login(credential, task_id):
        return

    # 回退到 Playwright 手动验证码模式
    t = threading.Thread(target=_run_in_thread, args=(credential, task_id), daemon=True)
    t.start()
    logger.info("登录后台线程已启动（Playwright 模式），task_id=%d", task_id)
