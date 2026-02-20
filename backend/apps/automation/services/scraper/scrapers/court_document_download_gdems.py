"""Business logic services."""

import logging
import os
from typing import TYPE_CHECKING, Any, Protocol

from apps.core.filesystem import FolderFilesystemService
from apps.core.path import Path

if TYPE_CHECKING:
    from playwright.sync_api import Page

    class _GdemsHost(Protocol):
        page: Page

        def navigate_to_url(self, timeout: int = ...) -> None: ...
        def random_wait(self, min_sec: float = ..., max_sec: float = ...) -> None: ...
        def screenshot(self, name: str = ...) -> str: ...
        def _save_page_state(self, name: str) -> Any: ...
        def _prepare_download_dir(self) -> Any: ...


logger = logging.getLogger("apps.automation")


class CourtDocumentGdemsDownloadMixin:
    def _download_gdems(self: "_GdemsHost", url: str) -> dict[str, Any]:
        logger.info("=" * 60)
        logger.info("处理 sd.gdems.com 链接...")
        logger.info("=" * 60)

        self.navigate_to_url()
        self.page.wait_for_load_state("networkidle", timeout=30000)
        self.random_wait(3, 5)

        screenshot_cover = self.screenshot("gdems_cover")

        self._gdems_click_confirm_button() # type: ignore

        screenshot_preview = self.screenshot("gdems_preview")

        download_dir = self._prepare_download_dir()
        zip_filepath = self._gdems_download_zip(download_dir) # type: ignore

        extracted_files = self._gdems_extract_zip(zip_filepath, download_dir) # type: ignore
        all_files: list[Any] = []
        return {
            "source": "sd.gdems.com",
            "zip_file": str(zip_filepath),
            "extracted_files": extracted_files,
            "files": all_files,
            "file_count": len(extracted_files),
            "screenshots": [screenshot_cover, screenshot_preview],
            "message": f"成功下载并解压 {len(extracted_files)} 个文件",
        }

    def _gdems_click_confirm_button(self: "_GdemsHost") -> None:
        """点击"确认并预览材料"按钮"""
        try:
            submit_button = self._gdems_find_confirm_button() # type: ignore

            if submit_button and submit_button.count() > 0:
                submit_button.first.click()
                logger.info("已点击'确认并预览材料'按钮")
                self.page.wait_for_load_state("networkidle", timeout=30000)
                self.random_wait(5, 7)
            else:
                logger.warning("未找到确认按钮,可能页面已经在预览状态")
        except Exception as e:
            logger.warning(f"点击确认按钮时出错: {e},继续尝试下载")

    def _gdems_find_confirm_button(self: "_GdemsHost") -> Any:
        """按优先级查找确认按钮"""
        strategies: list[Any] = [
            ("ID/class", "#submit-btn, #confirm-btn, .submit-btn, .confirm-btn"),
        ]
        for name, selector in strategies:
            try:
                btn = self.page.locator(selector)
                if btn.count() > 0 and btn.first.is_visible():
                    logger.info(f"通过 {name} 找到确认按钮")
                    return btn
            except Exception:
                logger.exception("操作失败")

                pass

        text_strategies: list[Any] = [
            ("文本", "确认并预览材料"),
        ]
        for name, text in text_strategies:
            try:
                btn = self.page.get_by_text(text, exact=False)
                if btn.count() > 0 and btn.first.is_visible():
                    logger.info(f"通过{name}找到确认按钮")
                    return btn
            except Exception:
                logger.exception("操作失败")

                pass

        try:
            btn = self.page.locator("button:has-text('确认'), button:has-text('确定'), button:has-text('预览')")
            if btn.count() > 0 and btn.first.is_visible():
                logger.info("通过按钮选择器找到确认按钮")
                return btn
        except Exception:
            logger.exception("操作失败")

            pass

        return None

    def _gdems_download_zip(self: "_GdemsHost", download_dir: Path) -> Any:
        """查找下载按钮并下载 ZIP 文件"""
        download_button = self._gdems_find_download_button() # type: ignore

        if not download_button or download_button.count() == 0:
            self._save_page_state("gdems_no_download_button")
            raise ValueError("找不到下载按钮")

        try:
            download_button.first.scroll_into_view_if_needed()
            self.random_wait(1, 2)

            with self.page.expect_download(timeout=60000) as download_info:
                download_button.first.click()
                logger.info("已点击下载按钮,等待下载...")

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

    def _gdems_find_download_button(self: "_GdemsHost") -> Any:
        """按优先级查找下载按钮"""
        download_xpath = "/html/body/div/div[1]/div[1]/label/a/img"
        strategies: list[Any] = [
            ("a.downloadPackClass", "a.downloadPackClass"),
            ("XPath", f"xpath={download_xpath}"),
            ("label a:has(img)", "label a:has(img)"),
            ("文本'送达材料'", "a:has-text('送达材料')"),
            ("文本'下载'", "a:has-text('下载'), button:has-text('下载'), [title*='下载']"),
        ]

        for name, selector in strategies:
            try:
                btn = self.page.locator(selector)
                if btn.count() > 0 and btn.first.is_visible():
                    logger.info(f"通过 {name} 找到下载按钮")
                    return btn
            except Exception:
                logger.exception("操作失败")

                pass

        return None

    def _gdems_extract_zip(self, zip_filepath: Path, download_dir: Path) -> list[str]:
        """解压 ZIP 文件并返回文件列表"""
        extracted_files: list[str] = []
        try:
            extract_dir = download_dir / "extracted"
            extract_dir.makedirs_p()

            with open(str(zip_filepath), "rb") as f:
                zip_content = f.read()
            FolderFilesystemService().extract_zip_bytes(str(extract_dir), zip_content)
            for root, _, files in os.walk(str(extract_dir)):
                for file in files:
                    extracted_files.append(str(Path(root) / file))

            logger.info(f"ZIP 文件已解压,共 {len(extracted_files)} 个文件")
        except Exception as e:
            logger.error(f"解压失败: {e}")
            extracted_files: list[Any] = [] # type: ignore
        return extracted_files
