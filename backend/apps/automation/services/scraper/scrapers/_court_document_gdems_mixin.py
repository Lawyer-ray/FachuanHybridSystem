"""法院文书爬虫 — gdems 下载 Mixin"""

import logging
import zipfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("apps.automation")


class CourtDocumentGdemsMixin:
    """sd.gdems.com 文书下载相关方法"""

    # 子类提供
    def _prepare_download_dir(self) -> Path: ...
    def _save_page_state(self, name: str) -> dict[str, Any]: ...
    def navigate_to_url(self) -> None: ...
    def screenshot(self, name: str) -> Any: ...
    def random_wait(self, min_s: float, max_s: float) -> None: ...

    def _find_visible_locator(self, selectors: list[str]) -> Any:
        """按顺序尝试多个选择器，返回第一个可见的定位器"""
        for selector in selectors:
            try:
                loc = self.page.locator(selector)  # type: ignore[attr-defined]
                if loc.count() > 0 and loc.first.is_visible():
                    return loc
            except Exception:
                pass
        return None

    def _click_gdems_confirm_button(self) -> None:
        """点击 gdems 确认按钮"""
        try:
            selectors = [
                "#submit-btn, #confirm-btn, .submit-btn, .confirm-btn",
                "button:has-text('确认'), button:has-text('确定'), button:has-text('预览')",
            ]
            submit_button = self._find_visible_locator(selectors)
            if not submit_button:
                try:
                    btn = self.page.get_by_text("确认并预览材料", exact=False)  # type: ignore[attr-defined]
                    if btn.count() > 0 and btn.first.is_visible():
                        submit_button = btn
                except Exception:
                    pass
            if submit_button and submit_button.count() > 0:
                submit_button.first.click()
                logger.info("已点击'确认并预览材料'按钮")
                self.page.wait_for_load_state("networkidle", timeout=30000)  # type: ignore[attr-defined]
                self.random_wait(5, 7)
            else:
                logger.warning("未找到确认按钮，可能页面已经在预览状态")
        except Exception as e:
            logger.warning(f"点击确认按钮时出错: {e}，继续尝试下载")

    def _download_gdems_zip(self, download_dir: Path) -> Path:
        """下载 gdems ZIP 文件，返回文件路径"""
        download_xpath = "/html/body/div/div[1]/div[1]/label/a/img"
        selectors = [
            "a.downloadPackClass",
            f"xpath={download_xpath}",
            "label a:has(img)",
            "a:has-text('送达材料')",
            "a:has-text('下载'), button:has-text('下载'), [title*='下载']",
        ]
        try:
            download_button = self._find_visible_locator(selectors)
            if not download_button or download_button.count() == 0:
                self._save_page_state("gdems_no_download_button")
                raise ValueError("找不到下载按钮")
            download_button.first.scroll_into_view_if_needed()
            self.random_wait(1, 2)
            with self.page.expect_download(timeout=60000) as download_info:  # type: ignore[attr-defined]
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

    def _extract_gdems_zip(self, zip_filepath: Path, download_dir: Path) -> list[str]:
        """解压 ZIP 文件，返回解压后的文件路径列表"""
        try:
            extract_dir = download_dir / "extracted"
            extract_dir.mkdir(exist_ok=True)
            with zipfile.ZipFile(zip_filepath, "r") as zip_ref:
                zip_ref.extractall(extract_dir)
                extracted = [str(extract_dir / name) for name in zip_ref.namelist()]
            logger.info(f"ZIP 文件已解压，共 {len(extracted)} 个文件")
            return extracted
        except Exception as e:
            logger.error(f"解压失败: {e}")
            return []

    def _download_gdems(self, url: str) -> dict[str, Any]:
        """下载 sd.gdems.com 的文书"""
        logger.info("处理 sd.gdems.com 链接...")
        self.navigate_to_url()
        self.page.wait_for_load_state("networkidle", timeout=30000)  # type: ignore[attr-defined]
        self.random_wait(3, 5)
        screenshot_cover = self.screenshot("gdems_cover")
        self._click_gdems_confirm_button()
        screenshot_preview = self.screenshot("gdems_preview")
        download_dir = self._prepare_download_dir()
        zip_filepath = self._download_gdems_zip(download_dir)
        extracted_files = self._extract_gdems_zip(zip_filepath, download_dir)
        all_files = [str(zip_filepath)] + extracted_files
        return {
            "source": "sd.gdems.com",
            "zip_file": str(zip_filepath),
            "extracted_files": extracted_files,
            "files": all_files,
            "file_count": len(extracted_files),
            "screenshots": [screenshot_cover, screenshot_preview],
            "message": f"成功下载并解压 {len(extracted_files)} 个文件",
        }
