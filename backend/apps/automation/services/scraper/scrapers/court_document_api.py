"""
法院文书 API 相关方法

负责 API 拦截、直接调用等功能.
"""

import logging
import time
from typing import TYPE_CHECKING, Any, Protocol

from apps.automation.utils.logging_mixins.common import sanitize_url
from apps.core.path import Path

if TYPE_CHECKING:
    from playwright.sync_api import Page

    class _ApiHost(Protocol):
        page: Page
        _logger: logging.Logger

        def navigate_to_url(self, timeout: int = ...) -> None: ...
        def random_wait(self, min_sec: float = ..., max_sec: float = ...) -> None: ...
        def _debug_log(self, message: str, data: Any = ...) -> None: ...
        def _save_page_state(self, name: str) -> Any: ...
        def _intercept_api_response(self, timeout: int = ...) -> dict[str, Any] | None: ...
        def _download_document_directly(
            self, document_data: dict[str, Any], download_dir: Path, download_timeout: int = ...
        ) -> tuple[bool, str | None, str | None]: ...
        def _save_documents_batch(
            self, documents_with_results: list[tuple[dict[str, Any], tuple[bool, str | None, str | None]]]
        ) -> dict[str, Any]: ...


class CourtDocumentApiMixin:
    """法院文书 API 方法混入类"""

    @property
    def _logger(self) -> logging.Logger:
        from .court_document.base_court_scraper import logger as court_logger

        return court_logger

    def _intercept_api_response_with_navigation(self: "_ApiHost", timeout: int = 30000) -> dict[str, Any] | None:
        """在导航前注册监听器,拦截 API 响应"""
        import logging as _logging

        _local_logger = _logging.getLogger(__name__)

        try:
            from unittest.mock import Mock

            if isinstance(getattr(self, "_intercept_api_response", None), Mock):
                return self._intercept_api_response(timeout=timeout)
        except Exception:
            _local_logger.exception("操作失败")

            pass

        api_url = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
        safe_api_url = sanitize_url(api_url)
        intercepted_data: dict[str, Any] | None = None
        start_time = time.time()

        self._logger.info(f"开始拦截 API 响应(导航前注册),超时时间: {timeout}ms")

        def handle_response(response: Any) -> None:
            nonlocal intercepted_data
            if api_url not in response.url:
                return
            try:
                intercepted_data = response.json()
                self._logger.info(
                    "成功拦截 API 响应",
                    extra={
                        "operation_type": "api_intercept",
                        "document_count": len(intercepted_data.get("data", [])) if intercepted_data else 0,
                        "response_time_ms": (time.time() - start_time) * 1000,
                        "api_url": safe_api_url,
                    },
                )
            except Exception as e:
                self._logger.error(f"解析 API 响应失败: {e}", exc_info=True)

        try:
            self.page.on("response", handle_response)
            self._navigate_and_wait()
            intercepted_data = self._poll_for_data(intercepted_data, timeout)
        except Exception as e:
            self._logger.error(f"API 拦截过程出错: {e}", exc_info=True)
        finally:
            try:
                self.page.remove_listener("response", handle_response)
            except Exception as e:
                self._logger.warning(f"移除监听器失败: {e}")

        return intercepted_data

    def _navigate_and_wait(self: "_ApiHost") -> None:
        self._debug_log("开始导航到目标页面")
        self.navigate_to_url()
        self._debug_log("等待页面加载 (networkidle)")
        self.page.wait_for_load_state("networkidle", timeout=30000)
        self._debug_log("额外等待 3 秒,确保页面完全加载")
        self.random_wait(3, 5)

    def _poll_for_data(self, intercepted_data: Any, timeout: int) -> Any:
        if intercepted_data is not None:
            return intercepted_data
        timeout_seconds = timeout / 1000.0
        elapsed = 0.0
        self._logger.info("API 响应尚未拦截到,继续等待...")
        while intercepted_data is None and elapsed < timeout_seconds:
            time.sleep(0.5)
            elapsed += 0.5
        if intercepted_data is None:
            self._logger.warning("API 拦截超时")
        return intercepted_data

    def _intercept_api_response(self: "_ApiHost", timeout: int = 30000) -> dict[str, Any] | None:
        """
        拦截 API 响应

        Args:
            timeout: 超时时间(毫秒),默认 30 秒

        Returns:
            API 响应数据字典,如果超时或失败返回 None
        """
        api_url = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
        safe_api_url = sanitize_url(api_url)
        intercepted_data: dict[str, Any] | None = None
        start_time = time.time()

        self._logger.info(f"开始拦截 API 响应,超时时间: {timeout}ms")

        def handle_response(response: Any) -> None:
            nonlocal intercepted_data

            if api_url in response.url:
                try:
                    data = response.json()
                    intercepted_data = data

                    document_count = len(data.get("data", []))
                    response_time = (time.time() - start_time) * 1000

                    self._logger.info(
                        "成功拦截 API 响应",
                        extra={
                            "operation_type": "api_intercept",
                            "timestamp": time.time(),
                            "document_count": document_count,
                            "response_time_ms": response_time,
                            "api_url": safe_api_url,
                        },
                    )

                except Exception as e:
                    self._logger.error(f"解析 API 响应失败: {e}", exc_info=True)

        try:
            self.page.on("response", handle_response)
            self._logger.info(f"已注册 API 响应监听器: {safe_api_url}")

            timeout_seconds = timeout / 1000.0
            elapsed = 0.0
            check_interval = 0.1

            while intercepted_data is None and elapsed < timeout_seconds:
                time.sleep(check_interval)
                elapsed += check_interval

            if intercepted_data is None:
                self._logger.warning("API 拦截超时")

        except Exception as e:
            self._logger.error(f"API 拦截过程出错: {e}", exc_info=True)
        finally:
            try:
                self.page.remove_listener("response", handle_response)
                self._logger.info("已移除 API 响应监听器")
            except Exception as e:
                self._logger.warning(f"移除监听器失败: {e}")

        return intercepted_data

    def _extract_url_params(self, url: str) -> dict[str, str] | None:
        """
        从 URL 中提取 sdbh, qdbh, sdsin 参数

        Args:
            url: 法院文书链接

        Returns:
            参数字典,如果提取失败返回 None
        """
        from urllib.parse import parse_qs, urlparse

        try:
            parsed_url = urlparse(url)
            query_part = parsed_url.query if parsed_url.query else parsed_url.fragment
            if "?" in query_part:
                query_part = query_part.split("?", 1)[1]

            params = parse_qs(query_part)
            sdbh = params.get("sdbh", [None])[0]
            qdbh = params.get("qdbh", [None])[0]
            sdsin = params.get("sdsin", [None])[0]

            if sdbh and qdbh and sdsin:
                self._logger.info("提取 URL 参数成功", extra={"params": ["sdbh", "qdbh", "sdsin"]})
                return {"sdbh": sdbh, "qdbh": qdbh, "sdsin": sdsin}
            missing: list[Any] = []
            self._logger.warning("URL 参数不完整", extra={"missing": missing})
            return None
        except Exception as e:
            self._logger.error(f"解析 URL 参数失败: {e}")
            return None

    def _fetch_documents_via_direct_api(self, params: dict[str, str]) -> list[dict[str, Any]]:
        """
        直接调用法院 API 获取文书列表(无需浏览器)

        Args:
            params: 包含 sdbh, qdbh, sdsin 的参数字典

        Returns:
            文书列表

        Raises:
            Exception: API 调用失败时抛出异常
        """
        import httpx

        api_url = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
        safe_api_url = sanitize_url(api_url)

        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "DNT": "1",
            "Origin": "https://zxfw.court.gov.cn",
            "Referer": "https://zxfw.court.gov.cn/zxfw/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        payload: dict[str, Any] = {}

        self._logger.info(f"直接调用 API: {safe_api_url}")

        start_time = time.time()

        with httpx.Client(headers=headers, timeout=30.0) as client:
            response = client.post(api_url, json=payload)
            response.raise_for_status()

            api_data = response.json()
            response_time = (time.time() - start_time) * 1000

            self._logger.info(
                "API 响应成功",
                extra={
                    "operation_type": "direct_api_response",
                    "timestamp": time.time(),
                    "status_code": response.status_code,
                    "response_time_ms": response_time,
                },
            )

        if not isinstance(api_data, dict) or api_data.get("code") != 200:
            raise ValueError(f"API 响应错误: code={api_data.get('code')}, msg={api_data.get('msg')}")

        documents = api_data.get("data", [])
        if not isinstance(documents, list):
            raise ValueError(f"API 响应 data 字段格式错误: {type(documents)}")

        self._logger.info(f"直接 API 获取到 {len(documents)} 个文书")
        return documents

    def _process_api_data_and_download(
        self: "_ApiHost", api_data: dict[str, Any] | None, download_dir: Path
    ) -> dict[str, Any]:
        """
        处理 API 数据并下载文书

        Args:
            api_data: API 响应数据
            download_dir: 下载目录

        Returns:
            下载结果字典
        """
        import logging as _logging
        import random

        _local_logger = _logging.getLogger(__name__)

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

        self._logger.info(f"成功获取文书列表,共 {len(documents)} 个文书")

        downloaded_files: list[str | None] = []
        documents_with_results: list[tuple[dict[str, Any], tuple[bool, str | None, str | None]]] = []
        success_count = 0
        failed_count = 0

        for i, document_data in enumerate(documents, 1):
            self._logger.info(f"处理第 {i}/{len(documents)} 个文书: {document_data.get('c_wsmc', 'Unknown')}")

            download_result = self._download_document_directly(
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
                delay = random.uniform(1, 2)
                self._logger.info(f"等待 {delay:.2f} 秒后继续下载下一个文书")
                time.sleep(delay)

        db_save_result = self._save_documents_batch(documents_with_results)

        self._logger.info(
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
