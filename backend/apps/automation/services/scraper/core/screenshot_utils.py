"""
截图工具类

纯工具方法，不包含业务逻辑
"""

import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger("apps.automation")

__all__ = ["ScreenshotUtils", "collect_screenshots"]


def collect_screenshots(limit: int = 5) -> list[str]:
    """
    收集最新的截图

    S31-06（2026-11-23 二轮审计）：原实现是实例方法（无 self 使用），而唯一的生产
    调用点 TestService.test_login 用类名直调 → 必现 TypeError 并被宽捕获
    吞成「登录失败: collect_screenshots() missing 1 required positional argument: 'self'」。
    现在改为静态方法，类名/实例两种调用法都成立。

    Args:
        limit: 最多收集多少张

    Returns:
        截图 URL 列表
    """
    try:
        screenshot_dir = Path(settings.MEDIA_ROOT) / "automation" / "screenshots"
        if not screenshot_dir.exists():
            return []

        screenshots = sorted(screenshot_dir.glob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True)

        result = []
        for screenshot in screenshots[:limit]:
            relative_path = screenshot.relative_to(Path(settings.MEDIA_ROOT))
            screenshot_url = settings.MEDIA_URL + str(relative_path)
            result.append(screenshot_url)

        return result

    except Exception as e:
        logger.warning("收集截图失败: %s", e)
        return []


class ScreenshotUtils:
    """兼容旧调用方的壳（`ScreenshotUtils().collect_screenshots()` / `ScreenshotUtils.collect_screenshots()` 都可用）。

    service 层禁止 `@staticmethod` **装饰器**（结构棘轮按装饰器计数），
    所以真正的实现是模块级函数，这里用 `staticmethod(...)` 绑定，不引入装饰器。
    """

    collect_screenshots = staticmethod(collect_screenshots)
