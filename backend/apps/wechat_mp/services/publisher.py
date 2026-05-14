"""公众号文章发布服务（Playwright 自动化）"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from apps.core.services.browser import create_browser

from .auth_handler import capture_qr_code, check_login_status, load_cookies, save_cookies, wait_for_qr_scan
from .markdown_converter import convert_markdown_to_wechat_html

if TYPE_CHECKING:
    from apps.wechat_mp.models import PublishTask

logger = logging.getLogger(__name__)

# 公众号后台 URL
MP_HOME_URL = "https://mp.weixin.qq.com"
MP_NEW_ARTICLE_URL = "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77"


class PublishError(Exception):
    """发布异常"""


class WeChatPublisher:
    """公众号文章发布器"""

    def __init__(self, task: PublishTask) -> None:
        self.task = task
        self.account_id = task.account_id
        self.account_name = task.account.name

    def publish(self) -> dict:
        """执行发布流程。

        Returns:
            包含发布结果的字典

        Raises:
            PublishError: 发布失败时抛出
        """
        try:
            with create_browser(
                headless=False,  # 公众号后台需要有头模式（首次扫码）
                slow_mo=500,
                viewport={"width": 1280, "height": 800},
            ) as (page, context):
                return self._execute_publish(page, context)
        except PublishError:
            raise
        except Exception as e:
            logger.error("Publish failed for task %d: %s", self.task.pk, e, exc_info=True)
            raise PublishError(f"发布失败: {e}") from e

    def _execute_publish(self, page: Any, context: Any) -> dict:
        """在浏览器上下文中执行发布流程。"""
        # Step 1: 加载 Cookie 并检查登录状态
        self._update_status("logging_in")

        has_cookies = load_cookies(context, self.account_id)
        page.goto(MP_HOME_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        if not check_login_status(page):
            if has_cookies:
                logger.info("Cookies expired for account %d, waiting for QR scan", self.account_id)

            # 需要扫码登录
            qr_image = capture_qr_code(page)
            if qr_image:
                # 保存二维码截图供前端展示
                qr_path = Path(f"/tmp/wechat_qr_{self.account_id}.png")
                qr_path.write_bytes(qr_image)
                logger.info("QR code saved to %s", qr_path)

            # 等待扫码
            if not wait_for_qr_scan(page, timeout_seconds=120):
                raise PublishError("扫码登录超时，请重试")

            # 登录成功，保存 Cookie
            save_cookies(context, self.account_id)

        logger.info("Account %s logged in successfully", self.account_name)

        # Step 2: 进入新建图文页面
        self._update_status("editing")
        self._navigate_to_new_article(page)

        # Step 3: 填写标题
        self._fill_title(page, self.task.title)

        # Step 4: 注入内容到编辑器
        html_content = convert_markdown_to_wechat_html(self.task.content_md)
        self._inject_content(page, html_content)

        # Step 5: 上传封面图（如有）
        if self.task.cover_image:
            self._upload_cover(page, self.task.cover_image.path)

        # Step 6: 保存草稿或发布
        self._update_status("publishing")

        if self.task.save_as_draft:
            result = self._save_draft(page)
        else:
            result = self._publish_article(page)

        # 更新 Cookie
        save_cookies(context, self.account_id)

        return result

    def _navigate_to_new_article(self, page: Any) -> None:
        """导航到新建图文页面。"""
        try:
            # 点击"新的创作"按钮
            new_creation_btn = page.locator("text=新的创作").first
            new_creation_btn.click(timeout=10000)
            time.sleep(1)

            # 点击"图文消息"
            article_btn = page.locator("text=图文消息").first
            article_btn.click(timeout=10000)

            # 等待编辑器加载
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            time.sleep(3)

            # 如果打开了新窗口，切换到新窗口
            if len(page.context.pages) > 1:
                new_page = page.context.pages[-1]
                new_page.wait_for_load_state("domcontentloaded", timeout=30000)
                # 更新 page 引用（注意：这里需要返回新页面）
                logger.info("Switched to new article editor window")
        except Exception as e:
            raise PublishError(f"无法打开新建图文页面: {e}") from e

    def _fill_title(self, page: Any, title: str) -> None:
        """填写文章标题。"""
        try:
            # 公众号编辑器的标题输入框
            title_selectors = [
                "#title",
                "textarea[placeholder*='标题']",
                ".title_input textarea",
                "input[placeholder*='标题']",
            ]

            for selector in title_selectors:
                title_input = page.query_selector(selector)
                if title_input:
                    title_input.click()
                    title_input.fill(title)
                    logger.info("Title filled: %s", title)
                    return

            raise PublishError("找不到标题输入框")
        except PublishError:
            raise
        except Exception as e:
            raise PublishError(f"填写标题失败: {e}") from e

    def _inject_content(self, page: Any, html_content: str) -> None:
        """将 HTML 内容注入到编辑器。"""
        try:
            # 公众号编辑器使用 contenteditable div
            editor_selectors = [
                ".ql-editor",
                "#ueditor_0",
                ".ProseMirror",
                "[contenteditable='true']",
            ]

            for selector in editor_selectors:
                editor = page.query_selector(selector)
                if editor:
                    # 使用 JavaScript 注入内容
                    page.evaluate(
                        """(args) => {
                            const [selector, html] = args;
                            const editor = document.querySelector(selector);
                            if (editor) {
                                editor.innerHTML = html;
                                // 触发 input 事件让编辑器识别内容变化
                                editor.dispatchEvent(new Event('input', { bubbles: true }));
                                editor.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        }""",
                        [selector, html_content],
                    )
                    logger.info("Content injected into editor: %s", selector)
                    time.sleep(2)
                    return

            raise PublishError("找不到编辑器")
        except PublishError:
            raise
        except Exception as e:
            raise PublishError(f"注入内容失败: {e}") from e

    def _upload_cover(self, page: Any, cover_path: str) -> None:
        """上传封面图。"""
        try:
            # 查找封面图上传区域
            cover_selectors = [
                "text=选择封面",
                "text=上传封面",
                ".js_cover_area",
                "[data-type='cover']",
            ]

            for selector in cover_selectors:
                cover_btn = page.query_selector(selector)
                if cover_btn:
                    cover_btn.click()
                    time.sleep(1)

                    # 查找文件上传输入
                    file_input = page.query_selector("input[type='file']")
                    if file_input:
                        file_input.set_input_files(cover_path)
                        logger.info("Cover image uploaded: %s", cover_path)
                        time.sleep(3)
                        return

            logger.warning("Cover upload button not found, skipping")
        except Exception:
            logger.warning("Failed to upload cover image", exc_info=True)

    def _save_draft(self, page: Any) -> dict:
        """保存为草稿。"""
        try:
            draft_selectors = [
                "text=保存为草稿",
                "text=保存草稿",
                "button:has-text('保存')",
            ]

            for selector in draft_selectors:
                draft_btn = page.query_selector(selector)
                if draft_btn:
                    draft_btn.click()
                    time.sleep(3)

                    # 检查是否保存成功
                    success_indicator = page.query_selector("text=保存成功, text=已保存")
                    if success_indicator:
                        logger.info("Draft saved successfully")
                        return {"status": "draft_saved", "message": "草稿保存成功"}

                    return {"status": "draft_saved", "message": "草稿已保存（未检测到成功提示）"}

            raise PublishError("找不到保存草稿按钮")
        except PublishError:
            raise
        except Exception as e:
            raise PublishError(f"保存草稿失败: {e}") from e

    def _publish_article(self, page: Any) -> dict:
        """直接发布文章。"""
        try:
            publish_selectors = [
                "text=群发",
                "text=发布",
                "button:has-text('群发')",
            ]

            for selector in publish_selectors:
                publish_btn = page.query_selector(selector)
                if publish_btn:
                    publish_btn.click()
                    time.sleep(2)

                    # 可能需要确认对话框
                    confirm_btn = page.query_selector("text=确定, text=确认发布, text=继续群发")
                    if confirm_btn:
                        confirm_btn.click()
                        time.sleep(3)

                    logger.info("Article published")
                    return {"status": "published", "message": "文章已发布"}

            raise PublishError("找不到发布按钮")
        except PublishError:
            raise
        except Exception as e:
            raise PublishError(f"发布失败: {e}") from e

    def _update_status(self, status: str) -> None:
        """更新任务状态。"""
        from django.utils import timezone

        self.task.status = status
        if status == "logging_in":
            self.task.started_at = timezone.now()
        self.task.save(update_fields=["status", "started_at", "updated_at"])
        logger.info("Task %d status updated to: %s", self.task.pk, status)
