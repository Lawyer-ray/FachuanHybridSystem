"""zxfw 直接 API 下载 Mixin"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("apps.automation")


class ZxfwDirectApiMixin:
    """直接调用 API 下载文书（无需浏览器）"""

    def _extract_url_params(self, url: str) -> dict[str, str] | None:
        """从 URL 中提取 sdbh, qdbh, sdsin 参数"""
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
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
            ),
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
        """直接下载文书文件，返回 (成功标志, 文件路径, 错误信息)"""
        start_time = time.time()
        try:
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
            filename_base = re.sub(r'[<>:"/\\|?*]', "_", document_data.get("c_wsmc", "document"))
            file_extension = document_data.get("c_wjgs", "pdf")
            filename = f"{filename_base}.{file_extension}"
            filepath = download_dir / filename
            logger.info(
                "开始直接下载文书",
                extra={
                    "operation_type": "download_document_direct_start",
                    "timestamp": time.time(),
                    "url": url,
                    "file_name": filename,
                },
            )
            try:
                import httpx

                with httpx.Client(timeout=download_timeout / 1000.0, follow_redirects=True) as client:
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
                        "timestamp": time.time(),
                        "file_name": filename,
                        "file_size": file_size,
                        "download_time_ms": download_time,
                    },
                )
                return True, str(filepath), None
            except Exception as e:
                error_msg = f"下载失败: {e!s}"
                logger.error(
                    error_msg,
                    extra={
                        "operation_type": "download_document_direct_failed",
                        "timestamp": time.time(),
                        "url": url,
                        "file_name": filename,
                        "download_time_ms": (time.time() - start_time) * 1000,
                    },
                    exc_info=True,
                )
                return False, None, error_msg
        except Exception as e:
            error_msg = f"处理下载请求失败: {e!s}"
            logger.error(
                error_msg,
                extra={"operation_type": "download_document_direct_error", "timestamp": time.time()},
                exc_info=True,
            )
            return False, None, error_msg

    def _download_via_direct_api(self, url: str, download_dir: Path) -> dict[str, Any]:
        """通过直接调用 API 下载文书（无需浏览器，速度最快）"""
        params = self._extract_url_params(url)
        if not params:
            raise ValueError("无法从 URL 中提取必要参数 (sdbh, qdbh, sdsin)")
        documents = self._fetch_documents_via_direct_api(params)
        if len(documents) == 0:
            raise ValueError("API 返回的文书列表为空")
        logger.info(f"直接 API 获取到 {len(documents)} 个文书,开始下载")
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
            if success:
                success_count += 1
                if filepath:
                    downloaded_files.append(filepath)
            else:
                failed_count += 1
            documents_with_results.append((document_data, download_result))
            if i < len(documents):
                import random

                time.sleep(random.uniform(0.5, 1.5))
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
