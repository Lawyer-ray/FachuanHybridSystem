"""
广东电子送达 (sd.gdems.com) 文书下载爬虫

特点:
- 先进入封面页
- 需要点击"确认并预览材料"按钮
- 下载压缩包并自动解压
- 支持无文书可下载的情况（书记员未放置文件时，确定按钮无绑定事件）
"""

from __future__ import annotations

import logging
import random
import time
import zipfile
from pathlib import Path
from typing import Any

from .base_court_scraper import BaseCourtDocumentScraper

logger = logging.getLogger("apps.automation")


class GdemsCourtScraper(BaseCourtDocumentScraper):
    """
    广东电子送达 (sd.gdems.com) 文书下载爬虫

    特点:
    - 两步流程:确认预览 → 下载压缩包
    - 自动解压 ZIP 文件
    - 支持多种按钮定位策略
    - 检测无文书可下载的情况并返回通知内容
    """

    # 页面两种状态的判断依据:
    # - 有文书可下载: 页面存在 #submit-btn (绑定点击事件的确认按钮)
    # - 无文书可下载: 页面只有 div.login-button (无点击事件绑定的"确定"按钮)
    #   此时书记员尚未放置文件，点击"确定"不会跳转到预览/下载页

    def run(self) -> dict[str, Any]:
        """
        执行文书下载任务

        Returns:
            下载结果字典
        """
        logger.info("=" * 60)
        logger.info("处理 sd.gdems.com 链接...")
        logger.info("=" * 60)

        # 导航到目标页面（使用更长超时，该网站响应较慢）
        self.navigate_to_url(timeout=60000)

        # 等待页面加载
        self.page.wait_for_load_state("networkidle", timeout=30000)  # type: ignore
        self._random_wait(3, 5)

        # 截图保存封面页
        screenshot_cover = self.screenshot("gdems_cover")

        # 检测页面状态：是否存在可点击的确认按钮
        if not self._has_clickable_confirm_button():
            logger.warning("页面无可点击的确认按钮（#submit-btn），书记员可能未放置文书文件")
            return self._build_no_document_result(screenshot_cover)

        # 点击"确认并预览材料"按钮
        self._click_confirm_button()

        # 截图保存预览页
        screenshot_preview = self.screenshot("gdems_preview")

        # 准备下载目录
        download_dir = self._prepare_download_dir()

        # 下载压缩包
        zip_filepath = self._download_zip_file(download_dir)

        # 解压 ZIP 文件
        extracted_files = self._extract_zip_file(zip_filepath, download_dir)

        # 构建文件列表(用于结果显示)
        all_files: list[str] = []

        return {
            "source": "sd.gdems.com",
            "zip_file": str(zip_filepath),
            "extracted_files": extracted_files,
            "files": all_files,  # 添加 files 字段,与 zxfw 保持一致
            "file_count": len(extracted_files),
            "screenshots": [screenshot_cover, screenshot_preview],
            "message": f"成功下载并解压 {len(extracted_files)} 个文件",
        }

    def _has_clickable_confirm_button(self) -> bool:
        """
        检测页面是否存在可点击的确认按钮

        有文书可下载时，页面会渲染 #submit-btn 元素（绑定验证码提交事件）。
        无文书可下载时，页面只有 div.login-button "确定"按钮，但该按钮
        没有绑定任何点击事件，点击后不会跳转。

        Returns:
            True 表示存在可点击的确认按钮（有文书），False 表示无
        """
        # 检查 #submit-btn（有文书时绑定事件的按钮）
        submit_btn = self.page.locator("#submit-btn")  # type: ignore
        if submit_btn.count() > 0 and submit_btn.first.is_visible():
            logger.info("检测到 #submit-btn 确认按钮，页面有文书可下载")
            return True

        logger.info("未检测到 #submit-btn 确认按钮，页面可能无文书可下载")
        return False

    def _extract_canvas_notification(self) -> str:
        """
        提取 canvas 上绘制的通知文本

        页面 JS 在 $(document).ready 中将通知文字绘制到 canvas 上，
        我们从 JS 变量中提取原始文本（而非 OCR canvas 像素）。

        Returns:
            canvas 上显示的通知文本，提取失败返回空字符串
        """
        try:
            text = self.page.evaluate("""() => {
                // 页面 JS 在 $(document).ready 中定义 var text = "..." 并绘制到 canvas
                // 从内联 script 中提取该变量值
                var scripts = document.querySelectorAll('script:not([src])');
                for (var s of scripts) {
                    var content = s.textContent;
                    var match = content.match(/var\\s+text\\s*=\\s*"((?:[^"\\\\]|\\\\.)*)"/);
                    if (match) {
                        // 使用 JSON.parse 正确处理转义序列（\\n → 换行等）
                        try {
                            return JSON.parse('"' + match[1] + '"');
                        } catch(e) {
                            return match[1]
                                .replace(/\\\\n/g, '\\n')
                                .replace(/\\\\t/g, '\\t')
                                .replace(/\\\\"/g, '"');
                        }
                    }
                }
                return '';
            }""")  # type: ignore[union-attr]
            if text:
                logger.info("已提取 canvas 通知文本，长度: %d", len(text))
            return text or ""
        except Exception as e:
            logger.warning(f"提取 canvas 通知文本失败: {e}")
            return ""

    def _build_no_document_result(self, screenshot_cover: str) -> dict[str, Any]:
        """
        构建无文书可下载时的返回结果

        Args:
            screenshot_cover: 封面页截图路径

        Returns:
            包含通知内容的结果字典
        """
        # 提取页面上的通知内容
        notification_text = self._extract_canvas_notification()
        if notification_text:
            preview_text = notification_text[:200] + ("..." if len(notification_text) > 200 else "")
            logger.info(f"通知内容摘要: {preview_text}")

        # 保存页面状态用于调试
        self._save_page_state("gdems_no_document")

        return {
            "source": "sd.gdems.com",
            "zip_file": "",
            "extracted_files": [],
            "files": [],
            "file_count": 0,
            "screenshots": [screenshot_cover],
            "notification_text": notification_text,
            "message": "书记员尚未放置文书文件，确定按钮无法点击，无文书可下载",
        }

    def _random_wait(self, min_s: float, max_s: float) -> None:
        """随机等待，模拟人工操作间隔"""
        time.sleep(random.uniform(min_s, max_s))

    def _find_locator(self, selectors: list[str], label: str) -> Any | None:
        """
        按顺序尝试多个选择器，返回第一个可见的定位器

        Args:
            selectors: 选择器列表
            label: 用于日志的描述

        Returns:
            找到的定位器，或 None
        """
        for selector in selectors:
            try:
                loc = self.page.locator(selector)  # type: ignore
                if loc.count() > 0 and loc.first.is_visible():
                    logger.info(f"通过 '{selector}' 找到 {label}")
                    return loc
            except Exception:
                pass
        return None

    def _click_confirm_button(self) -> None:
        """点击"确认并预览材料"按钮，尝试多种定位策略"""
        try:
            selectors = [
                "#submit-btn, #confirm-btn, .submit-btn, .confirm-btn",
                "button:has-text('确认'), button:has-text('确定'), button:has-text('预览')",
            ]
            submit_button = self._find_locator(selectors, "确认按钮")

            # 文本定位器单独处理（get_by_text 接口不同）
            if not submit_button:
                try:
                    btn = self.page.get_by_text("确认并预览材料", exact=False)  # type: ignore
                    if btn.count() > 0 and btn.first.is_visible():
                        submit_button = btn
                        logger.info("通过文本找到确认按钮")
                except Exception:
                    pass

            if submit_button and submit_button.count() > 0:
                submit_button.first.click()
                logger.info("已点击'确认并预览材料'按钮")
                self.page.wait_for_load_state("networkidle", timeout=30000)  # type: ignore
                self._random_wait(5, 7)
            else:
                logger.warning("未找到确认按钮，可能页面已经在预览状态")
        except Exception as e:
            logger.warning(f"点击确认按钮时出错: {e}，继续尝试下载")

    def _download_zip_file(self, download_dir: Path) -> Path:
        """
        下载压缩包文件

        Args:
            download_dir: 下载目录

        Returns:
            ZIP 文件路径

        Raises:
            ValueError: 下载失败时抛出异常
        """
        download_xpath = "/html/body/div/div[1]/div[1]/label/a/img"
        selectors = [
            "a.downloadPackClass",
            f"xpath={download_xpath}",
            "label a:has(img)",
            "a:has-text('送达材料')",
            "a:has-text('下载'), button:has-text('下载'), [title*='下载']",
        ]

        try:
            download_button = self._find_locator(selectors, "下载按钮")

            if not download_button or download_button.count() == 0:
                self._save_page_state("gdems_no_download_button")
                raise ValueError("找不到下载按钮")

            download_button.first.scroll_into_view_if_needed()
            self._random_wait(1, 2)

            with self.page.expect_download(timeout=60000) as download_info:  # type: ignore
                download_button.first.click()
                logger.info("已点击下载按钮，等待下载...")

            download = download_info.value
            zip_filename = download.suggested_filename or "documents.zip"
            zip_filepath = download_dir / zip_filename
            download.save_as(str(zip_filepath))
            logger.info(f"ZIP 文件已保存: {zip_filepath}")
            return zip_filepath

        except Exception as e:
            logger.error(f"下载失败: {e}")
            self._save_page_state("gdems_download_error")
            raise ValueError(f"文件下载失败: {e}") from e

    def _extract_zip_file(self, zip_filepath: Path, download_dir: Path) -> list[str]:
        """
        解压 ZIP 文件

        Args:
            zip_filepath: ZIP 文件路径
            download_dir: 下载目录

        Returns:
            解压后的文件路径列表
        """
        extracted_files: list[str] = []

        try:
            extract_dir = download_dir / "extracted"
            extract_dir.mkdir(exist_ok=True)

            with zipfile.ZipFile(zip_filepath, "r") as zip_ref:
                for member in zip_ref.infolist():
                    target = (extract_dir / member.filename).resolve()
                    if not str(target).startswith(str(extract_dir.resolve())):
                        logger.warning(f"跳过不安全的 ZIP 条目: {member.filename}")
                        continue
                    zip_ref.extract(member, extract_dir)
                    if not member.is_dir():
                        extracted_files.append(str(target))
            logger.info(f"ZIP 文件已解压,共 {len(extracted_files)} 个文件")

        except Exception as e:
            logger.error(f"解压失败: {e}")
            # 解压失败不影响主流程,返回空列表
            extracted_files: list[Any] = []  # type: ignore
        return extracted_files
