"""国家企业信用信息公示系统报告申请服务（登录后：搜索→详情→申请报告）。"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger("apps.automation")

GSXT_SEARCH_URL = "https://shiming.gsxt.gov.cn/corp-query-homepage.html"
CAPTCHA_TIMEOUT = 180  # 等待用户手动完成验证码（秒）
SEARCH_TIMEOUT = 60    # 等待搜索结果（秒）


class GsxtReportError(Exception):
    """报告申请失败异常。"""


# ──────────────────────────────────────────────
# 内部辅助：等待极验验证码完成
# ──────────────────────────────────────────────

async def _wait_captcha_success(page: Page, captcha_selector: str, timeout: int = CAPTCHA_TIMEOUT) -> bool:
    """
    轮询等待极验验证码完成（class 包含 geetest_lock_success）。
    返回 True 表示成功，False 表示超时。
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(2)
        done = await page.evaluate(f"""(() => {{
            const el = document.querySelector('{captcha_selector}');
            return el ? el.className.includes('geetest_lock_success') : false;
        }})()""")
        if done:
            return True
    return False


# ──────────────────────────────────────────────
# Step 1: 搜索企业
# ──────────────────────────────────────────────

async def search_company(page: Page, company_name: str) -> None:
    """
    进入搜索页，填入企业名称，等待用户完成极验验证码，等待搜索结果页加载。
    搜索结果页 URL 包含 corp-query-search-1.html。
    """
    await page.goto(GSXT_SEARCH_URL, timeout=30000, wait_until="domcontentloaded")
    await asyncio.sleep(2)

    # 填入搜索词
    await page.fill("#keyword", company_name)
    await asyncio.sleep(0.5)
    await page.click("#btn_query")  # 点击搜索按钮，触发极验

    logger.info("已点击搜索，等待用户完成验证码...")

    # 等待搜索结果页（URL 变化）
    deadline = asyncio.get_event_loop().time() + CAPTCHA_TIMEOUT
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(2)
        if "corp-query-search-1" in page.url:
            logger.info("搜索结果页已加载: %s", page.url)
            return

    raise GsxtReportError(f"等待搜索结果超时（{CAPTCHA_TIMEOUT}秒），企业：{company_name}")


# ──────────────────────────────────────────────
# Step 2: 点击企业详情
# ──────────────────────────────────────────────

async def click_company_detail(page: Page, company_name: str) -> str:
    """
    在搜索结果页找到匹配企业名称的链接并点击，等待详情页加载。
    返回详情页 URL。
    """
    await asyncio.sleep(2)

    # 找到精确匹配或包含公司名的第一个链接
    href = await page.evaluate(f"""(() => {{
        const links = Array.from(document.querySelectorAll('a'));
        const match = links.find(a => a.innerText && a.innerText.trim() === '{company_name}');
        if (match) return match.href;
        // 模糊匹配
        const fuzzy = links.find(a => a.innerText && a.innerText.includes('{company_name}'));
        return fuzzy ? fuzzy.href : null;
    }})()""")

    if not href:
        raise GsxtReportError(f"搜索结果中未找到企业：{company_name}")

    logger.info("找到企业链接，跳转详情页: %s", href)
    await page.goto(href, timeout=30000, wait_until="domcontentloaded")
    # 等待详情页核心内容加载完成
    await page.wait_for_selector("#btn_send_pdf", timeout=30000)

    return page.url


# ──────────────────────────────────────────────
# Step 3: 申请发送报告
# ──────────────────────────────────────────────

async def request_report(page: Page) -> None:
    """
    在详情页点击"发送报告"按钮，等待用户完成极验验证码，
    然后点击弹窗中的"发送"按钮，等待 alert 确认。
    """
    # 等待按钮出现（页面 JS 动态渲染，domcontentloaded 后还需要时间）
    await page.wait_for_selector("#btn_send_pdf", timeout=30000)
    await page.click("#btn_send_pdf")
    logger.info("已点击发送报告，等待用户完成验证码...")

    # 等待极验完成（绑定在 btn_send_pdf 上的极验，class 含 geetest_lock_success）
    done = await _wait_captcha_success(
        page,
        ".geetest_captcha.geetest_bind.geetest_lock_success",
        timeout=CAPTCHA_TIMEOUT,
    )
    if not done:
        raise GsxtReportError(f"等待发送报告验证码超时（{CAPTCHA_TIMEOUT}秒）")

    logger.info("验证码完成，点击弹窗发送按钮...")

    # 等待弹窗出现
    await page.wait_for_selector("#send_pdf_dialog", state="visible", timeout=10000)

    # 点击弹窗内"发送" div（onclick="sendPdf()"）
    await page.click("#send_pdf_dialog div[onclick*='sendPdf']")

    # 等待 alert 弹出（sendPdf 成功后调用 alert(result)）
    try:
        dialog_msg = ""
        async def handle_dialog(dialog: object) -> None:  # type: ignore[type-arg]
            nonlocal dialog_msg
            dialog_msg = getattr(dialog, "message", "")
            await dialog.accept()  # type: ignore[attr-defined]

        page.on("dialog", handle_dialog)
        await asyncio.sleep(5)
        page.remove_listener("dialog", handle_dialog)

        logger.info("发送报告结果: %s", dialog_msg)
        if dialog_msg and ("失败" in dialog_msg or "error" in dialog_msg.lower()):
            raise GsxtReportError(f"发送报告失败：{dialog_msg}")

    except Exception as e:
        if isinstance(e, GsxtReportError):
            raise
        logger.warning("等待 alert 异常（可能已成功）: %s", e)


# ──────────────────────────────────────────────
# 完整流程串联
# ──────────────────────────────────────────────

async def _run_full_flow(task_id: int) -> None:
    """登录后执行：搜索→详情→申请报告，全程等待用户手动打验证码。"""
    from apps.automation.models.gsxt_report import GsxtReportStatus, GsxtReportTask
    from asgiref.sync import sync_to_async
    from playwright.async_api import async_playwright

    get_task = sync_to_async(GsxtReportTask.objects.select_related("client").get)

    def _save(t: GsxtReportTask, fields: list[str]) -> None:
        t.save(update_fields=fields)

    save_task = sync_to_async(_save)

    task = await get_task(pk=task_id)
    company_name: str = task.company_name

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = await context.new_page()

        try:
            task.status = GsxtReportStatus.WAITING_CAPTCHA
            task.error_message = f"正在搜索：{company_name}，请完成验证码"
            await save_task(task, ["status", "error_message"])

            await search_company(page, company_name)

            task.error_message = "已找到搜索结果，正在进入详情页"
            await save_task(task, ["error_message"])

            await click_company_detail(page, company_name)

            task.error_message = "已进入详情页，请完成发送报告验证码"
            await save_task(task, ["error_message"])

            await request_report(page)

            task.status = GsxtReportStatus.WAITING_EMAIL
            task.error_message = "报告已发送到邮箱，正在自动轮询收取…"
            await save_task(task, ["status", "error_message"])
            logger.info("任务 %d：报告申请成功，启动邮件轮询", task_id)

            # 60 秒后开始轮询邮箱
            from datetime import timedelta

            from asgiref.sync import sync_to_async
            from django.utils import timezone
            from django_q.models import Schedule

            def _schedule_email_check() -> None:
                Schedule.objects.create(
                    func="apps.automation.tasks.gsxt_tasks.check_gsxt_report_email",
                    args=f"{task_id},{repr(task.company_name)}",
                    schedule_type=Schedule.ONCE,
                    next_run=timezone.now() + timedelta(seconds=60),
                    name=f"gsxt_email_first_{task_id}",
                )

            await sync_to_async(_schedule_email_check)()

        except Exception as e:
            task.status = GsxtReportStatus.FAILED
            task.error_message = str(e)
            await save_task(task, ["status", "error_message"])
            logger.exception("任务 %d 失败: %s", task_id, e)

        finally:
            await page.close()


def start_report_flow(task_id: int) -> None:
    """非阻塞入口：在后台线程运行完整报告申请流程。"""
    def _run() -> None:
        asyncio.run(_run_full_flow(task_id))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    logger.info("报告申请后台线程已启动，task_id=%d", task_id)
