"""反检测配置。

提供浏览器反检测能力：随机 User-Agent、viewport 伪装、stealth 脚本注入。
"""

from __future__ import annotations

import logging
import random
from typing import Any, ClassVar

logger = logging.getLogger("apps.core")


class AntiDetection:
    """反检测工具。"""

    USER_AGENTS: ClassVar[list[str]] = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    def get_random_user_agent(self) -> str:
        return random.choice(self.USER_AGENTS)

    def get_context_options(self) -> dict[str, Any]:
        """返回反检测的浏览器上下文配置。"""
        return {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": self.get_random_user_agent(),
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "geolocation": {"longitude": 113.264385, "latitude": 23.129112},
            "permissions": ["geolocation"],
            "extra_http_headers": {
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            },
        }

    def apply_stealth(self, context: Any) -> None:
        """对 context 应用 playwright-stealth 反检测。"""
        try:
            from playwright_stealth import Stealth

            stealth = Stealth()
            stealth.apply_stealth_sync(context)
            logger.debug("已应用 playwright-stealth 反检测")
        except ImportError:
            logger.warning("playwright-stealth 未安装，跳过 stealth 注入")

    async def apply_stealth_async(self, context: Any) -> None:
        """异步版本：对 context 应用 playwright-stealth 反检测。"""
        try:
            from playwright_stealth import Stealth

            stealth = Stealth()
            await stealth.apply_stealth_async(context)
            logger.debug("已应用 playwright-stealth 反检测（async）")
        except ImportError:
            logger.warning("playwright-stealth 未安装，跳过 stealth 注入")


# 全局实例
anti_detection = AntiDetection()
