"""国家企业信用信息公示系统登录+报告申请 一体化服务。

流程：手动启动 Chrome（不带自动化标记）→ CDP WebSocket 直接导航（绕过 Playwright 注入）
→ Playwright connect_over_cdp 接管已有页面 → 登录 → 搜索 → 详情 → 申请报告。

关键：Playwright 创建新页面时会注入自动化标记导致 gsxt 白屏，
必须先用 CDP WebSocket 直接导航，再让 Playwright 接管已有页面。
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import threading
import time
from typing import Any, Protocol

import httpx
from django.utils import timezone

logger = logging.getLogger("apps.automation")

GSXT_LOGIN_URL = "https://shiming.gsxt.gov.cn/socialuser-use-rllogin.html"
GSXT_SEARCH_URL = "https://shiming.gsxt.gov.cn/corp-query-homepage.html"
CDP_URL = "http://localhost:9222"
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_USER_DATA_DIR = "/tmp/chrome_gsxt_profile"
LOGIN_CAPTCHA_TIMEOUT = 120  # 等待用户完成登录验证码（秒）
REPORT_CAPTCHA_TIMEOUT = 180  # 等待用户完成搜索/报告验证码（秒）


class GsxtCredentialProtocol(Protocol):
    account: str
    password: str
    last_login_success_at: Any

    def save(self, *, update_fields: list[str]) -> None: ...


class GsxtLoginError(Exception):
    """登录失败异常。"""


class GsxtReportError(Exception):
    """报告申请失败异常。"""


# ──────────────────────────────────────────────
# Chrome 进程管理
# ──────────────────────────────────────────────


def _kill_existing_chrome() -> None:
    """关闭使用同一 user-data-dir 的已有 Chrome 实例。"""
    try:
        result = subprocess.run(
            ["/usr/bin/pgrep", "-fl", CHROME_USER_DATA_DIR],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.stdout.strip():
            logger.info("关闭已有的 GSXT Chrome 实例...")
            subprocess.run(
                ["/usr/bin/pkill", "-f", CHROME_USER_DATA_DIR],
                capture_output=True,
                timeout=5,
            )
            time.sleep(2)
    except Exception:
        pass


def _check_cdp_available() -> bool:
    """检查 CDP 端点是否可用。"""
    try:
        with httpx.Client(transport=httpx.HTTPTransport(http2=False)) as client:
            resp = client.get(f"{CDP_URL}/json/version", timeout=2)
            return resp.status_code == 200
    except Exception:
        return False


def _ensure_chrome_running() -> None:
    """确保 Chrome 以调试模式运行。"""
    if _check_cdp_available():
        logger.info("Chrome CDP 已就绪，复用现有实例")
        return

    _kill_existing_chrome()

    logger.info("启动 Chrome 调试模式（不带自动化标记）...")
    process = subprocess.Popen(
        [CHROME_PATH, "--remote-debugging-port=9222", f"--user-data-dir={CHROME_USER_DATA_DIR}", "--no-first-run"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    for i in range(15):
        time.sleep(1)
        if _check_cdp_available():
            logger.info("Chrome 启动成功")
            return
        if process.poll() is not None:
            stderr_output = process.stderr.read().decode() if process.stderr else ""
            logger.error("Chrome 进程意外退出, stderr: %s", stderr_output)
            break

    raise GsxtLoginError(
        "Chrome 启动失败。请先关闭所有 Chrome 窗口后重试，"
        f'或手动运行：\n  "{CHROME_PATH}" --remote-debugging-port=9222 --user-data-dir={CHROME_USER_DATA_DIR}'
    )


# ──────────────────────────────────────────────
# CDP WebSocket 直接导航（绕过 Playwright 自动化注入）
# ──────────────────────────────────────────────


async def _cdp_navigate(url: str, wait_seconds: int = 8) -> str:
    """通过 CDP WebSocket 直接导航到目标 URL，避免 Playwright 注入自动化标记。

    gsxt 会检测 Playwright 注入的 navigator.webdriver=true 而白屏。
    本函数直接通过 CDP 协议操作，不触发 Playwright 的自动化注入。

    Returns:
        导航后的页面 URL。
    """
    import os

    import websockets

    # 禁止 WebSocket 走代理
    os.environ.setdefault("no_proxy", "localhost,127.0.0.1")
    os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")

    # 获取第一个 page 类型的 tab
    with httpx.Client(transport=httpx.HTTPTransport(http2=False)) as client:
        tabs = client.get(f"{CDP_URL}/json").json()
        ws_url = None
        for tab in tabs:
            if tab.get("type") == "page":
                ws_url = tab["webSocketDebuggerUrl"]
                break

    if not ws_url:
        raise GsxtLoginError("CDP 无可用页面")

    async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
        # 启用 Page 事件
        await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
        await ws.recv()

        # 导航
        await ws.send(
            json.dumps(
                {
                    "id": 2,
                    "method": "Page.navigate",
                    "params": {"url": url},
                }
            )
        )
        await ws.recv()

        # 等待页面加载
        await asyncio.sleep(wait_seconds)

        # 获取当前 URL
        await ws.send(
            json.dumps(
                {
                    "id": 3,
                    "method": "Runtime.evaluate",
                    "params": {"expression": "window.location.href"},
                }
            )
        )
        while True:
            r = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(r)
            if msg.get("id") == 3:
                return str(msg.get("result", {}).get("result", {}).get("value", url))


# ──────────────────────────────────────────────
# 验证码等待
# ──────────────────────────────────────────────


async def _wait_captcha_success(page: Any, captcha_selector: str, timeout: int) -> bool:
    """轮询等待极验验证码完成。"""
    from playwright.async_api import Page

    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(2)
        try:
            done = await page.evaluate(f"""(() => {{
                const el = document.querySelector('{captcha_selector}');
                return el ? el.className.includes('geetest_lock_success') : false;
            }})()""")
            if done:
                return True
        except Exception:
            logger.warning("检查验证码状态时页面异常")
            return False
    return False


# ──────────────────────────────────────────────
# 完整流程：登录 → 搜索 → 详情 → 申请报告
# ──────────────────────────────────────────────


async def _run_full_flow(credential: GsxtCredentialProtocol, task_id: int) -> None:
    """在一个浏览器会话中完成：登录→搜索→详情→申请报告。"""
    from asgiref.sync import sync_to_async
    from playwright.async_api import BrowserContext, Page, async_playwright

    from apps.automation.models.gsxt_report import GsxtReportStatus, GsxtReportTask

    get_task = sync_to_async(GsxtReportTask.objects.select_related("client").get)

    def _save(t: GsxtReportTask, fields: list[str]) -> None:
        t.save(update_fields=fields)

    save_task = sync_to_async(_save)

    task = await get_task(pk=task_id)
    company_name: str = task.company_name
    credit_code: str = task.credit_code or ""

    # ── Step 0: 先用 CDP 直接导航到登录页（绕过 Playwright 自动化注入）──
    task.status = GsxtReportStatus.WAITING_CAPTCHA
    task.error_message = "正在打开登录页，请完成验证码"
    await save_task(task, ["status", "error_message"])

    login_url = await _cdp_navigate(GSXT_LOGIN_URL, wait_seconds=8)
    logger.info("CDP 导航完成，当前 URL: %s", login_url)

    # ── Step 1: Playwright 接管已有页面 ──
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        context: BrowserContext = browser.contexts[0]

        # 找到刚才 CDP 打开的页面（包含 gsxt 的页面）
        page: Page | None = None
        for pg in context.pages:
            try:
                if "gsxt.gov.cn" in pg.url:
                    page = pg
                    break
            except Exception:
                pass

        if not page:
            # 回退：取最后一个页面
            page = context.pages[-1] if context.pages else await context.new_page()
            logger.warning("未找到 gsxt 页面，使用回退页面: %s", page.url)

        logger.info("Playwright 接管页面: %s", page.url)

        detail_page: Page | None = None

        try:
            # ── Step 2: 填写登录表单 ──
            await asyncio.sleep(2)
            await page.fill("#UserName", credential.account)
            await page.fill("#gsxtp", credential.password)
            await asyncio.sleep(0.5)
            await page.click("button:has-text('登录')")

            logger.info("已点击登录，等待用户完成验证码...")

            deadline = asyncio.get_event_loop().time() + LOGIN_CAPTCHA_TIMEOUT
            login_success = False
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(2)
                try:
                    if "rllogin" not in page.url:
                        login_success = True
                        break
                except Exception:
                    pass

            if not login_success:
                task.status = GsxtReportStatus.FAILED
                task.error_message = f"等待登录验证码超时（{LOGIN_CAPTCHA_TIMEOUT}秒）"
                await save_task(task, ["status", "error_message"])
                logger.warning("登录验证码超时，任务 %d 失败", task_id)
                return

            # 登录成功
            logger.info("登录成功，URL: %s", page.url)
            credential.last_login_success_at = timezone.now()
            await sync_to_async(credential.save)(update_fields=["last_login_success_at"])

            # ── Step 3: 搜索企业 ──
            task.status = GsxtReportStatus.WAITING_CAPTCHA
            task.error_message = f"正在搜索：{company_name}，请完成验证码"
            await save_task(task, ["status", "error_message"])

            # 用 CDP 导航到搜索页（避免 Playwright goto 触发检测）
            search_url = await _cdp_navigate(GSXT_SEARCH_URL, wait_seconds=5)
            logger.info("已导航到搜索页: %s", search_url)

            # Playwright 需要刷新 page 引用
            await asyncio.sleep(2)

            await page.fill("#keyword", company_name)
            await asyncio.sleep(0.5)
            await page.click("#btn_query")

            logger.info("已点击搜索，等待用户完成验证码...")

            # 等待搜索结果页
            search_deadline = asyncio.get_event_loop().time() + REPORT_CAPTCHA_TIMEOUT
            while asyncio.get_event_loop().time() < search_deadline:
                await asyncio.sleep(2)
                try:
                    if "corp-query-search-1" in page.url:
                        logger.info("搜索结果页已加载: %s", page.url)
                        break
                except Exception:
                    pass
            else:
                raise GsxtReportError(f"等待搜索结果超时（{REPORT_CAPTCHA_TIMEOUT}秒）")

            # ── Step 4: 点击企业详情 ──
            task.error_message = "已找到搜索结果，正在进入详情页"
            await save_task(task, ["error_message"])

            # 先用公司名，失败时用信用代码
            try:
                detail_page = await _click_company_detail(page, company_name, context)
            except GsxtReportError:
                if not credit_code:
                    raise
                logger.info("公司名匹配失败，改用信用代码搜索: %s", credit_code)
                task.error_message = f"名称未匹配，改用信用代码 {credit_code} 重新搜索，请完成验证码"
                await save_task(task, ["error_message"])
                await page.fill("#keyword", credit_code)
                await asyncio.sleep(0.5)
                await page.click("#btn_query")
                await asyncio.sleep(5)
                detail_page = await _click_company_detail(page, company_name, context)

            # ── Step 5: 申请发送报告 ──
            task.error_message = "已进入详情页，请完成发送报告验证码"
            await save_task(task, ["error_message"])

            target = detail_page or page
            # 详情页改版后，"发送报告"按钮藏在"更多"下拉菜单中
            # 流程：点击 #moreActionsToggle → 显示 #moreActionsMenu → 点击 #btn_send_pdf
            try:
                await target.wait_for_selector("#moreActionsToggle", timeout=30000)
                await target.click("#moreActionsToggle")
                logger.info("已点击'更多'按钮，等待下拉菜单显示...")
                await asyncio.sleep(1)
            except Exception:
                logger.warning("未找到'更多'按钮，尝试直接点击 #btn_send_pdf")

            # 等待 #btn_send_pdf 出现（在下拉菜单中）
            try:
                await target.wait_for_selector("#btn_send_pdf", timeout=15000)
            except Exception:
                raise GsxtReportError("详情页未找到发送报告按钮，可能页面未完全加载")

            await target.click("#btn_send_pdf")
            logger.info("已点击发送报告，等待用户完成验证码...")

            done = await _wait_captcha_success(
                target,
                ".geetest_captcha.geetest_bind.geetest_lock_success",
                REPORT_CAPTCHA_TIMEOUT,
            )
            if not done:
                raise GsxtReportError(f"等待发送报告验证码超时（{REPORT_CAPTCHA_TIMEOUT}秒）")

            logger.info("验证码完成，点击弹窗发送按钮...")
            await target.wait_for_selector("#send_pdf_dialog", state="visible", timeout=10000)
            await target.click("#send_pdf_dialog div[onclick*='sendPdf']")

            # 等待 alert
            dialog_msg = ""

            async def handle_dialog(dialog: object) -> None:
                nonlocal dialog_msg
                dialog_msg = getattr(dialog, "message", "")
                await dialog.accept()  # type: ignore[attr-defined]

            target.on("dialog", handle_dialog)
            await asyncio.sleep(5)
            target.remove_listener("dialog", handle_dialog)
            logger.info("发送报告结果: %s", dialog_msg)

            if dialog_msg and ("失败" in dialog_msg or "error" in dialog_msg.lower()):
                raise GsxtReportError(f"发送报告失败：{dialog_msg}")

            # ── Step 6: 启动邮件轮询 ──
            task.status = GsxtReportStatus.WAITING_EMAIL
            task.error_message = "报告已发送到邮箱，正在自动轮询收取…"
            await save_task(task, ["status", "error_message"])
            logger.info("任务 %d：报告申请成功，启动邮件轮询", task_id)

            from datetime import timedelta

            from apps.core.tasking import ScheduleQueryService

            def _schedule_email_check() -> None:
                ScheduleQueryService().create_once_schedule(
                    func="apps.automation.tasks.gsxt_tasks.check_gsxt_report_email",
                    args=f"{task_id},{task.company_name!r}",
                    name=f"gsxt_email_first_{task_id}",
                    next_run=timezone.now() + timedelta(seconds=60),
                )

            await sync_to_async(_schedule_email_check)()

        except Exception as e:
            task.status = GsxtReportStatus.FAILED
            task.error_message = str(e)
            await save_task(task, ["status", "error_message"])
            logger.exception("任务 %d 失败: %s", task_id, e)

        finally:
            # 不关闭浏览器，让用户可以看到结果/验证码页面
            pass


async def _click_company_detail(page: Any, company_name: str, context: Any) -> Any:
    """点击搜索结果中的企业链接，返回详情页 Page（通常在新标签页中打开）。

    gsxt 搜索结果页的每个结果是一个 ``a.search_list_item`` ，企业名称在 ``h1`` 中。
    链接 ``target="_blank"`` 所以详情页会在新标签页打开。
    注意：不能通过 CDP 直接导航到详情页 URL（会被知道创宇 WAF 拦截），
    必须在搜索结果页上点击链接进入。
    """
    from playwright.async_api import BrowserContext, Page

    await asyncio.sleep(2)

    # 使用 a.search_list_item h1 匹配企业名称（新版本页面结构）
    # h1 中的关键词可能被 <font color="red"> 包裹，所以用 includes 而非精确匹配
    link_info = await page.evaluate(f"""(() => {{
        const items = document.querySelectorAll('a.search_list_item');
        for (const item of items) {{
            const h1 = item.querySelector('h1');
            if (!h1) continue;
            const name = h1.innerText.trim();
            if (name === '{company_name}' || name.includes('{company_name}')) {{
                return {{ href: item.href, name: name }};
            }}
        }}
        // 模糊匹配：去除括号和空格后比较
        const normalized = '{company_name}'.replace(/[()（）\\s]/g, '');
        for (const item of items) {{
            const h1 = item.querySelector('h1');
            if (!h1) continue;
            const name = h1.innerText.trim();
            const normName = name.replace(/[()（）\\s]/g, '');
            if (normName.includes(normalized) || normalized.includes(normName)) {{
                return {{ href: item.href, name: name }};
            }}
        }}
        return null;
    }})()""")

    if not link_info:
        raise GsxtReportError(f"搜索结果中未找到企业：{company_name}")

    logger.info("找到企业链接: %s (href: %s)", link_info["name"], link_info["href"][:80])

    new_page: Page | None = None

    async def _on_new_page(p: Page) -> None:
        nonlocal new_page
        new_page = p
        logger.info("检测到新标签页打开: %s", p.url[:80])

    context.on("page", _on_new_page)

    try:
        # 必须用 JS click 在搜索页上点击链接（不能用 CDP 导航，会被 WAF 拦截）
        clicked = await page.evaluate(f"""(() => {{
            const items = document.querySelectorAll('a.search_list_item');
            for (const item of items) {{
                const h1 = item.querySelector('h1');
                if (!h1) continue;
                const name = h1.innerText.trim();
                if (name === '{company_name}' || name.includes('{company_name}')) {{
                    item.click();
                    return true;
                }}
            }}
            const normalized = '{company_name}'.replace(/[()（）\\s]/g, '');
            for (const item of items) {{
                const h1 = item.querySelector('h1');
                if (!h1) continue;
                const name = h1.innerText.trim();
                const normName = name.replace(/[()（）\\s]/g, '');
                if (normName.includes(normalized) || normalized.includes(normName)) {{
                    item.click();
                    return true;
                }}
            }}
            return false;
        }})()""")

        if clicked:
            logger.info("已点击企业链接，等待详情页加载...")
            await asyncio.sleep(8)
        else:
            # 最后的回退：直接通过链接 URL 导航（可能被 WAF 拦截）
            logger.warning("JS 点击失败，回退到 CDP 导航（可能被 WAF 拦截）")
            await _cdp_navigate(link_info["href"], wait_seconds=10)
            await asyncio.sleep(3)
    except Exception as e:
        logger.warning("点击链接异常: %s", e)
        raise GsxtReportError(f"点击企业链接失败: {e}") from e
    finally:
        context.remove_listener("page", _on_new_page)

    # 新标签页优先
    if new_page and not new_page.is_closed():
        # 详情页 #btn_send_pdf 初始可能不可见，等待加载完成
        try:
            await new_page.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception:
            pass
        return new_page

    # 在 context 中查找详情页
    for p in context.pages:
        try:
            url = p.url
            if not p.is_closed() and "gsxt.gov.cn" in url and "search" not in url and "homepage" not in url:
                logger.info("在 context 中找到详情页: %s", url[:80])
                return p
        except Exception:
            continue

    raise GsxtReportError("详情页未打开，可能被 WAF 拦截")


# ──────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────


def _run_in_thread(credential: GsxtCredentialProtocol, task_id: int) -> None:
    """在独立线程中运行完整流程。"""
    asyncio.run(_run_full_flow(credential, task_id))


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

    # 逆向登录成功，更新状态并启动报告流程
    credential.last_login_success_at = timezone.now()
    credential.save(update_fields=["last_login_success_at"])

    task = GsxtReportTask.objects.get(pk=task_id)
    task.status = GsxtReportStatus.PENDING
    task.save(update_fields=["status"])
    logger.info("逆向登录成功，task_id=%d", task_id)

    # 逆向登录不需要浏览器，但报告流程需要，所以仍需启动 Chrome
    from apps.automation.services.gsxt.gsxt_report_service import start_report_flow

    start_report_flow(task_id)
    return True


def start_login_gsxt(credential: GsxtCredentialProtocol, task_id: int) -> None:
    """
    非阻塞入口：优先尝试 HTTP 逆向登录，失败则启动完整 Playwright 流程。

    Raises:
        GsxtLoginError: Chrome 启动失败（仅 Playwright 模式）。
    """
    # 优先尝试逆向登录（无需浏览器）
    if _try_reverse_login(credential, task_id):
        return

    # 回退到 Playwright 模式：手动启动 Chrome + CDP 导航 + connect_over_cdp 接管
    _ensure_chrome_running()
    t = threading.Thread(target=_run_in_thread, args=(credential, task_id), daemon=True)
    t.start()
    logger.info("GSXT 全流程后台线程已启动，task_id=%d", task_id)
