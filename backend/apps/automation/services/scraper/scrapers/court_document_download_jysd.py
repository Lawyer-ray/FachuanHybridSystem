"""Business logic services."""

import contextlib
import logging
import re
import time
from typing import TYPE_CHECKING, Any, Protocol

from apps.core.path import Path

if TYPE_CHECKING:
    from playwright.sync_api import Page

    class _JysdHost(Protocol):
        page: Page

        def navigate_to_url(self, timeout: int = ...) -> None: ...
        def random_wait(self, min_sec: float = ..., max_sec: float = ...) -> None: ...
        def screenshot(self, name: str = ...) -> str: ...
        def _save_page_state(self, name: str) -> Any: ...
        def _prepare_download_dir(self) -> Any: ...


logger = logging.getLogger("apps.automation")


class CourtDocumentJysdDownloadMixin:
    def _download_jysd(self: "_JysdHost", url: str) -> dict[str, Any]:
        logger.info("=" * 60)
        logger.info("处理 jysd.10102368.com 链接...")
        logger.info("=" * 60)

        self.navigate_to_url()
        self.page.wait_for_load_state("domcontentloaded", timeout=30000)
        self.random_wait(2, 3)

        screenshot_cover = self.screenshot("jysd_cover")

        frame = self._jysd_get_iframe()
        page_ctx = frame if frame is not None else self.page

        self._jysd_click_details_button(page_ctx, frame)

        screenshot_after_details = self.screenshot("jysd_after_details")

        rows = self._jysd_get_table_rows(page_ctx, frame)
        row_count = rows.count()

        logger.info(f"检测到 {row_count} 份文书,开始逐条下载")
        download_dir = self._prepare_download_dir()

        downloaded_files, documents, success_count, failed_count = self._jysd_download_all_rows(
            rows, row_count, download_dir
        )

        if not downloaded_files:
            with contextlib.suppress(Exception):
                self._save_page_state("jysd_download_all_failed")
            raise ValueError("所有文书下载失败,请查看调试文件")

        logger.info(
            "jysd 下载完成",
            extra={
                "operation_type": "jysd_download_summary",
                "timestamp": time.time(),
                "total_count": row_count,
                "success_count": success_count,
                "failed_count": failed_count,
            },
        )

        return {
            "source": "jysd.10102368.com",
            "document_count": row_count,
            "downloaded_count": success_count,
            "failed_count": failed_count,
            "files": downloaded_files,
            "documents": documents,
            "screenshots": [screenshot_cover, screenshot_after_details],
            "message": f"成功下载 {success_count}/{row_count} 份文书",
        }

    def _jysd_get_iframe(self: "_JysdHost") -> Any:
        """获取 jysd 页面的 iframe"""
        frame = None
        try:
            iframe_locator = self.page.locator("iframe#mainframe")
            if iframe_locator.count() == 0:
                iframe_locator = self.page.locator("iframe").first
            iframe_locator.wait_for(state="attached", timeout=20000)

            frame = self._jysd_resolve_frame()

            if frame is not None:
                with contextlib.suppress(Exception):
                    frame.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception as e:
            logger.warning(f"未能获取 iframe,上下文将使用主页面: {e}")

        return frame

    def _jysd_resolve_frame(self: "_JysdHost") -> Any:
        """按优先级查找 mainframe"""
        try:
            frame = self.page.frame(name="mainframe")
            if frame is not None:
                return frame
        except Exception:
            logger.exception("操作失败")

            pass

        for f in self.page.frames:
            if f.name == "mainframe":
                return f

        for f in self.page.frames:
            if f != self.page.main_frame:
                return f

        return None

    def _jysd_click_details_button(self: "_JysdHost", page_ctx: Any, frame: Any) -> None:
        """点击"查看文书详情"按钮"""
        details_button_xpath = "//*[@id='app']/section/main/section/div[2]/div/button/div"
        try:
            details_button = page_ctx.locator(f"xpath={details_button_xpath}")
            if details_button.count() == 0:
                details_button = page_ctx.get_by_text("查看文书详情", exact=False)

            details_button.first.wait_for(state="visible", timeout=20000)
            with contextlib.suppress(Exception):
                details_button.first.scroll_into_view_if_needed()
            self.random_wait(0.5, 1)

            details_button.first.click()
            logger.info("已点击「查看文书详情」按钮,等待页面跳转")

            self._jysd_wait_after_click(frame)
            self.random_wait(3, 5)
        except Exception as e:
            logger.warning(f"点击「查看文书详情」失败: {e},继续尝试在当前页查找文书表格")

    def _jysd_wait_after_click(self: "_JysdHost", frame: Any) -> None:
        """点击详情按钮后等待页面加载"""
        if frame is not None:
            try:
                frame.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                logger.exception("操作失败")

                with contextlib.suppress(Exception):
                    frame.wait_for_load_state("domcontentloaded", timeout=30000)
        else:
            try:
                self.page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                logger.exception("操作失败")

                self.page.wait_for_load_state("domcontentloaded", timeout=30000)

    def _jysd_get_table_rows(self: "_JysdHost", page_ctx: Any, frame: Any) -> Any:
        """获取文书列表表格行"""
        rows_xpath = "//*[@id='container']/main/section/div[2]/div[3]/div/div[3]/table/tbody/tr"
        rows = page_ctx.locator(f"xpath={rows_xpath}")
        if rows.count() == 0:
            rows = page_ctx.locator("css=table tbody tr")

        try:
            rows.first.wait_for(state="attached", timeout=15000)
        except Exception:
            with contextlib.suppress(Exception):
                self._save_page_state("jysd_no_table_rows")
            if frame is not None:
                self._jysd_save_iframe_debug(frame)
            raise ValueError("未找到文书列表表格行") from None

        row_count = rows.count()
        if row_count <= 0:
            with contextlib.suppress(Exception):
                self._save_page_state("jysd_empty_table_rows")
            raise ValueError("文书列表为空")

        return rows

    def _jysd_save_iframe_debug(self: "_JysdHost", frame: Any) -> None:
        """保存 iframe HTML 用于调试"""
        try:
            download_dir = self._prepare_download_dir()
            html_path = download_dir / "jysd_iframe_page.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(frame.content())
            logger.info(f"[DEBUG] iframe HTML 已保存: {html_path}")
        except Exception:
            logger.exception("操作失败")

            pass

    def _jysd_download_all_rows(
        self: "_JysdHost", rows: Any, row_count: int, download_dir: Path
    ) -> tuple[list[str], list[dict[str, Any]], int, int]:
        """逐行下载文书"""
        downloaded_files: list[str] = []
        documents: list[dict[str, Any]] = []
        success_count = 0
        failed_count = 0

        for index in range(row_count):
            row = rows.nth(index)
            doc_name = ""

            try:
                name_locator = row.locator("xpath=./td[1]/div")
                doc_name = (name_locator.first.inner_text() or "").strip()

                download_button = row.locator("xpath=./td[4]/div/button")
                download_button.first.wait_for(state="visible", timeout=10000)
                download_button.first.scroll_into_view_if_needed()
                self.random_wait(0.5, 1)

                with self.page.expect_download(timeout=60000) as download_info:
                    download_button.first.click()
                    logger.info(f"已点击下载按钮: 第 {index + 1}/{row_count} 份文书")

                download = download_info.value
                filepath = self._jysd_save_download(download, doc_name, index, download_dir)

                downloaded_files.append(str(filepath))
                success_count += 1
                documents.append(
                    {
                        "index": index + 1,
                        "document_name": doc_name,
                        "suggested_filename": download.suggested_filename or "",
                        "saved_path": str(filepath),
                    }
                )
                self.random_wait(0.8, 1.8)

            except Exception as e:
                failed_count += 1
                documents.append(
                    {
                        "index": index + 1,
                        "document_name": doc_name,
                        "error": str(e),
                    }
                )
                logger.warning(f"下载第 {index + 1}/{row_count} 份文书失败: {e}")
                self.random_wait(0.5, 1.2)
                continue

        return downloaded_files, documents, success_count, failed_count

    def _jysd_save_download(self, download: Any, doc_name: str, index: int, download_dir: Path) -> Any:
        """保存下载的文件到目标路径"""
        suggested = download.suggested_filename or ""
        ext = Path(suggested).ext if suggested else ""
        if not ext:
            ext = ".pdf"

        filename_base = doc_name or f"document_{index + 1}"
        filename_base = re.sub(r'[<>:"/\\|?*]', "_", filename_base).strip() or f"document_{index + 1}"

        target_path = download_dir / f"{filename_base}{ext}"
        counter = 1
        while target_path.exists():
            target_path = download_dir / f"{filename_base}({counter}){ext}"
            counter += 1
            if counter > 100:
                break

        download.save_as(str(target_path))
        return target_path
