"""
浏览器服务 - 单例模式管理 Playwright 浏览器实例
"""

import logging
import os
import subprocess
import sys
from typing import Any, Optional, cast

from playwright.sync_api import Browser, BrowserContext, Playwright, sync_playwright

from apps.core.interfaces import IBrowserService

logger = logging.getLogger("apps.automation")

_PLAYWRIGHT_INSTALL_CMD = [sys.executable, "-m", "playwright", "install", "chromium"]


def _ensure_browser_installed() -> None:
    """
    检测 Playwright 浏览器是否已安装，若缺失则自动安装。

    场景：Playwright Python 包升级后，新版期望的 chromium 路径变化
    （如 chromium_headless_shell-1208），但旧镜像中只有旧版路径。
    此函数在启动浏览器前调用，避免因浏览器二进制缺失导致任务失败。
    """
    from pathlib import Path

    try:
        # playwright 内部通过 PLAYWRIGHT_BROWSERS_PATH 环境变量或默认缓存目录定位浏览器
        browsers_path = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / ".cache" / "ms-playwright")))
        if browsers_path.exists():
            # 检查是否有 chromium 相关目录
            chromium_dirs = list(browsers_path.glob("chromium*"))
            if chromium_dirs:
                return  # 浏览器已安装

        logger.warning("未检测到 Playwright chromium 浏览器，尝试安装...")
        subprocess.run(
            _PLAYWRIGHT_INSTALL_CMD,
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Playwright chromium 安装完成")
    except Exception as e:
        logger.warning("浏览器安装检测异常: %s，尝试直接安装...", e)
        try:
            subprocess.run(
                _PLAYWRIGHT_INSTALL_CMD,
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("Playwright chromium 安装完成")
        except subprocess.CalledProcessError as install_err:
            logger.error("Playwright chromium 自动安装失败: %s", install_err.stderr)


class BrowserService:
    """
    浏览器服务单例

    全局复用 Browser 实例，每个任务创建独立的 Context
    """

    _instance: Optional["BrowserService"] = None
    _playwright: Playwright | None = None
    _browser: Browser | None = None

    def __new__(cls) -> "BrowserService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # 避免重复初始化
        if not hasattr(self, "_initialized"):
            self._initialized = True
            logger.info("BrowserService 初始化")

    def start_browser(self, headless: bool | None = None) -> Browser:
        """
        启动浏览器（如果尚未启动）

        Args:
            headless: 是否无头模式（None 则从配置读取，默认开发环境 False，生产环境 True）

        Returns:
            Browser 实例
        """
        if self._browser is None:
            if headless is None:
                from apps.core.services.system_config_service import SystemConfigService

                svc = SystemConfigService()
                raw = svc.get_value("SCRAPER_HEADLESS", "")
                if raw:
                    headless = raw.lower() in ("true", "1", "yes")
                else:
                    # 默认：生产环境无头，开发环境有头
                    debug_raw = svc.get_value("DEBUG_MODE", "false")
                    headless = debug_raw.lower() not in ("true", "1", "yes")

            mode = "无头" if headless else "有头"
            logger.info(f"启动 Playwright 浏览器（{mode}模式）...")

            # 启动前确保浏览器二进制已安装（处理版本升级导致的路径不匹配）
            _ensure_browser_installed()

            self._playwright = sync_playwright().start()

            launch_options: dict[str, Any] = {
                "headless": headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",  # 反爬虫检测
                    "--no-sandbox",
                ],
            }

            # 开发模式下减慢操作速度，方便观察
            if not headless:
                launch_options["slow_mo"] = 500

            try:
                self._browser = self._playwright.chromium.launch(**launch_options)
                logger.info(f"浏览器启动成功（{mode}模式）")
            except Exception as e:
                error_msg = str(e)
                if "Executable doesn't exist" in error_msg or "playwright install" in error_msg:
                    logger.warning("浏览器二进制缺失，尝试自动安装后重试: %s", error_msg)
                    # 关闭当前 playwright 实例
                    if self._playwright:
                        self._playwright.stop()
                        self._playwright = None
                    # 安装浏览器
                    _ensure_browser_installed()
                    # 重新启动
                    self._playwright = sync_playwright().start()
                    self._browser = self._playwright.chromium.launch(**launch_options)
                    logger.info(f"浏览器自动安装后启动成功（{mode}模式）")
                else:
                    raise
        return self._browser

    def get_browser(self) -> Browser:
        """获取浏览器实例（自动启动）"""
        if self._browser is None:
            self.start_browser()
        return cast(Browser, self._browser)

    def create_context(self, use_anti_detection: bool = True, **kwargs: Any) -> BrowserContext:
        """
        创建新的浏览器上下文

        每个任务应该使用独立的 Context，避免互相干扰

        Args:
            use_anti_detection: 是否使用反检测配置
            **kwargs: 传递给 new_context 的参数

        Returns:
            BrowserContext 实例
        """
        browser = self.get_browser()

        # 默认配置
        if use_anti_detection:
            from .anti_detection import anti_detection

            default_config = anti_detection.get_browser_context_options()
        else:
            default_config = {
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            }

        default_config.update(kwargs)

        context = browser.new_context(**default_config)

        # 应用 playwright-stealth 到上下文
        if use_anti_detection:
            try:
                from playwright_stealth import Stealth

                stealth = Stealth()
                stealth.apply_stealth_sync(context)
                logger.info("创建新的浏览器上下文（已应用 playwright-stealth）")
            except ImportError:
                logger.warning("playwright-stealth 未安装，使用基础反检测")
                logger.info("创建新的浏览器上下文（基础反检测）")
        else:
            logger.info("创建新的浏览器上下文（无反检测）")

        return context

    def close(self) -> None:
        """关闭浏览器和 Playwright"""
        if self._browser:
            logger.info("关闭浏览器...")
            self._browser.close()
            self._browser = None

        if self._playwright:
            self._playwright.stop()
            self._playwright = None

        logger.info("浏览器已关闭")

    def __del__(self) -> None:
        """析构时自动关闭"""
        self.close()


class BrowserServiceAdapter(IBrowserService):
    """
    浏览器服务适配器

    实现 IBrowserService Protocol，将 BrowserService 适配为标准接口
    """

    def __init__(self, service: BrowserService | None = None):
        """
        初始化适配器

        Args:
            service: BrowserService 实例，为 None 时使用全局单例
        """
        self._service = service

    @property
    def service(self) -> BrowserService:
        """延迟加载服务实例"""
        if self._service is None:
            self._service = BrowserService()
        return self._service

    def get_browser(self) -> Any:
        """
        获取浏览器实例（同步版本）

        Returns:
            浏览器实例对象
        """
        return self.service.get_browser()

    def close_browser(self) -> None:  # type: ignore[override]
        """
        关闭浏览器（同步版本）
        """
        self.service.close()

    def create_context(self, use_anti_detection: bool = True, **kwargs: Any) -> BrowserContext:
        """
        创建新的浏览器上下文

        每个任务应该使用独立的 Context，避免互相干扰

        Args:
            use_anti_detection: 是否使用反检测配置
            **kwargs: 传递给 new_context 的参数

        Returns:
            BrowserContext 实例
        """
        return self.service.create_context(use_anti_detection=use_anti_detection, **kwargs)

    # 内部方法版本，供其他模块调用
    def get_browser_internal(self) -> Any:
        """
        获取浏览器实例（内部接口，无权限检查）

        Returns:
            浏览器实例对象
        """
        return self.service.get_browser()

    def close_browser_internal(self) -> None:
        """
        关闭浏览器（内部接口，无权限检查）
        """
        self.service.close()


# 注意：不再使用全局单例，请通过 ServiceLocator.get_browser_service() 获取服务实例
