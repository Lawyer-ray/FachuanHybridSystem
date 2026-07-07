"""金诚同达 OA 归档材料提交 — Playwright 自动化全流程。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from playwright.async_api import Page

from apps.core.services.browser import BrowserProfile, create_browser_async

from ..auth.service import JtnAuthService
from .archive_models import ArchiveFormData
from .constants import (
    _POPUP_IFRAME_KEYWORD,
    AJAX_WAIT,
    ARCHIVE_PAGE_URL,
    DESCRIPTION_SELECTOR,
    IFRAME_PROJECT_NO_SELECTOR,
    IFRAME_SEARCH_FN,
    MEDIUM_WAIT,
    POPUP_WAIT,
    SAVE_BTN_ID,
    SHORT_WAIT,
)

logger = logging.getLogger("apps.oa_filing.jtn_archive")

_HEADED_PROFILE = BrowserProfile(
    name="jtn_archive",
    headless=False,
    anti_detection=True,
    timeout=60_000,
    navigation_timeout=60_000,
)


class PlaywrightArchiveMixin:  # pragma: no cover
    """Playwright 归档材料提交全流程 mixin。"""

    _account: str
    _password: str
    _auth: JtnAuthService

    async def _run_archive_submission(self: Any, form_data: ArchiveFormData) -> None:
        """归档材料提交 Playwright 全流程。"""
        async with create_browser_async(_HEADED_PROFILE) as (page, context):
            # 1. 登录
            await self._login(page, context)

            # 2. 导航到归档页面
            await self._navigate(page)

            # 3. 搜索并选择案件
            await self._search_and_select_case(page, form_data.oa_case_number)

            # 4. 填写案件小结
            await self._fill_description(page, form_data.description)

            # 5. 上传归档文件
            await self._upload_files(page, form_data.file_paths)

            # 6. 保存
            await self._save(page)

            logger.info("归档材料提交完成")

    async def _login(self: Any, page: Page, context: Any) -> None:  # pragma: no cover
        """登录 OA：优先缓存 cookies，否则 SSO 扫码。"""
        cached = JtnAuthService.load_cookies()
        if cached:
            logger.info("使用缓存 cookies 登录归档页面")
            await JtnAuthService.inject_to_context(context, cached)
            await page.goto(ARCHIVE_PAGE_URL, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(MEDIUM_WAIT)
            if "login" not in page.url.lower():
                logger.info("Cookies 有效，已进入归档页面")
                return
            logger.warning("缓存 cookies 已失效，执行 SSO 扫码登录")

        cookies = await self._auth.sso_login()
        await JtnAuthService.inject_to_context(context, cookies)

    async def _navigate(self: Any, page: Page) -> None:  # pragma: no cover
        """导航到结案归档管理 - 结案申请页面。"""
        logger.info("导航到归档页面: %s", ARCHIVE_PAGE_URL)
        await page.goto(ARCHIVE_PAGE_URL, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(MEDIUM_WAIT)

        if "login" in page.url.lower():
            logger.warning("当前在登录页，等待 SSO 扫码...")
            await page.wait_for_url("**/ims.jtn.com/projclose/**", timeout=180_000)
            await asyncio.sleep(MEDIUM_WAIT)

        logger.info("已进入归档页面: %s", page.url)

    async def _search_and_select_case(self: Any, page: Page, case_no: str) -> None:  # pragma: no cover
        """搜索案件并选择（与盖章共用搜索弹窗模式）。"""
        logger.info("搜索案件: %s", case_no)

        # 1. 通过 JS 点击"案件编号"行的搜索图标打开弹窗
        await page.evaluate("""() => {
            const tds = document.querySelectorAll('td');
            for (const td of tds) {
                if (td.textContent.trim().startsWith('案件编号')) {
                    const row = td.closest('tr');
                    if (row) { const img = row.querySelector('img'); if (img) { img.click(); return; } }
                }
            }
        }""")
        await asyncio.sleep(POPUP_WAIT)

        # 2. 找到弹窗 iframe
        popup_frame = await self._find_popup_frame(page)
        if popup_frame is None:
            raise RuntimeError("未找到案件搜索弹窗 iframe")

        # 3. 在 iframe 中搜索案件
        await popup_frame.evaluate(f"""() => {{
            const el = document.getElementById("project_no");
            el.removeAttribute("readonly");
            el.value = "{case_no}";
        }}""")
        await asyncio.sleep(SHORT_WAIT)

        await popup_frame.evaluate(IFRAME_SEARCH_FN)
        await asyncio.sleep(AJAX_WAIT)

        # 4. 选择第一个结果
        radio_count = await popup_frame.locator('input[type="radio"]').count()
        if radio_count == 0:
            raise RuntimeError(f"未找到案件: {case_no}")

        await popup_frame.evaluate('document.querySelectorAll("input[type=radio]")[0].click()')
        await asyncio.sleep(SHORT_WAIT)
        logger.info("已选择案件: %s", case_no)

        # 5. 点击 layui 层的"选择"按钮
        await page.evaluate("""() => {
            const layers = document.querySelectorAll(".layui-layer");
            for (const layer of layers) {
                for (const a of layer.querySelectorAll("a")) {
                    if (a.innerText.trim() === "选择") { a.click(); return; }
                }
            }
        }""")
        await asyncio.sleep(POPUP_WAIT)
        logger.info("案件已回填到主页面")

    async def _find_popup_frame(self: Any, page: Page) -> Any:  # pragma: no cover
        """查找案件搜索弹窗的 iframe。"""
        for frame in page.frames:
            if _POPUP_IFRAME_KEYWORD in frame.url:
                return frame
        return None

    async def _fill_description(self: Any, page: Page, description: str) -> None:  # pragma: no cover
        """填写案件小结（readonly textarea，需 JS 去除 readonly）。"""
        logger.info("填写案件小结: %s", description)
        result = await page.evaluate(f"""() => {{
            const ta = document.querySelector('{DESCRIPTION_SELECTOR}');
            if (!ta) return 'textarea not found';
            ta.readOnly = false;
            ta.removeAttribute('readonly');
            ta.value = '{description}';
            ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
            ta.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return 'ok';
        }}""")
        if result != "ok":
            raise RuntimeError(f"填写案件小结失败: {result}")
        await asyncio.sleep(SHORT_WAIT)

    async def _upload_files(self: Any, page: Page, file_paths: list[str]) -> None:  # pragma: no cover
        """上传归档文件到归档文件区域。

        归档文件区域在 #tblFiles 表格中：
        - 第一行（案件业务卷宗）：默认选中，name="pfile"
        - 第二行（请选择）：附加文件类型，name="pfile"

        注意：页面顶层有一个隐藏的 file input（display:none），
        必须用 #tblFiles input[type=file] 限定范围，跳过隐藏的。
        """
        if not file_paths:
            raise RuntimeError("没有要上传的文件")

        # 限定在 #tblFiles 表格中，避免匹配到页面顶层的隐藏 file input
        file_inputs = page.locator('#tblFiles input[type="file"]')
        fi_count = await file_inputs.count()
        if fi_count < 1:
            raise RuntimeError("未找到归档文件上传区域 (#tblFiles)")

        # 上传第一个文件到"案件业务卷宗"行
        first_path = file_paths[0]
        logger.info("上传文件: %s → 案件业务卷宗", Path(first_path).name)
        await file_inputs.first.set_input_files(first_path)
        await asyncio.sleep(MEDIUM_WAIT)

        # 如果有多个文件，通过"请选择"行上传第二个文件
        if len(file_paths) > 1 and fi_count >= 2:
            second_path = file_paths[1]
            logger.info("上传文件: %s → 请选择行", Path(second_path).name)
            await file_inputs.nth(1).set_input_files(second_path)
            await asyncio.sleep(MEDIUM_WAIT)

        # 更多文件需要先点击"增加"按钮添加行（暂不支持，后续扩展）
        if len(file_paths) > 2:
            logger.warning("归档文件超过 2 个时暂不自动添加行，仅上传前 2 个文件")

    async def _save(self: Any, page: Page) -> None:  # pragma: no cover
        """点击保存按钮提交归档申请。"""
        logger.info("保存归档申请...")
        save_btn = page.locator(f"#{SAVE_BTN_ID}")
        await save_btn.first.click()
        await asyncio.sleep(MEDIUM_WAIT)
        logger.info("归档申请已提交")
