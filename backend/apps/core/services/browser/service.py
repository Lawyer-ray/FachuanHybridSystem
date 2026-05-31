"""浏览器服务单例。

进程级生命周期管理，支持多 Profile 的浏览器实例复用。
适用于高频任务场景，避免每次任务都启动/关闭浏览器。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from .profiles import BrowserProfile, get_profile

if TYPE_CHECKING:
    from playwright.async_api import Browser as AsyncBrowser
    from playwright.async_api import BrowserContext as AsyncBrowserContext
    from playwright.sync_api import Browser, BrowserContext

logger = logging.getLogger("apps.core")

class BrowserService:
    """浏览器服务单例。

    管理多个 Profile 对应的浏览器实例，提供 context 创建接口。
    """

    _instance: BrowserService | None = None
    _browsers: dict[str, tuple[Any, Any]]

    def __new__(cls) -> BrowserService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._browsers = {}
        return cls._instance

    def get_context(
        self,
        profile: str | BrowserProfile = "default",
        *,
        use_anti_detection: bool = True,
        **kwargs: Any,
    ) -> BrowserContext:
        """获取同步浏览器上下文。

        Args:
            profile: 配置档案名称或实例
            use_anti_detection: 是否应用反检测
            **kwargs: 传递给 new_context 的额外参数

        Returns:
            BrowserContext 实例
        """
        if isinstance(profile, str):
            profile = get_profile(profile)

        pw, browser = self._get_or_create_browser(profile)

        # 构建 context 参数
        context_args = profile.to_context_args()
        if use_anti_detection and profile.anti_detection:
            from .anti_detection import anti_detection

            anti_opts = anti_detection.get_context_options()
            anti_opts.update(context_args)
            context_args = anti_opts

        context_args.update(kwargs)
        context = browser.new_context(**context_args)

        # 设置超时
        context.set_default_timeout(profile.timeout)
        context.set_default_navigation_timeout(profile.navigation_timeout)

        # 注入 stealth
        if use_anti_detection and profile.anti_detection:
            from .anti_detection import anti_detection

            anti_detection.apply_stealth(context)

        return cast(BrowserContext, context)

    def _get_or_create_browser(self, profile: BrowserProfile) -> tuple[Any, Any]:
        """获取或创建浏览器实例。"""
        if profile.name in self._browsers:
            pw, browser = self._browsers[profile.name]
            return pw, browser

        from playwright.sync_api import sync_playwright

        logger.info("创建浏览器实例 (profile=%s)", profile.name)
        pw = sync_playwright().start()
        launch_args = profile.to_launch_args()
        browser = pw.chromium.launch(**launch_args)

        self._browsers[profile.name] = (pw, browser)
        return pw, browser

    def close(self, profile: str | None = None) -> None:
        """关闭浏览器实例。

        Args:
            profile: 指定关闭某个 profile 的浏览器，None 则关闭所有
        """
        if profile:
            if profile in self._browsers:
                pw, browser = self._browsers.pop(profile)
                browser.close()
                pw.stop()
                logger.info("浏览器已关闭 (profile=%s)", profile)
        else:
            for name, (pw, browser) in list(self._browsers.items()):
                try:
                    browser.close()
                    pw.stop()
                except Exception as e:
                    logger.warning("关闭浏览器失败 (profile=%s): %s", name, e)
            self._browsers.clear()
            logger.info("所有浏览器已关闭")

    @classmethod
    def reset(cls) -> None:
        """重置单例（用于测试）。"""
        if cls._instance:
            cls._instance.close()
            cls._instance = None

def get_browser_service() -> BrowserService:
    """获取浏览器服务单例。"""
    return BrowserService()
