"""zxfw 传统页面点击回退下载 Mixin"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("apps.automation")


class ZxfwFallbackMixin:
    """传统页面点击回退下载方法"""

    def _find_pdf_iframe(self) -> Any | None:
        """查找页面中的 PDF viewer iframe"""
        try:
            frame = self.page.frame_locator("#if")  # type: ignore[attr-defined]
            logger.info("[DEBUG] 通过 #if 找到 iframe")
            return frame
        except Exception:
            pass
        iframes = self.page.locator("iframe").all()  # type: ignore[attr-defined]
        for i, iframe in enumerate(iframes):
            src = iframe.get_attribute("src") or ""
            iframe_id = iframe.get_attribute("id") or ""
            logger.info(f"[DEBUG] 检查 iframe {i}: id={iframe_id}, src={src[:60]}...")
            if iframe_id == "if" or "pdfjs" in src or "viewer" in src:
                logger.info(f"[DEBUG] 找到 PDF viewer iframe (index {i})")
                return self.page.frame_locator(f"iframe >> nth={i}")  # type: ignore[attr-defined]
        return None

    def _click_doc_item(self, doc_index: int, doc_count: int) -> None:
        """点击文书列表中的指定项"""
        if doc_count <= 1 and doc_index == 1:
            return
        doc_item_xpath = (
            "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
            "/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view"
            f"/uni-view[1]/uni-view[1]/uni-view[{doc_index}]"
        )
        try:
            doc_item = self.page.locator(f"xpath={doc_item_xpath}")  # type: ignore[attr-defined]
            if doc_item.count() > 0:
                doc_item.first.click()
                logger.info(f"[DEBUG] 已点击第 {doc_index} 个文书项")
                self.random_wait(2, 3)  # type: ignore[attr-defined]
            else:
                logger.warning(f"[DEBUG] 未找到第 {doc_index} 个文书项")
        except Exception as e:
            logger.warning(f"[DEBUG] 点击文书项失败: {e}")

    def _download_single_doc(self, frame: Any, doc_index: int, download_dir: Path) -> str | None:
        """在 iframe 内下载单个文书，返回文件路径或 None"""
        filename_default = f"document_{doc_index}.pdf"
        try:
            btn = frame.locator("#download")
            btn.first.wait_for(state="visible", timeout=10000)
            btn.first.scroll_into_view_if_needed()
            self.random_wait(1, 2)  # type: ignore[attr-defined]
            with self.page.expect_download(timeout=60000) as dl_info:  # type: ignore[attr-defined]
                btn.first.click()
                logger.info(f"[DEBUG] 已点击第 {doc_index} 个文书的下载按钮")
            download = dl_info.value
            filepath = download_dir / (download.suggested_filename or filename_default)
            download.save_as(str(filepath))
            logger.info(f"[DEBUG] 文件已保存: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.warning(f"[DEBUG] #download 方式失败: {e}，尝试备用 XPath")
        try:
            fallback_xpath = "/html/body/div[1]/div[2]/div[5]/div/div[1]/div[2]/button[4]"
            btn = frame.locator(f"xpath={fallback_xpath}")
            btn.first.wait_for(state="visible", timeout=5000)
            with self.page.expect_download(timeout=60000) as dl_info:  # type: ignore[attr-defined]
                btn.first.click()
                logger.info("[DEBUG] 通过备用 XPath 点击下载按钮")
            download = dl_info.value
            filepath = download_dir / (download.suggested_filename or filename_default)
            download.save_as(str(filepath))
            return str(filepath)
        except Exception as e2:
            logger.error(f"[DEBUG] 第 {doc_index} 个文书下载失败: {e2}")
            return None

    def _download_via_fallback(self, download_dir: Path) -> dict[str, Any]:
        """通过传统页面点击方式下载文书（回退机制）"""
        downloaded_files: list[str] = []
        success_count = 0
        failed_count = 0
        doc_list_xpath = (
            "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
            "/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view"
            "/uni-view[1]/uni-view[1]/uni-view"
        )
        try:
            doc_items = self.page.locator(f"xpath={doc_list_xpath}").all()  # type: ignore[attr-defined]
            doc_count = len(doc_items)
            logger.info(f"[DEBUG] 检测到 {doc_count} 个文书项")
        except Exception as e:
            logger.warning(f"[DEBUG] 无法检测文书列表: {e}，尝试单文件下载")
            doc_count = 1
        if doc_count == 0:
            logger.info("[DEBUG] 未检测到文书列表，尝试直接下载")
            doc_count = 1
        for doc_index in range(1, doc_count + 1):
            logger.info(f"[DEBUG] 下载第 {doc_index}/{doc_count} 个文书")
            try:
                self._click_doc_item(doc_index, doc_count)
                frame = self._find_pdf_iframe()
                if not frame:
                    logger.warning(f"[DEBUG] 第 {doc_index} 个文书未找到 iframe，跳过")
                    failed_count += 1
                    continue
                filepath = self._download_single_doc(frame, doc_index, download_dir)
                if filepath:
                    downloaded_files.append(filepath)
                    success_count += 1
                else:
                    failed_count += 1
                self.random_wait(1, 2)  # type: ignore[attr-defined]
            except Exception as e:
                logger.error(f"[DEBUG] 处理第 {doc_index} 个文书时出错: {e}")
                failed_count += 1
        if not downloaded_files:
            self._save_page_state("zxfw_final_failed")  # type: ignore[attr-defined]
            raise ValueError("所有下载策略均失败，请查看调试文件")
        logger.info(
            "回退方式下载完成",
            extra={"operation_type": "fallback_download_summary", "timestamp": __import__("time").time(),
                   "total_count": doc_count, "success_count": success_count, "failed_count": failed_count},
        )
        return {
            "source": "zxfw.court.gov.cn",
            "document_count": doc_count,
            "downloaded_count": success_count,
            "failed_count": failed_count,
            "files": downloaded_files,
            "message": f"回退方式:成功下载 {success_count}/{doc_count} 份文书",
        }
