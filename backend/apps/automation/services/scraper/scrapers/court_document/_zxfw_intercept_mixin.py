"""zxfw Playwright API 拦截下载 Mixin"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger("apps.automation")


class ZxfwInterceptMixin:
    """Playwright API 拦截下载方法"""

    page: Page

    def _debug_log(self, message: str, data: Any = None) -> None:
        raise NotImplementedError

    def navigate_to_url(self) -> None:
        raise NotImplementedError

    def random_wait(self, min_s: float, max_s: float) -> None:
        raise NotImplementedError

    def _save_page_state(self, name: str) -> dict[str, Any]:
        raise NotImplementedError

    def _download_document_directly(
        self,
        document_data: dict[str, Any],
        download_dir: Path,
        download_timeout: int,
    ) -> tuple[bool, str | None, str | None]:
        raise NotImplementedError

    def _save_documents_batch(
        self,
        documents_with_results: list[tuple[dict[str, Any], tuple[bool, str | None, str | None]]],
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _intercept_api_response_with_navigation(self, timeout: int = 30000) -> dict[str, Any] | None:
        """在导航前注册监听器，拦截 API 响应"""
        api_url = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
        intercepted_data: dict[str, Any] | None = None
        start_time = time.time()
        logger.info(f"开始拦截 API 响应(导航前注册),超时时间: {timeout}ms")

        def handle_response(response: Any) -> None:
            nonlocal intercepted_data
            if api_url in response.url:
                try:
                    data = response.json()
                    intercepted_data = data
                    document_count = len(data.get("data", []))
                    response_time = (time.time() - start_time) * 1000
                    logger.info(
                        "成功拦截 API 响应",
                        extra={
                            "operation_type": "api_intercept",
                            "timestamp": time.time(),
                            "document_count": document_count,
                            "response_time_ms": response_time,
                            "api_url": api_url,
                        },
                    )
                except Exception as e:
                    logger.error(
                        f"解析 API 响应失败: {e}",
                        extra={
                            "operation_type": "api_intercept_parse_error",
                            "timestamp": time.time(),
                            "error": str(e),
                        },
                        exc_info=True,
                    )

        try:
            self.page.on("response", handle_response)
            logger.info(f"已注册 API 响应监听器: {api_url}")
            self._debug_log("开始导航到目标页面")
            self.navigate_to_url()
            self._debug_log("等待页面加载 (networkidle)")
            self.page.wait_for_load_state("networkidle", timeout=30000)
            self._debug_log("额外等待 3 秒,确保页面完全加载")
            self.random_wait(3, 5)
            if intercepted_data is None:
                timeout_seconds = timeout / 1000.0
                elapsed = 0.0
                check_interval = 0.5
                logger.info("API 响应尚未拦截到,继续等待...")
                while intercepted_data is None and elapsed < timeout_seconds:
                    time.sleep(check_interval)
                    elapsed += check_interval
                if intercepted_data is None:
                    logger.warning(
                        "API 拦截超时",
                        extra={
                            "operation_type": "api_intercept_timeout",
                            "timestamp": time.time(),
                            "timeout_ms": timeout,
                            "elapsed_ms": elapsed * 1000,
                            "api_url": api_url,
                        },
                    )
        except Exception as e:
            logger.error(
                f"API 拦截过程出错: {e}",
                extra={"operation_type": "api_intercept_error", "timestamp": time.time(), "error": str(e)},
                exc_info=True,
            )
        finally:
            try:
                self.page.remove_listener("response", handle_response)
                logger.info("已移除 API 响应监听器")
            except Exception as e:
                logger.warning(f"移除监听器失败: {e}")
        return intercepted_data

    def _download_via_api_intercept_with_navigation(self, download_dir: Path) -> dict[str, Any]:
        """通过 API 拦截方式下载文书（在导航前注册监听器）"""
        api_data = self._intercept_api_response_with_navigation(timeout=30000)
        self._debug_log("保存页面状态")
        self._save_page_state("zxfw_after_navigation")
        return self._process_api_data_and_download(api_data, download_dir)

    def _process_api_data_and_download(self, api_data: dict[str, Any] | None, download_dir: Path) -> dict[str, Any]:
        """处理 API 数据并下载文书"""
        if api_data is None:
            raise ValueError("API 拦截超时,未能获取文书列表")
        if not isinstance(api_data, dict):
            raise ValueError(f"API 响应格式错误:期望 dict,实际 {type(api_data)}")
        if "data" not in api_data:
            raise ValueError("API 响应缺少 data 字段")
        documents = api_data.get("data", [])
        if not isinstance(documents, list):
            raise ValueError(f"API 响应 data 字段格式错误:期望 list,实际 {type(documents)}")
        if len(documents) == 0:
            raise ValueError("API 响应中没有文书数据")
        logger.info(
            f"成功获取文书列表,共 {len(documents)} 个文书",
            extra={
                "operation_type": "api_intercept_parse_success",
                "timestamp": time.time(),
                "document_count": len(documents),
            },
        )
        downloaded_files: list[str] = []
        documents_with_results: list[tuple[dict[str, Any], tuple[bool, str | None, str | None]]] = []
        success_count = 0
        failed_count = 0
        for i, document_data in enumerate(documents, 1):
            logger.info(f"处理第 {i}/{len(documents)} 个文书: {document_data.get('c_wsmc', 'Unknown')}")
            download_result = self._download_document_directly(
                document_data=document_data, download_dir=download_dir, download_timeout=60000
            )
            success, filepath, _ = download_result
            if success:
                success_count += 1
                if filepath:
                    downloaded_files.append(filepath)
            else:
                failed_count += 1
            documents_with_results.append((document_data, download_result))
            if i < len(documents):
                import random
                import time as _time

                delay = random.uniform(1, 2)
                logger.info(f"等待 {delay:.2f} 秒后继续下载下一个文书")
                _time.sleep(delay)
        db_save_result = self._save_documents_batch(documents_with_results)
        logger.info(
            "文书下载完成",
            extra={
                "operation_type": "download_summary",
                "timestamp": time.time(),
                "total_count": len(documents),
                "success_count": success_count,
                "failed_count": failed_count,
                "db_saved_count": db_save_result.get("success", 0),
                "db_failed_count": db_save_result.get("failed", 0),
            },
        )
        return {
            "source": "zxfw.court.gov.cn",
            "method": "api_intercept",
            "document_count": len(documents),
            "downloaded_count": success_count,
            "failed_count": failed_count,
            "files": downloaded_files,
            "db_save_result": db_save_result,
            "message": f"API 拦截方式:成功下载 {success_count}/{len(documents)} 份文书",
        }
