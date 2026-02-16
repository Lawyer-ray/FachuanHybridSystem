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

    def _click_confirm_button(self) -> None:
        """
        点击"确认并预览材料"按钮

        尝试多种定位策略
        """
        try:
            submit_button: Any | None = None

            # 方案 1: 使用 ID/class
            try:
                submit_button = self.page.locator("#submit-btn, #confirm-btn, .submit-btn, .confirm-btn")
                if submit_button.count() > 0 and submit_button.first.is_visible():
                    logger.info("通过 ID/class 找到确认按钮")
                else:
                    submit_button = None
            except Exception:
                logger.exception("操作失败")

                pass

            # 方案 2: 使用文本
            if not submit_button:
                try:
                    submit_button = self.page.get_by_text("确认并预览材料", exact=False)
                    if submit_button.count() > 0 and submit_button.first.is_visible():
                        logger.info("通过文本找到确认按钮")
                    else:
                        submit_button = None
                except Exception:
                    logger.exception("操作失败")

                    pass

            # 方案 3: 使用按钮文本
            if not submit_button:
                try:
                    submit_button = self.page.locator(
                        "button:has-text('确认'), button:has-text('确定'), button:has-text('预览')"
                    )
                    if submit_button.count() > 0 and submit_button.first.is_visible():
                        logger.info("通过按钮选择器找到确认按钮")
                    else:
                        submit_button = None
                except Exception:
                    logger.exception("操作失败")

                    pass

            if submit_button and submit_button.count() > 0:
                submit_button.first.click()
                logger.info("已点击'确认并预览材料'按钮")

                # 等待预览页加载
                self.page.wait_for_load_state("networkidle", timeout=30000)
                self.random_wait(5, 7)  # type: ignore[attr-defined]
            else:
                logger.warning("未找到确认按钮,可能页面已经在预览状态")

        except Exception as e:
            logger.warning(f"点击确认按钮时出错: {e},继续尝试下载")

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
        # 点击下载按钮 - 多种方式尝试
        download_xpath = "/html/body/div/div[1]/div[1]/label/a/img"

        try:
            download_button: Any | None = None

            # 方式1: 使用 downloadPackClass 类名(最可靠)
            try:
                download_button = self.page.locator("a.downloadPackClass")
                if download_button.count() > 0 and download_button.first.is_visible():
                    logger.info("通过 a.downloadPackClass 找到下载按钮")
                else:
                    download_button = None
            except Exception:
                logger.exception("操作失败")

                pass

            # 方式2: 使用提供的 XPath
            if not download_button:
                try:
                    download_button = self.page.locator(f"xpath={download_xpath}")
                    if download_button.count() > 0 and download_button.first.is_visible():
                        logger.info(f"通过 XPath 找到下载按钮: {download_xpath}")
                    else:
                        download_button = None
                except Exception:
                    logger.exception("操作失败")

                    pass

            # 方式3: 查找 label 下的 a 标签(包含 img)
            if not download_button:
                try:
                    download_button = self.page.locator("label a:has(img)")
                    if download_button.count() > 0 and download_button.first.is_visible():
                        logger.info("通过 label a:has(img) 找到下载按钮")
                    else:
                        download_button = None
                except Exception:
                    logger.exception("操作失败")

                    pass

            # 方式4: 查找包含"送达材料"文本的链接
            if not download_button:
                try:
                    download_button = self.page.locator("a:has-text('送达材料')")
                    if download_button.count() > 0 and download_button.first.is_visible():
                        logger.info("通过文本'送达材料'找到下载按钮")
                    else:
                        download_button = None
                except Exception:
                    logger.exception("操作失败")

                    pass

            # 方式5: 查找任何包含"下载"的元素
            if not download_button:
                try:
                    download_button = self.page.locator("a:has-text('下载'), button:has-text('下载'), [title*='下载']")
                    if download_button.count() > 0 and download_button.first.is_visible():
                        logger.info("通过文本找到下载按钮")
                    else:
                        download_button = None
                except Exception:
                    logger.exception("操作失败")

                    pass

            if not download_button or download_button.count() == 0:
                # 保存页面 HTML 用于调试
                self._save_page_state("gdems_no_download_button")
                raise ValueError("找不到下载按钮")

            # 滚动到按钮位置
            download_button.first.scroll_into_view_if_needed()
            self.random_wait(1, 2)  # type: ignore[attr-defined]

            # 监听下载事件
            with self.page.expect_download(timeout=60000) as download_info:
                download_button.first.click()
                logger.info("已点击下载按钮,等待下载...")

            download = download_info.value

            # 保存 ZIP 文件
            zip_filename = download.suggested_filename or "documents.zip"
            zip_filepath = download_dir / zip_filename
            download.save_as(str(zip_filepath))

            logger.info(f"ZIP 文件已保存: {zip_filepath}")

            return zip_filepath

        except Exception as e:
            logger.error(f"下载失败: {e}")
            self._save_page_state("gdems_download_error")
            raise ValueError(f"文件下载失败: {e}")

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
