"""
广东电子送达 (sd.gdems.com) 文书下载爬虫

特点:
- 先进入封面页
- 需要点击"确认并预览材料"按钮
- 下载压缩包并自动解压
"""

from __future__ import annotations

import logging
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
    """

    def run(self) -> dict[str, Any]:
        """
        执行文书下载任务

        Returns:
            下载结果字典
        """
        logger.info("=" * 60)
        logger.info("处理 sd.gdems.com 链接...")
        logger.info("=" * 60)

        # 导航到目标页面
        self.navigate_to_url()

        # 等待页面加载
        self.page.wait_for_load_state("networkidle", timeout=30000)
        self.random_wait(3, 5)  # type: ignore[attr-defined]

        # 截图保存封面页
        screenshot_cover = self.screenshot("gdems_cover")

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
                loc = self.page.locator(selector)
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
                    btn = self.page.get_by_text("确认并预览材料", exact=False)
                    if btn.count() > 0 and btn.first.is_visible():
                        submit_button = btn
                        logger.info("通过文本找到确认按钮")
                except Exception:
                    pass

            if submit_button and submit_button.count() > 0:
                submit_button.first.click()
                logger.info("已点击'确认并预览材料'按钮")
                self.page.wait_for_load_state("networkidle", timeout=30000)
                self.random_wait(5, 7)  # type: ignore[attr-defined]
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
            self.random_wait(1, 2)  # type: ignore[attr-defined]

            with self.page.expect_download(timeout=60000) as download_info:
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
                zip_ref.extractall(extract_dir)
                extracted_files: list[Any] = []  # type: ignore[no-redef]
            logger.info(f"ZIP 文件已解压,共 {len(extracted_files)} 个文件")

        except Exception as e:
            logger.error(f"解压失败: {e}")
            # 解压失败不影响主流程,返回空列表
            extracted_files: list[Any] = []  # type: ignore[no-redef]
        return extracted_files
