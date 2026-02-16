"""Business logic services."""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol

from playwright.sync_api import BrowserContext, Page

from apps.automation.utils.logging_mixins.common import sanitize_url

from .court_zxfw_token_extractors import (
    extract_baoquan_token_from_authorization_json,
    extract_token_from_url_query,
    is_hs512_jwt,
)

logger = logging.getLogger("apps.automation")


class ScreenshotSaver(Protocol):
    def __call__(self, name: str) -> str: ...


class BaoquanTokenFetcher:
    BAOQUAN_URL = "https://zxfw.court.gov.cn/zxfw/#/pagesOther/common/wsdb/index"
    BAOQUAN_SITE_NAME = "court_baoquan"

    def __init__(self, *, page: Page, context: BrowserContext, save_screenshot: ScreenshotSaver | None = None) -> None:
        self.page = page
        self.context = context
        self._save_screenshot = save_screenshot

    def fetch(self, *, save_debug: bool = False) -> dict[str, Any]:
        logger.info("=" * 60)
        logger.info("开始获取保全系统 Token (HS512)...")
        logger.info("=" * 60)

        captured_token: dict[str, str | None] = {"value": None}

        handler = self._make_response_handler(captured_token)  # type: ignore[func-returns-value]

        try:
            self.page.on("response", handler)

            logger.info(f"导航到文书送达页面: {sanitize_url(self.BAOQUAN_URL)}")
            with self.page.expect_response(
                lambda response: "/api/info?token=" in response.url and "eyJhbGciOiJIUzUxMiJ9" in response.url,
                timeout=30000,
            ) as response_info:
                self.page.goto(self.BAOQUAN_URL, timeout=30000)

            response = response_info.value
            url = response.url
            logger.info(f"📡 捕获到 info 请求: {sanitize_url(url)}")

            token = extract_token_from_url_query(url, param="token")
            if token and is_hs512_jwt(token):
                captured_token["value"] = token
                logger.info("✅ 从 info URL 参数捕获到保全 Token")

            time.sleep(2)

            if save_debug and self._save_screenshot:
                self._save_screenshot("baoquan_page")

            self.page.remove_listener("response", handler)

            return self._build_token_result(captured_token["value"], save_debug)
        except Exception as e:
            logger.exception("获取保全 Token 失败", extra={"error": str(e)})
            if save_debug and self._save_screenshot:
                self._save_screenshot("baoquan_error")
            raise

    def _make_response_handler(self, captured_token: dict[str, str | None]) -> None:
        """创建 Playwright 响应事件处理器"""

        def handle_response(response) -> None:  # type: ignore
            try:
                url = response.url

                if "baoquan" in url.lower():
                    logger.info(f"🌐 保全系统请求: {sanitize_url(url)} (状态: {response.status})")

                    if "/api/info?token=" in url and "eyJhbGciOiJIUzUxMiJ9" in url:
                        token = extract_token_from_url_query(url, param="token")
                        if token and is_hs512_jwt(token):
                            captured_token["value"] = token
                            logger.info("✅ 从 info URL 参数捕获到保全 Token")
                            return

                self._try_capture_authorization_token(response, captured_token)
            except Exception:
                logger.exception("处理保全响应失败")

        return handle_response  # type: ignore[return-value]

    def _try_capture_authorization_token(self, response: Any, captured_token: dict[str, str | None]) -> None:
        """尝试从 getauthorization 接口捕获 Token"""
        url = response.url
        if "getauthorization" not in url.lower() or response.status != 200:
            return

        logger.info(f"📡 捕获到 getauthorization 接口: {sanitize_url(url)}")
        try:
            response_text = response.text()
            logger.info(f"📄 响应内容长度: {len(response_text)}")

            import json

            response_body = json.loads(response_text)
            token = extract_baoquan_token_from_authorization_json(response_body)
            if token:
                captured_token["value"] = token
                logger.info("✅ 从 getauthorization 响应捕获到保全 Token")
        except Exception:
            logger.exception("解析 getauthorization 响应失败")

    def _build_token_result(self, token: str | None, save_debug: bool) -> dict[str, Any]:
        """根据捕获的 Token 构建返回结果"""
        if token:
            logger.info("✅ 保全 Token 获取成功!")
            return {
                "success": True,
                "message": "保全 Token 获取成功",
                "token": token,
                "site_name": self.BAOQUAN_SITE_NAME,
            }

        logger.error("❌ 未能获取保全 Token")
        if save_debug and self._save_screenshot:
            self._save_screenshot("baoquan_token_failed")
        raise ValueError("未能获取保全系统 Token")
