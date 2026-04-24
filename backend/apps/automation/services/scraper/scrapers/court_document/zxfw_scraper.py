"""
法院执行网 (zxfw.court.gov.cn) 文书下载爬虫

支持三级下载策略:
1. 优先:直接调用 API(无需浏览器,速度最快)
2. 次选:Playwright 拦截 API 响应
3. 回退:传统页面点击下载

当 Playwright 未安装时，仅使用策略 1（纯 API），策略 2/3 不可用。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from django.utils.translation import gettext_lazy as _

from ._zxfw_direct_api_mixin import ZxfwDirectApiMixin
from ._zxfw_fallback_mixin import ZxfwFallbackMixin
from ._zxfw_intercept_mixin import ZxfwInterceptMixin
from .base_court_scraper import BaseCourtDocumentScraper

logger = logging.getLogger("apps.automation")


def _is_playwright_available() -> bool:
    """检查 Playwright 是否已安装"""
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


class ZxfwCourtScraper(ZxfwDirectApiMixin, ZxfwInterceptMixin, ZxfwFallbackMixin, BaseCourtDocumentScraper):  # type: ignore
    """
    法院执行网 (zxfw.court.gov.cn) 文书下载爬虫

    特点:
    - 支持三级下载策略(直接 API → API 拦截 → 页面点击)
    - Playwright 未安装时仅使用纯 API 策略
    - 自动提取 URL 参数(sdbh, qdbh, sdsin)
    - 批量下载多个文书
    - 自动保存到数据库
    """

    # 一张网优先走纯 API，不强制要求浏览器
    requires_browser = False

    def run(self) -> dict[str, Any]:
        """执行文书下载任务"""
        logger.info("=" * 60)
        logger.info("处理 zxfw.court.gov.cn 链接...")
        logger.info("=" * 60)

        download_dir: Path = self._prepare_download_dir()
        playwright_available = _is_playwright_available()

        # ========== 第一优先级:直接调用 API（无需浏览器）==========
        direct_api_error: Exception | None = None
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
                "直接 API 调用失败%s",
                "，尝试 Playwright 拦截方式" if playwright_available else "，且 Playwright 未安装，无法降级",
                extra={
                    "operation_type": "direct_api_failed",
                    "timestamp": time.time(),
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

        # ========== Playwright 未安装时直接报错 ==========
        if not playwright_available:
            from apps.core.exceptions import ExternalServiceError

            raise ExternalServiceError(
                message=_("直接 API 调用失败，且 Playwright 未安装无法降级到浏览器模式"),
                code="DOWNLOAD_API_FAILED_NO_PLAYWRIGHT",
                errors={
                    "direct_api_error": str(direct_api_error),
                    "hint": "安装 Playwright 可增加降级策略: uv add playwright && playwright install chromium",
                },
            )

        # ========== 第二优先级:Playwright 拦截 API ==========
        api_intercept_error: Exception | None = None
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
                "使用回退机制:传统页面点击下载",
                extra={"operation_type": "fallback_attempt", "timestamp": time.time()},
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
                message=_("所有下载方式均失败"),
                code="DOWNLOAD_ALL_METHODS_FAILED",
                errors={
                    "direct_api_error": str(direct_api_error),
                    "api_intercept_error": str(api_intercept_error),
                    "fallback_error": str(fallback_error),
                },
            ) from fallback_error
