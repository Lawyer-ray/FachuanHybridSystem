"""金诚同达 OA 盖章申请 — Playwright 自动化全流程。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from playwright.async_api import Page

from apps.core.services.browser import BrowserProfile, create_browser_async

from ..auth.service import JtnAuthService
from .constants import (
    _POPUP_IFRAME_KEYWORD,
    AJAX_WAIT,
    DEFAULT_STAMP_COPIES,
    FILE_TYPE_SOUHAN,
    IFRAME_PROJECT_NO_SELECTOR,
    IFRAME_SEARCH_FN,
    MEDIUM_WAIT,
    POPUP_WAIT,
    SHORT_WAIT,
    STAMP_PAGE_URL,
    STAMP_TYPE_INDEX_DIANZI,
    STAMP_TYPE_INDEX_GONGZHANG,
    UPLOAD_WAIT,
    XPATH_FILE_TYPE,
    XPATH_SAVE_BTN,
    XPATH_SEARCH_CASE_BTN,
    XPATH_STAMP_COPIES,
)
from .stamp_models import StampFormData

logger = logging.getLogger("apps.oa_filing.jtn_stamp")

# 有头浏览器 Profile（盖章需要用户扫码）
_HEADED_PROFILE = BrowserProfile(
    name="jtn_stamp",
    headless=False,
    anti_detection=True,
    timeout=60_000,
    navigation_timeout=60_000,
)


class PlaywrightStampMixin:  # pragma: no cover
    """Playwright 盖章申请全流程 mixin。"""

    _account: str
    _password: str
    _auth: JtnAuthService

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------

    async def _run_stamp_application(self: Any, form_data: StampFormData) -> None:
        """盖章申请 Playwright 全流程。"""
        async with create_browser_async(_HEADED_PROFILE) as (page, context):
            # 1. 登录
            await self._login_to_stamp(page, context)

            # 2. 导航到盖章页面
            await self._navigate_to_stamp_page(page)

            # 3. 搜索并选择案件
            await self._search_and_select_case(page, form_data.oa_case_number)

            # 4. 填写盖章表单
            await self._fill_stamp_form(page, form_data)

            # 5. 上传文件
            await self._upload_file(page, form_data.file_path)

            # 6. 保存
            await self._save_form(page)

            logger.info("盖章申请完成")

    # ------------------------------------------------------------------
    # 登录
    # ------------------------------------------------------------------

    async def _login_to_stamp(self: Any, page: Page, context: Any) -> None:  # pragma: no cover
        """登录 OA：优先缓存 cookies，否则 SSO 扫码。"""
        cached = JtnAuthService.load_cookies()
        if cached:
            logger.info("使用缓存 cookies 登录盖章页面")
            await JtnAuthService.inject_to_context(context, cached)
            # 验证 cookies 有效性
            await page.goto(STAMP_PAGE_URL, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(MEDIUM_WAIT)
            if "login" not in page.url.lower():
                logger.info("Cookies 有效，已进入盖章页面")
                return
            logger.warning("缓存 cookies 已失效，执行 SSO 扫码登录")

        # SSO 扫码登录（内部会创建 headed browser 等用户扫码）
        cookies = await self._auth.sso_login()
        await JtnAuthService.inject_to_context(context, cookies)

    # ------------------------------------------------------------------
    # 导航
    # ------------------------------------------------------------------

    async def _navigate_to_stamp_page(self: Any, page: Page) -> None:  # pragma: no cover
        """导航到盖章文书管理页面。"""
        logger.info("导航到盖章页面: %s", STAMP_PAGE_URL)
        await page.goto(STAMP_PAGE_URL, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(MEDIUM_WAIT)

        if "login" in page.url.lower():
            logger.warning("当前在登录页，等待 SSO 扫码...")
            await page.wait_for_url("**/ims.jtn.com/projdoc/**", timeout=180_000)
            await asyncio.sleep(MEDIUM_WAIT)

        logger.info("已进入盖章页面: %s", page.url)

    # ------------------------------------------------------------------
    # 搜索并选择案件
    # ------------------------------------------------------------------

    async def _search_and_select_case(self: Any, page: Page, case_no: str) -> None:  # pragma: no cover
        """搜索案件并选择。"""
        logger.info("搜索案件: %s", case_no)

        # 1. 点击搜索按钮打开弹窗
        search_btn = page.locator(XPATH_SEARCH_CASE_BTN)
        await search_btn.first.click()
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

    # ------------------------------------------------------------------
    # 填写盖章表单
    # ------------------------------------------------------------------

    async def _fill_stamp_form(self: Any, page: Page, form_data: StampFormData) -> None:  # pragma: no cover
        """填写盖章表单：文档类型、盖章类型、份数。"""
        # 选择文档类型
        file_type = page.locator(XPATH_FILE_TYPE)
        await file_type.first.select_option(label=form_data.file_type)
        await asyncio.sleep(SHORT_WAIT)
        logger.info("文档类型: %s", form_data.file_type)

        # 勾选盖章类型
        stamp_type_indices = []
        if "公章" in form_data.stamp_types:
            stamp_type_indices.append(STAMP_TYPE_INDEX_GONGZHANG)
        if "电子公章" in form_data.stamp_types:
            stamp_type_indices.append(STAMP_TYPE_INDEX_DIANZI)

        for idx in stamp_type_indices:
            label = page.locator(f'//*[@id="table_file_1"]/tbody/tr/td[2]/ul/li[{idx}]/label')
            await label.first.click()
            await asyncio.sleep(SHORT_WAIT)

        logger.info("盖章类型: %s", ", ".join(form_data.stamp_types))

        # 填写盖章份数
        copies_input = page.locator(XPATH_STAMP_COPIES)
        await copies_input.first.fill(str(form_data.stamp_copies))
        await asyncio.sleep(SHORT_WAIT)
        logger.info("盖章份数: %d", form_data.stamp_copies)

    # ------------------------------------------------------------------
    # 上传文件
    # ------------------------------------------------------------------

    async def _upload_file(self: Any, page: Page, file_path: str) -> None:  # pragma: no cover
        """上传文件到盖章表单。"""
        logger.info("上传文件: %s", Path(file_path).name)

        # 1. 点击"上传文件"按钮
        upload_btn = page.locator('//*[@id="table_file_1"]/tbody/tr/td[5]/button')
        await upload_btn.first.click()
        await asyncio.sleep(POPUP_WAIT)

        # 2. 找到上传 iframe（URL 含 legalup/attachment 或 uptype=uploadfile）
        upload_frame = None
        for frame in page.frames:
            url = frame.url.lower()
            if "legalup" in url or "uploadfile" in url:
                upload_frame = frame
                break

        if upload_frame is None:
            # 回退：按 iframe name 匹配 layui 层弹窗
            for frame in page.frames:
                if "layui-layer-iframe" in (frame.name or ""):
                    upload_frame = frame
                    break

        if upload_frame is None:
            raise RuntimeError("未找到文件上传弹窗 iframe")

        logger.info("上传 iframe: %s", upload_frame.url[:100])

        # 3. 设置文件
        file_input = upload_frame.locator('input[type="file"]')
        await file_input.first.set_input_files(file_path)
        await asyncio.sleep(MEDIUM_WAIT)
        logger.info("文件已选择")

        # 4. 点击"开始上传"
        #    按钮是 <div class="uploadBtn disabled">，set_input_files 后 webuploader
        #    应移除 disabled class，但有时有延迟。先等一下，再 JS 兜底。
        upload_btn = upload_frame.locator(".uploadBtn")
        if await upload_btn.count() > 0:
            await upload_frame.evaluate(
                "() => {"
                "  const btn = document.querySelector('.uploadBtn');"
                "  if (btn) {"
                "    btn.classList.remove('disabled', 'state-pedding');"
                "    btn.click();"
                "  }"
                "}"
            )
            await asyncio.sleep(UPLOAD_WAIT)
            logger.info("文件上传中...")
        else:
            # 极端回退：在 layui 层找
            await page.evaluate(
                "() => {"
                "  const layers = document.querySelectorAll('.layui-layer');"
                "  for (const layer of layers) {"
                "    for (const a of layer.querySelectorAll('a, button, span, div')) {"
                "      if (a.innerText && a.innerText.trim() === '开始上传') { a.click(); return; }"
                "    }"
                "  }"
                "}"
            )
            await asyncio.sleep(UPLOAD_WAIT)
            logger.info("文件上传中...（通过 layui 层）")

        # 5. 点击"确定"关闭上传弹窗
        await page.evaluate(
            "() => {"
            "  const layers = document.querySelectorAll('.layui-layer');"
            "  for (const layer of layers) {"
            "    for (const a of layer.querySelectorAll('a, button, span')) {"
            "      if (a.innerText && a.innerText.trim() === '确定') { a.click(); return; }"
            "    }"
            "  }"
            "}"
        )
        await asyncio.sleep(POPUP_WAIT)
        logger.info("文件上传完成")

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------

    async def _save_form(self: Any, page: Page) -> None:  # pragma: no cover
        """点击保存按钮提交盖章申请。"""
        logger.info("保存盖章申请...")
        save_btn = page.locator(XPATH_SAVE_BTN)
        await save_btn.first.click()
        await asyncio.sleep(MEDIUM_WAIT)
        logger.info("盖章申请已提交")
