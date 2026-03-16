"""国家企业信用信息公示系统登录服务（手动验证码介入模式）。"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import threading
import time
from typing import Any, Protocol

import httpx
from django.utils import timezone

logger = logging.getLogger("apps.automation")

GSXT_LOGIN_URL = "https://shiming.gsxt.gov.cn/socialuser-use-rllogin.html"
CDP_URL = "http://localhost:9222"
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_USER_DATA_DIR = "/tmp/chrome_debug_profile"
CAPTCHA_TIMEOUT = 120  # 等待用户手动完成验证码的最长时间（秒）


class GsxtCredentialProtocol(Protocol):
    account: str
    password: str
    last_login_success_at: Any

    def save(self, *, update_fields: list[str]) -> None: ...


class GsxtLoginError(Exception):
    """登录失败异常。"""


def _ensure_chrome_running() -> None:
    """确保 Chrome 以调试模式运行，如果未运行则自动启动。"""
    try:
        resp = httpx.get(f"{CDP_URL}/json/version", timeout=2)
        if resp.status_code == 200:
            return
    except Exception:
        pass

    logger.info("启动 Chrome 调试模式...")
    subprocess.Popen(
        [CHROME_PATH, "--remote-debugging-port=9222", f"--user-data-dir={CHROME_USER_DATA_DIR}", "--no-first-run"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(10):
        time.sleep(1)
        try:
            resp = httpx.get(f"{CDP_URL}/json/version", timeout=2)
            if resp.status_code == 200:
                logger.info("Chrome 启动成功")
                return
        except Exception:
            pass

    raise GsxtLoginError("Chrome 启动失败，请手动启动后重试")


async def _do_login_and_wait(credential: GsxtCredentialProtocol, task_id: int) -> None:
    """连接 Chrome，填账号密码，等待用户完成验证码，检测登录成功后更新任务状态。"""
    from apps.automation.models.gsxt_report import GsxtReportStatus, GsxtReportTask
    from asgiref.sync import sync_to_async
    from playwright.async_api import async_playwright

    get_task = sync_to_async(GsxtReportTask.objects.get)

    def _save_cred() -> None:
        credential.last_login_success_at = timezone.now()
        credential.save(update_fields=["last_login_success_at"])

    def _save_task(t: GsxtReportTask, fields: list[str]) -> None:
        t.save(update_fields=fields)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
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
            await page.close()


def _run_in_thread(credential: GsxtCredentialProtocol, task_id: int) -> None:
    """在独立线程中运行异步登录流程（避免阻塞 Django 请求）。"""
    asyncio.run(_do_login_and_wait(credential, task_id))


class GsxtLoginService:
    """Class-based facade for GSXT login workflow."""

    def start_login(self, credential: GsxtCredentialProtocol, task_id: int) -> None:
        start_login_gsxt(credential, task_id)


def start_login_gsxt(credential: GsxtCredentialProtocol, task_id: int) -> None:
    """
    非阻塞入口：启动 Chrome，填账号密码，在后台线程等待验证码完成。
    立即返回，不阻塞 Django 请求。

    Raises:
        GsxtLoginError: Chrome 启动失败。
    """
    _ensure_chrome_running()
    t = threading.Thread(target=_run_in_thread, args=(credential, task_id), daemon=True)
    t.start()
    logger.info("登录后台线程已启动，task_id=%d", task_id)
