"""Business logic services."""

import logging
import re
import time
from typing import TYPE_CHECKING, Any, Protocol

from apps.automation.utils.logging_mixins.common import sanitize_url
from apps.core.path import Path

if TYPE_CHECKING:
    from playwright.sync_api import Page

    class _ZxfwHost(Protocol):
        page: Page
        _logger: logging.Logger

        def navigate_to_url(self, timeout: int = ...) -> None: ...
        def random_wait(self, min_sec: float = ..., max_sec: float = ...) -> None: ...
        def _save_page_state(self, name: str) -> Any: ...
        def _prepare_download_dir(self) -> Any: ...
        def _debug_log(self, message: str, data: Any = ...) -> None: ...
        def _extract_url_params(self, url: str) -> dict[str, str] | None: ...
        def _fetch_documents_via_direct_api(self, params: dict[str, str]) -> list[dict[str, Any]]: ...
        def _intercept_api_response_with_navigation(self, timeout: int = ...) -> dict[str, Any] | None: ...
        def _process_api_data_and_download(
            self, api_data: dict[str, Any] | None, download_dir: Path
        ) -> dict[str, Any]: ...
        def _save_documents_batch(
            self, documents_with_results: list[tuple[dict[str, Any], tuple[bool, str | None, str | None]]]
        ) -> dict[str, Any]: ...


logger = logging.getLogger("apps.automation")


class CourtDocumentZxfwDownloadMixin:
    def _download_document_directly(
        self: "_ZxfwHost", document_data: dict[str, Any], download_dir: Path, download_timeout: int = 60000
    ) -> tuple[bool, str | None, str | None]:
        start_time = time.time()

        try:
            url = document_data.get("wjlj")
            if not url:
                error_msg = "文书数据中缺少下载链接 (wjlj)"
                self._logger.error(error_msg)
                return False, None, error_msg

            filename_base = document_data.get("c_wsmc", "document")
            file_extension = document_data.get("c_wjgs", "pdf")

            filename_base = re.sub(r'[<>:"/\\|?*]', "_", filename_base)

            if filename_base.lower().endswith(f".{file_extension.lower()}"):
                filename = filename_base
            else:
                filename = f"{filename_base}.{file_extension}"

            filepath = download_dir / filename

            self._logger.info(f"开始直接下载文书: {filename}, URL: {sanitize_url(url)}")

            try:
                import httpx

                timeout_seconds = download_timeout / 1000.0

                with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
                    response = client.get(url)
                    response.raise_for_status()

                    with open(filepath, "wb") as f:
                        f.write(response.content)

                file_size = filepath.stat().st_size if filepath.exists() else None
                download_time = (time.time() - start_time) * 1000

                self._logger.info(
                    "文书下载成功",
                    extra={
                        "operation_type": "download_document_direct_success",
                        "timestamp": time.time(),
                        "file_name": filename,
                        "file_size": file_size,
                        "download_time_ms": download_time,
                        "file_path": str(filepath),
                    },
                )

                return True, str(filepath), None

            except Exception as e:
                logger.exception("操作失败")
                error_msg = f"下载失败: {e!s}"
                self._logger.error(error_msg, exc_info=True)

                return False, None, error_msg

        except Exception as e:
            logger.exception("操作失败")
            error_msg = f"处理下载请求失败: {e!s}"
            self._logger.error(error_msg, exc_info=True)
            return False, None, error_msg

    def _try_click_download(self: "_ZxfwHost", timeout: int = 30000) -> Any | None:
        strategies: list[Any] = [
            {"name": "ID #download", "locator": "#download"},
            {"name": "文本 '下载'", "locator": "text=下载"},
            {"name": "按钮角色", "locator": "button:has-text('下载')"},
            {"name": "链接", "locator": "a:has-text('下载')"},
            {"name": "可点击元素", "locator": "[onclick*='download'], [href*='download']"},
        ]

        for strategy in strategies:
            try:
                self._logger.info(f"[DEBUG] 尝试策略: {strategy['name']}")

                locator = self.page.locator(strategy["locator"]).first
                if locator.count() == 0:
                    self._logger.info(f"[DEBUG] 策略 {strategy['name']}: 未找到元素")
                    continue

                if not locator.is_visible():
                    self._logger.info(f"[DEBUG] 策略 {strategy['name']}: 元素不可见")
                    continue

                self._logger.info(f"[DEBUG] 策略 {strategy['name']}: 找到元素,尝试点击")

                locator.scroll_into_view_if_needed()
                self.random_wait(0.5, 1)

                with self.page.expect_download(timeout=timeout) as download_info:
                    locator.click()
                    self._logger.info(f"[DEBUG] 策略 {strategy['name']}: 点击成功,等待下载")

                download = download_info.value
                self._logger.info(f"[DEBUG] 策略 {strategy['name']}: 下载成功!文件: {download.suggested_filename}")
                return download

            except Exception as e:
                logger.exception("操作失败")
                self._logger.warning(f"[DEBUG] 策略 {strategy['name']} 失败: {e}")
                continue

        return None

    def _download_via_direct_api(self: "_ZxfwHost", url: str, download_dir: Path) -> dict[str, Any]:
        import random

        params = self._extract_url_params(url)
        if not params:
            raise ValueError("无法从 URL 中提取必要参数 (sdbh, qdbh, sdsin)")

        documents = self._fetch_documents_via_direct_api(params)

        if len(documents) == 0:
            raise ValueError("API 返回的文书列表为空")

        self._logger.info(f"直接 API 获取到 {len(documents)} 个文书,开始下载")

        downloaded_files: list[str | None] = []
        documents_with_results: list[tuple[dict[str, Any], tuple[bool, str | None, str | None]]] = []
        success_count = 0
        failed_count = 0

        for i, document_data in enumerate(documents, 1):
            self._logger.info(f"下载第 {i}/{len(documents)} 个文书: {document_data.get('c_wsmc', 'Unknown')}")

            download_result = self._download_document_directly(  # type: ignore[attr-defined]
                document_data=document_data, download_dir=download_dir, download_timeout=60000
            )

            success, filepath, error = download_result

            if success:
                success_count += 1
                downloaded_files.append(filepath)
            else:
                failed_count += 1

            documents_with_results.append((document_data, download_result))

            if i < len(documents):
                delay = random.uniform(0.5, 1.5)
                time.sleep(delay)

        db_save_result = self._save_documents_batch(documents_with_results)

        self._logger.info(
            "直接 API 方式下载完成",
            extra={
                "operation_type": "direct_api_download_summary",
                "timestamp": time.time(),
                "total_count": len(documents),
                "success_count": success_count,
                "failed_count": failed_count,
            },
        )

        return {
            "source": "zxfw.court.gov.cn",
            "method": "direct_api",
            "document_count": len(documents),
            "downloaded_count": success_count,
            "failed_count": failed_count,
            "files": downloaded_files,
            "db_save_result": db_save_result,
            "message": f"直接 API 方式:成功下载 {success_count}/{len(documents)} 份文书",
        }

    def _download_via_api_intercept_with_navigation(self: "_ZxfwHost", download_dir: Path) -> dict[str, Any]:
        api_data = self._intercept_api_response_with_navigation(timeout=30000)

        self._debug_log("保存页面状态")
        self._save_page_state("zxfw_after_navigation")

        return self._process_api_data_and_download(api_data, download_dir)

    def _download_via_api_intercept(self: "_ZxfwHost", download_dir: Path) -> dict[str, Any]:
        return self._download_via_api_intercept_with_navigation(download_dir)  # type: ignore[no-any-return, attr-defined]

    def _download_via_fallback(self: "_ZxfwHost", download_dir: Path) -> dict[str, Any]:
        downloaded_files: list[str] = []
        success_count = 0
        failed_count = 0

        doc_count = self._zxfw_detect_doc_count()  # type: ignore[attr-defined]

        for doc_index in range(1, doc_count + 1):
            logger.info(f"\n{'=' * 40}")
            logger.info(f"[DEBUG] 下载第 {doc_index}/{doc_count} 个文书")
            logger.info(f"{'=' * 40}")

            try:
                self._zxfw_click_doc_item(doc_index, doc_count)  # type: ignore[attr-defined]
                frame = self._zxfw_find_pdf_iframe()  # type: ignore[attr-defined]

                if not frame:
                    logger.warning(f"[DEBUG] 第 {doc_index} 个文书未找到 iframe,跳过")
                    continue

                filepath = self._zxfw_download_from_frame(frame, doc_index, download_dir)  # type: ignore[attr-defined]
                if filepath:
                    downloaded_files.append(filepath)
                    success_count += 1
                else:
                    failed_count += 1

                self.random_wait(1, 2)

            except Exception as e:
                logger.error(f"[DEBUG] 处理第 {doc_index} 个文书时出错: {e}")
                failed_count += 1
                continue

        if not downloaded_files:
            self._save_page_state("zxfw_final_failed")
            raise ValueError("所有下载策略均失败,请查看调试文件")

        logger.info(
            "回退方式下载完成",
            extra={
                "operation_type": "fallback_download_summary",
                "timestamp": time.time(),
                "total_count": doc_count,
                "success_count": success_count,
                "failed_count": failed_count,
            },
        )

        return {
            "source": "zxfw.court.gov.cn",
            "document_count": doc_count,
            "downloaded_count": success_count,
            "failed_count": failed_count,
            "files": downloaded_files,
            "message": f"回退方式:成功下载 {success_count}/{doc_count} 份文书",
        }

    def _zxfw_detect_doc_count(self: "_ZxfwHost") -> int:
        """检测文书列表中的文书数量"""
        doc_list_xpath = (
            "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page"
            "/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view"
            "/uni-view[1]/uni-view[1]/uni-view"
        )
        try:
            doc_items = self.page.locator(f"xpath={doc_list_xpath}").all()
            doc_count = len(doc_items)
            logger.info(f"[DEBUG] 检测到 {doc_count} 个文书项")
        except Exception as e:
            logger.warning(f"[DEBUG] 无法检测文书列表: {e},尝试单文件下载")
            doc_count = 1

        if doc_count == 0:
            logger.info("[DEBUG] 未检测到文书列表,尝试直接下载")
            doc_count = 1

        return doc_count

    def _zxfw_click_doc_item(self: "_ZxfwHost", doc_index: int, doc_count: int) -> None:
        """点击指定的文书项"""
        if doc_count <= 1 and doc_index <= 1:
            return

        doc_item_xpath = (
            "/html/body/uni-app/uni-layout/uni-content/uni-main"
            "/uni-page/uni-page-wrapper/uni-page-body/uni-view"
            "/uni-view/uni-view/uni-view[1]/uni-view[1]"
            f"/uni-view[{doc_index}]"
        )
        try:
            doc_item = self.page.locator(f"xpath={doc_item_xpath}")
            if doc_item.count() > 0:
                doc_item.first.click()
                logger.info(f"[DEBUG] 已点击第 {doc_index} 个文书项")
                self.random_wait(2, 3)
            else:
                logger.warning(f"[DEBUG] 未找到第 {doc_index} 个文书项")
        except Exception as e:
            logger.warning(f"[DEBUG] 点击文书项失败: {e}")

    def _zxfw_find_pdf_iframe(self: "_ZxfwHost") -> Any:
        """查找 PDF viewer iframe"""
        try:
            frame = self.page.frame_locator("#if")
            logger.info("[DEBUG] 通过 #if 找到 iframe")
            return frame
        except Exception:
            logger.exception("操作失败")

            pass

        iframes = self.page.locator("iframe").all()
        for i, iframe in enumerate(iframes):
            src = iframe.get_attribute("src") or ""
            iframe_id = iframe.get_attribute("id") or ""
            logger.info(f"[DEBUG] 检查 iframe {i}: id={iframe_id}, src={src[:60]}...")

            if iframe_id == "i" or "pdfjs" in src or "viewer" in src:
                logger.info(f"[DEBUG] 找到 PDF viewer iframe (index {i})")
                return self.page.frame_locator(f"iframe >> nth={i}")

        return None

    def _zxfw_download_from_frame(self: "_ZxfwHost", frame: Any, doc_index: int, download_dir: Path) -> str | None:
        """从 iframe 中下载文书,返回文件路径或 None"""
        try:
            btn = frame.locator("#download")
            btn.first.wait_for(state="visible", timeout=10000)
            btn.first.scroll_into_view_if_needed()
            self.random_wait(1, 2)

            with self.page.expect_download(timeout=60000) as download_info:
                btn.first.click()
                logger.info(f"[DEBUG] 已点击第 {doc_index} 个文书的下载按钮")

            download = download_info.value
            filename = download.suggested_filename or f"document_{doc_index}.pdf"
            filepath = download_dir / filename
            download.save_as(str(filepath))
            logger.info(f"[DEBUG] 文件已保存: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.warning(f"[DEBUG] #download 方式失败: {e},尝试备用 XPath")

        return self._zxfw_download_from_frame_fallback(frame, doc_index, download_dir)  # type: ignore[no-any-return, attr-defined]

    def _zxfw_download_from_frame_fallback(
        self: "_ZxfwHost", frame: Any, doc_index: int, download_dir: Path
    ) -> str | None:
        """备用 XPath 方式下载"""
        try:
            download_xpath = "/html/body/div[1]/div[2]/div[5]/div/div[1]/div[2]/button[4]"
            btn = frame.locator(f"xpath={download_xpath}")
            btn.first.wait_for(state="visible", timeout=5000)

            with self.page.expect_download(timeout=60000) as download_info:
                btn.first.click()
                logger.info("[DEBUG] 通过备用 XPath 点击下载按钮")

            download = download_info.value
            filename = download.suggested_filename or f"document_{doc_index}.pdf"
            filepath = download_dir / filename
            download.save_as(str(filepath))
            return str(filepath)

        except Exception as e2:
            logger.error(f"[DEBUG] 第 {doc_index} 个文书下载失败: {e2}")
            return None
