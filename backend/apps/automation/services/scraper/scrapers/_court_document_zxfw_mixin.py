"""法院文书爬虫 — zxfw.court.gov.cn 下载 Mixin"""

import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("apps.automation")

_ZXFW_API_URL = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
_ZXFW_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "DNT": "1",
    "Origin": "https://zxfw.court.gov.cn",
    "Referer": "https://zxfw.court.gov.cn/zxfw/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    ),
}


class CourtDocumentZxfwMixin:
    """zxfw.court.gov.cn 文书下载相关方法"""

    # 子类提供
    def _prepare_download_dir(self) -> Path: ...
    def _save_page_state(self, name: str) -> dict[str, Any]: ...
    def _debug_log(self, message: str, data: Any = None) -> None: ...
    def _save_documents_batch(
        self,
        documents_with_results: list[tuple[dict[str, Any], tuple[bool, str | None, str | None]]],
    ) -> dict[str, Any]: ...
    def navigate_to_url(self) -> None: ...
    def random_wait(self, min_s: float, max_s: float) -> None: ...

    # ==================== API 拦截 ====================

    def _intercept_api_response_with_navigation(self, timeout: int = 30000) -> dict[str, Any] | None:
        """在导航前注册监听器，拦截 API 响应"""
        intercepted_data: dict[str, Any] | None = None
        start_time = time.time()
        logger.info(f"开始拦截 API 响应（导航前注册），超时时间: {timeout}ms")

        def handle_response(response: Any) -> None:
            nonlocal intercepted_data
            if _ZXFW_API_URL in response.url:
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
                        },
                    )
                except Exception as e:
                    logger.error(f"解析 API 响应失败: {e}", exc_info=True)

        try:
            self.page.on("response", handle_response)
            self._debug_log("开始导航到目标页面")
            self.navigate_to_url()
            self._debug_log("等待页面加载 (networkidle)")
            self.page.wait_for_load_state("networkidle", timeout=30000)
            self._debug_log("额外等待 3 秒，确保页面完全加载")
            self.random_wait(3, 5)
            if intercepted_data is None:
                timeout_seconds = timeout / 1000.0
                elapsed = 0.0
                logger.info("API 响应尚未拦截到，继续等待...")
                while intercepted_data is None and elapsed < timeout_seconds:
                    time.sleep(0.5)
                    elapsed += 0.5
                if intercepted_data is None:
                    logger.warning(
                        "API 拦截超时",
                        extra={"operation_type": "api_intercept_timeout", "timeout_ms": timeout},
                    )
        except Exception as e:
            logger.error(f"API 拦截过程出错: {e}", exc_info=True)
        finally:
            try:
                self.page.remove_listener("response", handle_response)
                logger.info("已移除 API 响应监听器")
            except Exception as e:
                logger.warning(f"移除监听器失败: {e}")
        return intercepted_data

    def _intercept_api_response(self, timeout: int = 30000) -> dict[str, Any] | None:
        """拦截 API 响应（页面加载后注册，可能错过响应）"""
        intercepted_data: dict[str, Any] | None = None
        start_time = time.time()
        logger.info(f"开始拦截 API 响应，超时时间: {timeout}ms")

        def handle_response(response: Any) -> None:
            nonlocal intercepted_data
            if _ZXFW_API_URL in response.url:
                try:
                    intercepted_data = response.json()
                    document_count = len(intercepted_data.get("data", []))
                    logger.info(
                        "成功拦截 API 响应",
                        extra={
                            "operation_type": "api_intercept",
                            "timestamp": time.time(),
                            "document_count": document_count,
                            "response_time_ms": (time.time() - start_time) * 1000,
                        },
                    )
                except Exception as e:
                    logger.error(f"解析 API 响应失败: {e}", exc_info=True)

        try:
            self.page.on("response", handle_response)
            timeout_seconds = timeout / 1000.0
            elapsed = 0.0
            while intercepted_data is None and elapsed < timeout_seconds:
                time.sleep(0.1)
                elapsed += 0.1
            if intercepted_data is None:
                logger.warning("API 拦截超时", extra={"operation_type": "api_intercept_timeout", "timeout_ms": timeout})
        except Exception as e:
            logger.error(f"API 拦截过程出错: {e}", exc_info=True)
        finally:
            try:
                self.page.remove_listener("response", handle_response)
            except Exception as e:
                logger.warning(f"移除监听器失败: {e}")
        return intercepted_data

    # ==================== 直接下载 ====================

    def _download_document_directly(
        self,
        document_data: dict[str, Any],
        download_dir: Path,
        download_timeout: int = 60000,
    ) -> tuple[bool, str | None, str | None]:
        """使用 httpx 直接下载文书文件"""
        import httpx

        start_time = time.time()
        try:
            url = document_data.get("wjlj")
            if not url:
                return False, None, "文书数据中缺少下载链接 (wjlj)"
            filename_base = re.sub(r'[<>:"/\\|?*]', "_", document_data.get("c_wsmc", "document"))
            file_extension = document_data.get("c_wjgs", "pdf")
            filename = f"{filename_base}.{file_extension}"
            filepath = download_dir / filename
            logger.info(
                "开始直接下载文书",
                extra={
                    "operation_type": "download_document_direct_start",
                    "url": url,
                    "file_name": filename,
                },
            )
            try:
                timeout_seconds = download_timeout / 1000.0
                with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
                    response = client.get(url)
                    response.raise_for_status()
                    with open(filepath, "wb") as f:
                        f.write(response.content)
                file_size = filepath.stat().st_size
                download_time = (time.time() - start_time) * 1000
                logger.info(
                    "文书下载成功",
                    extra={
                        "operation_type": "download_document_direct_success",
                        "file_name": filename,
                        "file_size": file_size,
                        "download_time_ms": download_time,
                        "file_path": str(filepath),
                    },
                )
                return True, str(filepath), None
            except Exception as e:
                error_msg = f"下载失败: {e!s}"
                logger.error(
                    error_msg,
                    extra={"operation_type": "download_document_direct_failed", "url": url},
                    exc_info=True,
                )
                return False, None, error_msg
        except Exception as e:
            error_msg = f"处理下载请求失败: {e!s}"
            logger.error(error_msg, exc_info=True)
            return False, None, error_msg

    # ==================== URL 参数提取 ====================

    def _extract_url_params(self, url: str) -> dict[str, str] | None:
        """从 URL 中提取 sdbh, qdbh, sdsin 参数"""
        from urllib.parse import parse_qs

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
                logger.info(f"提取 URL 参数成功: sdbh={sdbh}, qdbh={qdbh}, sdsin={sdsin}")
                return {"sdbh": sdbh, "qdbh": qdbh, "sdsin": sdsin}
            logger.warning(f"URL 参数不完整: sdbh={sdbh}, qdbh={qdbh}, sdsin={sdsin}")
            return None
        except Exception as e:
            logger.error(f"解析 URL 参数失败: {e}")
            return None

    def _fetch_documents_via_direct_api(self, params: dict[str, str]) -> list[dict[str, Any]]:
        """直接调用法院 API 获取文书列表（无需浏览器）"""
        import httpx

        payload = {"sdbh": params.get("sdbh"), "qdbh": params.get("qdbh"), "sdsin": params.get("sdsin")}
        logger.info(f"直接调用 API: {_ZXFW_API_URL}, payload: {payload}")
        start_time = time.time()
        with httpx.Client(headers=_ZXFW_HEADERS, timeout=30.0) as client:
            response = client.post(_ZXFW_API_URL, json=payload)
            response.raise_for_status()
            api_data = response.json()
            response_time = (time.time() - start_time) * 1000
            logger.info(
                "API 响应成功",
                extra={"operation_type": "direct_api_response", "response_time_ms": response_time},
            )
        if not isinstance(api_data, dict) or api_data.get("code") != 200:
            raise ValueError(f"API 响应错误: code={api_data.get('code')}, msg={api_data.get('msg')}")
        documents = api_data.get("data", [])
        if not isinstance(documents, list):
            raise ValueError(f"API 响应 data 字段格式错误: {type(documents)}")
        logger.info(f"直接 API 获取到 {len(documents)} 个文书")
        return documents

    # ==================== 下载策略 ====================

    def _download_via_direct_api(self, url: str, download_dir: Path) -> dict[str, Any]:
        """通过直接调用 API 下载文书（无需浏览器，速度最快）"""
        import random

        params = self._extract_url_params(url)
        if not params:
            raise ValueError("无法从 URL 中提取必要参数 (sdbh, qdbh, sdsin)")
        documents = self._fetch_documents_via_direct_api(params)
        if len(documents) == 0:
            raise ValueError("API 返回的文书列表为空")
        logger.info(f"直接 API 获取到 {len(documents)} 个文书，开始下载")
        downloaded_files: list[str] = []
        documents_with_results: list[tuple[dict[str, Any], tuple[bool, str | None, str | None]]] = []
        success_count = 0
        failed_count = 0
        for i, document_data in enumerate(documents, 1):
            logger.info(f"下载第 {i}/{len(documents)} 个文书: {document_data.get('c_wsmc', 'Unknown')}")
            download_result = self._download_document_directly(
                document_data=document_data, download_dir=download_dir, download_timeout=60000
            )
            success, filepath, _ = download_result
            if success and filepath:
                success_count += 1
                downloaded_files.append(filepath)
            else:
                failed_count += 1
            documents_with_results.append((document_data, download_result))
            if i < len(documents):
                time.sleep(random.uniform(0.5, 1.5))
        db_save_result = self._save_documents_batch(documents_with_results)
        logger.info(
            "直接 API 方式下载完成",
            extra={
                "operation_type": "direct_api_download_summary",
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
            "message": f"直接 API 方式：成功下载 {success_count}/{len(documents)} 份文书",
        }

    def _download_via_api_intercept_with_navigation(self, download_dir: Path) -> dict[str, Any]:
        """通过 API 拦截方式下载文书（在导航前注册监听器）"""
        api_data = self._intercept_api_response_with_navigation(timeout=30000)
        self._debug_log("保存页面状态")
        self._save_page_state("zxfw_after_navigation")
        return self._process_api_data_and_download(api_data, download_dir)

    def _download_via_api_intercept(self, download_dir: Path) -> dict[str, Any]:
        """通过 API 拦截方式下载文书（已废弃，保留用于回退）"""
        api_data = self._intercept_api_response(timeout=30000)
        return self._process_api_data_and_download(api_data, download_dir)

    def _process_api_data_and_download(self, api_data: dict[str, Any] | None, download_dir: Path) -> dict[str, Any]:
        """处理 API 数据并下载文书"""
        import random

        if api_data is None:
            raise ValueError("API 拦截超时，未能获取文书列表")
        if not isinstance(api_data, dict):
            raise ValueError(f"API 响应格式错误：期望 dict，实际 {type(api_data)}")
        if "data" not in api_data:
            raise ValueError("API 响应缺少 data 字段")
        documents = api_data.get("data", [])
        if not isinstance(documents, list):
            raise ValueError(f"API 响应 data 字段格式错误：期望 list，实际 {type(documents)}")
        if len(documents) == 0:
            raise ValueError("API 响应中没有文书数据")
        logger.info(f"成功获取文书列表，共 {len(documents)} 个文书")
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
            if success and filepath:
                success_count += 1
                downloaded_files.append(filepath)
            else:
                failed_count += 1
            documents_with_results.append((document_data, download_result))
            if i < len(documents):
                delay = random.uniform(1, 2)
                logger.info(f"等待 {delay:.2f} 秒后继续下载下一个文书")
                time.sleep(delay)
        db_save_result = self._save_documents_batch(documents_with_results)
        logger.info(
            "文书下载完成",
            extra={
                "operation_type": "download_summary",
                "total_count": len(documents),
                "success_count": success_count,
                "failed_count": failed_count,
                "db_saved_count": db_save_result.get("success", 0),
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
            "message": f"API 拦截方式：成功下载 {success_count}/{len(documents)} 份文书",
        }

    def _try_click_download(self, timeout: int = 30000) -> Any:
        """尝试多种方式点击下载按钮"""
        strategies = [
            {"name": "ID #download", "locator": "#download"},
            {"name": "文本 '下载'", "locator": "text=下载"},
            {"name": "按钮角色", "locator": "button:has-text('下载')"},
            {"name": "链接", "locator": "a:has-text('下载')"},
            {"name": "可点击元素", "locator": "[onclick*='download'], [href*='download']"},
        ]
        for strategy in strategies:
            try:
                logger.info(f"[DEBUG] 尝试策略: {strategy['name']}")
                locator = self.page.locator(strategy["locator"]).first
                if locator.count() == 0 or not locator.is_visible():
                    continue
                locator.scroll_into_view_if_needed()
                self.random_wait(0.5, 1)
                with self.page.expect_download(timeout=timeout) as download_info:
                    locator.click()
                download = download_info.value
                logger.info(f"[DEBUG] 策略 {strategy['name']}: 下载成功！文件: {download.suggested_filename}")
                return download
            except Exception as e:
                logger.warning(f"[DEBUG] 策略 {strategy['name']} 失败: {e}")
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
            doc_items = self.page.locator(f"xpath={doc_list_xpath}").all()
            doc_count = len(doc_items)
            logger.info(f"[DEBUG] 检测到 {doc_count} 个文书项")
        except Exception as e:
            logger.warning(f"[DEBUG] 无法检测文书列表: {e}，尝试单文件下载")
            doc_count = 1
        if doc_count == 0:
            doc_count = 1
        for doc_index in range(1, doc_count + 1):
            logger.info(f"[DEBUG] 下载第 {doc_index}/{doc_count} 个文书")
            try:
                self._click_doc_item_legacy(doc_index, doc_count)
                frame = self._find_pdf_iframe_legacy()
                if not frame:
                    logger.warning(f"[DEBUG] 第 {doc_index} 个文书未找到 iframe，跳过")
                    failed_count += 1
                    continue
                filepath = self._download_single_doc_legacy(frame, doc_index, download_dir)
                if filepath:
                    downloaded_files.append(filepath)
                    success_count += 1
                else:
                    failed_count += 1
                self.random_wait(1, 2)
            except Exception as e:
                logger.error(f"[DEBUG] 处理第 {doc_index} 个文书时出错: {e}")
                failed_count += 1
        if not downloaded_files:
            self._save_page_state("zxfw_final_failed")
            raise ValueError("所有下载策略均失败，请查看调试文件")
        return {
            "source": "zxfw.court.gov.cn",
            "document_count": doc_count,
            "downloaded_count": success_count,
            "failed_count": failed_count,
            "files": downloaded_files,
            "message": f"回退方式：成功下载 {success_count}/{doc_count} 份文书",
        }

    def _download_zxfw_court(self, url: str) -> dict[str, Any]:
        """下载 zxfw.court.gov.cn 的文书（三级降级策略）"""
        logger.info("=" * 60)
        logger.info("处理 zxfw.court.gov.cn 链接...")
        logger.info("=" * 60)
        download_dir = self._prepare_download_dir()

        # 第一优先级：直接调用 API
        direct_api_error: Exception | None = None
        try:
            result = self._download_via_direct_api(url, download_dir)
            logger.info("直接 API 调用成功", extra={"operation_type": "direct_api_success"})
            return result
        except Exception as e:
            direct_api_error = e
            logger.warning(f"直接 API 调用失败，尝试 Playwright 拦截方式: {e}")

        # 第二优先级：Playwright 拦截 API
        api_intercept_error: Exception | None = None
        try:
            result = self._download_via_api_intercept_with_navigation(download_dir)
            result["method"] = "api_intercept"
            result["direct_api_error"] = {"type": type(direct_api_error).__name__, "message": str(direct_api_error)}
            logger.info("Playwright API 拦截成功", extra={"operation_type": "api_intercept_success"})
            return result
        except Exception as e:
            api_intercept_error = e
            logger.warning(f"Playwright API 拦截失败，回退到传统方式: {e}")

        # 第三优先级：传统页面点击
        try:
            result = self._download_via_fallback(download_dir)
            result["method"] = "fallback"
            result["direct_api_error"] = {"type": type(direct_api_error).__name__, "message": str(direct_api_error)}
            result["api_intercept_error"] = {
                "type": type(api_intercept_error).__name__,
                "message": str(api_intercept_error),
            }
            logger.info("回退机制执行成功", extra={"operation_type": "fallback_success"})
            return result
        except Exception as fallback_error:
            logger.error(
                "所有下载方式均失败",
                extra={
                    "operation_type": "all_methods_failed",
                    "direct_api_error": str(direct_api_error),
                    "api_intercept_error": str(api_intercept_error),
                    "fallback_error": str(fallback_error),
                },
                exc_info=True,
            )
            from apps.core.exceptions import ExternalServiceError

            raise ExternalServiceError(
                message="所有下载方式均失败",
                code="DOWNLOAD_ALL_METHODS_FAILED",
                errors={
                    "direct_api_error": str(direct_api_error),
                    "api_intercept_error": str(api_intercept_error),
                    "fallback_error": str(fallback_error),
                },
            ) from fallback_error
