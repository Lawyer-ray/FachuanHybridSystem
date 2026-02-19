"""
法院执行网 (zxfw.court.gov.cn) 文书下载爬虫

支持三级下载策略:
1. 优先:直接调用 API(无需浏览器,速度最快)
2. 次选:Playwright 拦截 API 响应
3. 回退:传统页面点击下载
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .base_court_scraper import BaseCourtDocumentScraper

logger = logging.getLogger("apps.automation")


class ZxfwCourtScraper(BaseCourtDocumentScraper):
    """
    法院执行网 (zxfw.court.gov.cn) 文书下载爬虫

    特点:
    - 支持三级下载策略(直接 API → API 拦截 → 页面点击)
    - 自动提取 URL 参数(sdbh, qdbh, sdsin)
    - 批量下载多个文书
    - 自动保存到数据库
    """

    def run(self) -> dict[str, Any]:
        """
        执行文书下载任务

        Returns:
            包含下载文件路径列表的字典
        """
        logger.info("=" * 60)
        logger.info("处理 zxfw.court.gov.cn 链接...")
        logger.info("=" * 60)

        # 准备下载目录
        download_dir = self._prepare_download_dir()

        # ========== 第一优先级:直接调用 API ==========
        direct_api_error = None
        try:
            logger.info(
                "尝试直接调用 API 获取文书列表(无需浏览器)",
                extra={"operation_type": "direct_api_attempt", "timestamp": time.time(), "url": self.task.url},
            )

            result = self._download_via_direct_api(self.task.url, download_dir)

            logger.info(
                "直接 API 调用成功",
                extra={
                    "operation_type": "direct_api_success",
                    "timestamp": time.time(),
                    "document_count": result.get("document_count", 0),
                    "downloaded_count": result.get("downloaded_count", 0),
                },
            )

            return result

        except Exception as e:
            direct_api_error = e
            logger.warning(
                "直接 API 调用失败,尝试 Playwright 拦截方式",
                extra={
                    "operation_type": "direct_api_failed",
                    "timestamp": time.time(),
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

        # ========== 第二优先级:Playwright 拦截 API ==========
        api_intercept_error = None
        try:
            logger.info(
                "尝试使用 Playwright API 拦截方式",
                extra={"operation_type": "api_intercept_attempt", "timestamp": time.time(), "url": self.task.url},
            )

            result = self._download_via_api_intercept_with_navigation(download_dir)
            result["method"] = "api_intercept"
            result["direct_api_error"] = {"type": type(direct_api_error).__name__, "message": str(direct_api_error)}

            logger.info(
                "Playwright API 拦截成功",
                extra={
                    "operation_type": "api_intercept_success",
                    "timestamp": time.time(),
                    "document_count": result.get("document_count", 0),
                    "downloaded_count": result.get("downloaded_count", 0),
                },
            )

            return result

        except Exception as e:
            api_intercept_error = e
            logger.warning(
                "Playwright API 拦截失败,回退到传统方式",
                extra={
                    "operation_type": "api_intercept_failed",
                    "timestamp": time.time(),
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

        # ========== 第三优先级:传统页面点击 ==========
        try:
            logger.info(
                "使用回退机制:传统页面点击下载", extra={"operation_type": "fallback_attempt", "timestamp": time.time()}
            )

            result = self._download_via_fallback(download_dir)
            result["method"] = "fallback"
            result["direct_api_error"] = {"type": type(direct_api_error).__name__, "message": str(direct_api_error)}
            result["api_intercept_error"] = {
                "type": type(api_intercept_error).__name__,
                "message": str(api_intercept_error),
            }

            logger.info(
                "回退机制执行成功",
                extra={
                    "operation_type": "fallback_success",
                    "timestamp": time.time(),
                    "downloaded_count": result.get("downloaded_count", 0),
                },
            )

            return result

        except Exception as fallback_error:
            logger.error(
                "所有下载方式均失败",
                extra={
                    "operation_type": "all_methods_failed",
                    "timestamp": time.time(),
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

    def _extract_url_params(self, url: str) -> dict[str, str] | None:
        """
        从 URL 中提取 sdbh, qdbh, sdsin 参数

        Args:
            url: 法院文书链接

        Returns:
            参数字典,如果提取失败返回 None
        """
        try:
            parsed_url = urlparse(url)
            # 参数可能在 query 或 fragment 中
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
            else:
                logger.warning(f"URL 参数不完整: sdbh={sdbh}, qdbh={qdbh}, sdsin={sdsin}")
                return None
        except Exception as e:
            logger.error(f"解析 URL 参数失败: {e}")
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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        }

        payload = {"sdbh": params.get("sdbh"), "qdbh": params.get("qdbh"), "sdsin": params.get("sdsin")}

        logger.info(f"直接调用 API: {api_url}, payload: {payload}")

        start_time = time.time()

        with httpx.Client(headers=headers, timeout=30.0) as client:
            response = client.post(api_url, json=payload)
            response.raise_for_status()

            api_data = response.json()
            response_time = (time.time() - start_time) * 1000

            logger.info(
                "API 响应成功",
                extra={
                    "operation_type": "direct_api_response",
                    "timestamp": time.time(),
                    "status_code": response.status_code,
                    "response_time_ms": response_time,
                },
            )

        # 验证响应格式
        if not isinstance(api_data, dict) or api_data.get("code") != 200:
            raise ValueError(f"API 响应错误: code={api_data.get('code')}, msg={api_data.get('msg')}")

        documents = api_data.get("data", [])
        if not isinstance(documents, list):
            raise ValueError(f"API 响应 data 字段格式错误: {type(documents)}")

        logger.info(f"直接 API 获取到 {len(documents)} 个文书")
        return documents

    def _download_document_directly(
        self, document_data: dict[str, Any], download_dir: Path, download_timeout: int = 60000
    ) -> tuple[bool, str | None, str | None]:
        """
        直接下载文书文件

        使用 httpx 直接下载 OSS 文件链接.

        Args:
            document_data: 文书数据字典,必须包含 wjlj, c_wsmc, c_wjgs 字段
            download_dir: 下载目录路径
            download_timeout: 下载超时时间(毫秒),默认 60 秒

        Returns:
            (成功标志, 文件路径, 错误信息) 的元组
            - 成功标志: True 表示下载成功,False 表示失败
            - 文件路径: 下载成功时返回本地文件路径,失败时返回 None
            - 错误信息: 下载失败时返回错误描述,成功时返回 None

        Raises:
            无异常抛出,所有错误通过返回值传递
        """
        start_time = time.time()

        try:
            # 提取下载 URL
            url = document_data.get("wjlj")
            if not url:
                error_msg = "文书数据中缺少下载链接 (wjlj)"
                logger.error(
                    error_msg,
                    extra={
                        "operation_type": "download_document_direct",
                        "timestamp": time.time(),
                        "document_data": document_data,
                    },
                )
                return False, None, error_msg

            # 构建文件名(基于 c_wsmc)
            filename_base = document_data.get("c_wsmc", "document")
            file_extension = document_data.get("c_wjgs", "pdf")

            # 清理文件名中的非法字符
            filename_base = re.sub(r'[<>:"/\\|?*]', "_", filename_base)
            filename = f"{filename_base}.{file_extension}"

            filepath = download_dir / filename

            logger.info(
                "开始直接下载文书",
                extra={
                    "operation_type": "download_document_direct_start",
                    "timestamp": time.time(),
                    "url": url,
                    "file_name": filename,
                    "timeout_ms": download_timeout,
                },
            )

            # 使用 httpx 下载文件
            try:
                import httpx

                timeout_seconds = download_timeout / 1000.0

                with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
                    response = client.get(url)
                    response.raise_for_status()

                    # 保存文件
                    with open(filepath, "wb") as f:
                        f.write(response.content)

                # 获取文件大小
                file_size = filepath.stat().st_size
                download_time = (time.time() - start_time) * 1000  # 转换为毫秒

                logger.info(
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
                error_msg = f"下载失败: {e!s}"
                download_time = (time.time() - start_time) * 1000

                logger.error(
                    error_msg,
                    extra={
                        "operation_type": "download_document_direct_failed",
                        "timestamp": time.time(),
                        "url": url,
                        "file_name": filename,
                        "download_time_ms": download_time,
                        "error": str(e),
                    },
                    exc_info=True,
                )

                return False, None, error_msg

        except Exception as e:
            error_msg = f"处理下载请求失败: {e!s}"
            logger.error(
                error_msg,
                extra={
                    "operation_type": "download_document_direct_error",
                    "timestamp": time.time(),
                    "document_data": document_data,
                },
                exc_info=True,
            )
            return False, None, error_msg

    def _download_via_direct_api(self, url: str, download_dir: Path) -> dict[str, Any]:
        """
        通过直接调用 API 下载文书(无需浏览器,速度最快)

        Args:
            url: 文书链接
            download_dir: 下载目录

        Returns:
            下载结果字典

        Raises:
            Exception: 参数提取或 API 调用失败时抛出异常
        """
        # 1. 从 URL 提取参数
        params = self._extract_url_params(url)
        if not params:
            raise ValueError("无法从 URL 中提取必要参数 (sdbh, qdbh, sdsin)")

        # 2. 直接调用 API 获取文书列表
        documents = self._fetch_documents_via_direct_api(params)

        if len(documents) == 0:
            raise ValueError("API 返回的文书列表为空")

        logger.info(f"直接 API 获取到 {len(documents)} 个文书,开始下载")

        # 3. 下载所有文书
        downloaded_files: list[str] = []
        documents_with_results: list[tuple[dict[str, Any], tuple[bool, str | None, str | None]]] = []
        success_count = 0
        failed_count = 0

        for i, document_data in enumerate(documents, 1):
            logger.info(f"下载第 {i}/{len(documents)} 个文书: {document_data.get('c_wsmc', 'Unknown')}")

            download_result = self._download_document_directly(
                document_data=document_data, download_dir=download_dir, download_timeout=60000
            )

            success, filepath, error = download_result

            if success:
                success_count += 1
                if filepath:
                    downloaded_files.append(filepath)
            else:
                failed_count += 1

            documents_with_results.append((document_data, download_result))

            # 下载延迟
            if i < len(documents):
                import random

                delay = random.uniform(0.5, 1.5)
                time.sleep(delay)

        # 4. 批量保存到数据库
        db_save_result = self._save_documents_batch(documents_with_results)

        logger.info(
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

    def _intercept_api_response_with_navigation(self, timeout: int = 30000) -> dict[str, Any] | None:
        """
        在导航前注册监听器,拦截 API 响应

        解决原有方法的问题:API 请求在页面加载时就发出,
        但监听器在页面加载后才注册,导致错过响应.

        Args:
            timeout: 超时时间(毫秒),默认 30 秒

        Returns:
            API 响应数据字典,如果超时或失败返回 None
        """
        api_url = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
        intercepted_data = None
        start_time = time.time()

        logger.info(f"开始拦截 API 响应(导航前注册),超时时间: {timeout}ms")

        def handle_response(response: Any) -> None:
            """响应处理器"""
            nonlocal intercepted_data

            # 检查是否是目标 API
            if api_url in response.url:
                try:
                    # 解析 JSON 响应
                    data = response.json()
                    intercepted_data = data

                    # 记录统计信息
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
                            "api_url": api_url,
                        },
                        exc_info=True,
                    )

        try:
            # 先注册响应监听器
            self.page.on("response", handle_response)
            logger.info(f"已注册 API 响应监听器: {api_url}")

            # 然后导航到目标页面
            self._debug_log("开始导航到目标页面")
            self.navigate_to_url()

            # 等待页面加载
            self._debug_log("等待页面加载 (networkidle)")
            self.page.wait_for_load_state("networkidle", timeout=30000)

            # 额外等待,确保 JS 渲染完成
            self._debug_log("额外等待 3 秒,确保页面完全加载")
            self.random_wait(3, 5)  # type: ignore[attr-defined]

            # 如果还没拦截到,再等待一段时间
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
                extra={
                    "operation_type": "api_intercept_error",
                    "timestamp": time.time(),
                    "error": str(e),
                    "api_url": api_url,
                },
                exc_info=True,
            )
        finally:
            # 移除监听器
            try:
                self.page.remove_listener("response", handle_response)
                logger.info("已移除 API 响应监听器")
            except Exception as e:
                logger.warning(f"移除监听器失败: {e}")

        return intercepted_data

    def _download_via_api_intercept_with_navigation(self, download_dir: Path) -> dict[str, Any]:
        """
        通过 API 拦截方式下载文书(在导航前注册监听器)

        解决原有方法的问题:API 请求在页面加载时就发出,
        但监听器在页面加载后才注册,导致错过响应.

        Args:
            download_dir: 下载目录

        Returns:
            下载结果字典

        Raises:
            Exception: API 拦截或下载失败时抛出异常
        """
        # 在导航前注册监听器并拦截 API 响应
        api_data = self._intercept_api_response_with_navigation(timeout=30000)

        # 保存页面状态(用于调试)
        self._debug_log("保存页面状态")
        self._save_page_state("zxfw_after_navigation")

        return self._process_api_data_and_download(api_data, download_dir)

    def _process_api_data_and_download(self, api_data: dict[str, Any] | None, download_dir: Path) -> dict[str, Any]:
        """
        处理 API 数据并下载文书

        Args:
            api_data: API 响应数据
            download_dir: 下载目录

        Returns:
            下载结果字典
        """

        if api_data is None:
            raise ValueError("API 拦截超时,未能获取文书列表")

        # 验证响应格式
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

        # 下载所有文书
        downloaded_files: list[str] = []
        documents_with_results: list[tuple[dict[str, Any], tuple[bool, str | None, str | None]]] = []
        success_count = 0
        failed_count = 0

        for i, document_data in enumerate(documents, 1):
            logger.info(f"处理第 {i}/{len(documents)} 个文书: {document_data.get('c_wsmc', 'Unknown')}")

            # 下载文书
            download_result = self._download_document_directly(
                document_data=document_data, download_dir=download_dir, download_timeout=60000
            )

            success, filepath, error = download_result

            if success:
                success_count += 1
                if filepath:
                    downloaded_files.append(filepath)
            else:
                failed_count += 1

            # 保存文书数据和下载结果,用于后续数据库保存
            documents_with_results.append((document_data, download_result))

            # 添加下载延迟(避免触发反爬机制)
            if i < len(documents):
                import random

                delay = random.uniform(1, 2)
                logger.info(f"等待 {delay:.2f} 秒后继续下载下一个文书")
                time.sleep(delay)

        # 批量保存到数据库
        db_save_result = self._save_documents_batch(documents_with_results)

        # 记录汇总日志
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

    def _download_via_fallback(self, download_dir: Path) -> dict[str, Any]:
        """
        通过传统页面点击方式下载文书(回退机制)

        Args:
            download_dir: 下载目录

        Returns:
            下载结果字典

        Raises:
            Exception: 下载失败时抛出异常
        """
        downloaded_files: list[str] = []
        success_count = 0
        failed_count = 0

        # 检测文书列表数量
        # 文书列表容器 XPath
        doc_list_xpath = "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view/uni-view[1]/uni-view[1]/uni-view"

        try:
            doc_items = self.page.locator(f"xpath={doc_list_xpath}").all()
            doc_count = len(doc_items)
            logger.info(f"[DEBUG] 检测到 {doc_count} 个文书项")
        except Exception as e:
            logger.warning(f"[DEBUG] 无法检测文书列表: {e},尝试单文件下载")
            doc_count = 1

        if doc_count == 0:
            # 没有检测到文书列表,尝试直接下载
            logger.info("[DEBUG] 未检测到文书列表,尝试直接下载")
            doc_count = 1

        # 逐一下载每个文书
        for doc_index in range(1, doc_count + 1):
            logger.info(f"\n{'=' * 40}")
            logger.info(f"[DEBUG] 下载第 {doc_index}/{doc_count} 个文书")
            logger.info(f"{'=' * 40}")

            try:
                # 如果有多个文书,需要先点击对应的文书项
                if doc_count > 1 or doc_index > 1:
                    # 点击文书项
                    doc_item_xpath = f"/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view/uni-view[1]/uni-view[1]/uni-view[{doc_index}]"

                    try:
                        doc_item = self.page.locator(f"xpath={doc_item_xpath}")
                        if doc_item.count() > 0:
                            doc_item.first.click()
                            logger.info(f"[DEBUG] 已点击第 {doc_index} 个文书项")
                            self.random_wait(2, 3)  # type: ignore[attr-defined]  # 等待 PDF 加载
                        else:
                            logger.warning(f"[DEBUG] 未找到第 {doc_index} 个文书项")
                    except Exception as e:
                        logger.warning(f"[DEBUG] 点击文书项失败: {e}")

                # 查找 iframe(使用 ID #if)
                frame = None
                try:
                    # 优先使用 ID 选择器
                    frame = self.page.frame_locator("#if")
                    logger.info("[DEBUG] 通过 #if 找到 iframe")
                except Exception:
                    logger.exception("操作失败")

                    pass

                if not frame:
                    # 备用:查找包含 pdfjs 的 iframe
                    iframes = self.page.locator("iframe").all()
                    for i, iframe in enumerate(iframes):
                        src = iframe.get_attribute("src") or ""
                        iframe_id = iframe.get_attribute("id") or ""
                        logger.info(f"[DEBUG] 检查 iframe {i}: id={iframe_id}, src={src[:60]}...")

                        if iframe_id == "if" or "pdfjs" in src or "viewer" in src:
                            frame = self.page.frame_locator(f"iframe >> nth={i}")
                            logger.info(f"[DEBUG] 找到 PDF viewer iframe (index {i})")
                            break

                if not frame:
                    logger.warning(f"[DEBUG] 第 {doc_index} 个文书未找到 iframe,跳过")
                    continue

                # 在 iframe 内点击下载按钮
                try:
                    # 使用 #download ID
                    btn = frame.locator("#download")
                    btn.first.wait_for(state="visible", timeout=10000)
                    btn.first.scroll_into_view_if_needed()
                    self.random_wait(1, 2)  # type: ignore[attr-defined]

                    # 监听下载
                    with self.page.expect_download(timeout=60000) as download_info:
                        btn.first.click()
                        logger.info(f"[DEBUG] 已点击第 {doc_index} 个文书的下载按钮")

                    download = download_info.value

                    # 保存文件
                    filename = download.suggested_filename or f"document_{doc_index}.pdf"
                    filepath = download_dir / filename
                    download.save_as(str(filepath))
                    logger.info(f"[DEBUG] 文件已保存: {filepath}")
                    downloaded_files.append(str(filepath))
                    success_count += 1

                except Exception as e:
                    logger.warning(f"[DEBUG] #download 方式失败: {e},尝试备用 XPath")

                    # 备用:使用原来的 XPath
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
                        downloaded_files.append(str(filepath))
                        success_count += 1

                    except Exception as e2:
                        logger.error(f"[DEBUG] 第 {doc_index} 个文书下载失败: {e2}")
                        failed_count += 1

                # 下载完成后等待一下
                self.random_wait(1, 2)  # type: ignore[attr-defined]

            except Exception as e:
                logger.error(f"[DEBUG] 处理第 {doc_index} 个文书时出错: {e}")
                failed_count += 1
                continue

        if not downloaded_files:
            # 最终失败,保存详细调试信息
            self._save_page_state("zxfw_final_failed")
            raise ValueError("所有下载策略均失败,请查看调试文件")

        # 记录汇总日志
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
