"""
浏览器管理器 - 提供上下文管理器接口统一管理浏览器生命周期

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""
import logging
from contextlib import contextmanager
from typing import Iterator, Optional, Tuple

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)

from ..config.browser_config import BrowserConfig
from .exceptions import BrowserCreationError

logger = logging.getLogger("apps.automation")


class BrowserManager:
    """
    浏览器管理器 - 提供上下文管理器接口
    
    统一管理浏览器的创建、配置和销毁，确保资源正确清理。
    
    Example:
        with BrowserManager.create_browser() as (page, context):
            page.goto("https://example.com")
            # 自动清理
    """
    
    @staticmethod
    @contextmanager
    def create_browser(
        config: Optional[BrowserConfig] = None,
        use_anti_detection: bool = True,
    ) -> Iterator[Tuple[Page, BrowserContext]]:
        """
        创建浏览器上下文
        
        Args:
            config: 浏览器配置，None 则使用默认配置
            use_anti_detection: 是否启用反检测
            
        Yields:
            (page, context) 元组
            
        Raises:
            BrowserCreationError: 浏览器创建失败时
            
        Example:
            with BrowserManager.create_browser() as (page, context):
                page.goto("https://example.com")
                # 自动清理
        """
        # 使用默认配置或传入的配置
        if config is None:
            config = BrowserConfig.from_env()
        
        # 验证配置
        try:
            config.validate()
        except Exception as e:
            raise BrowserCreationError(
                message="配置验证失败",
                config=config.__dict__ if config else None,
                original_error=e
            )
        
        playwright: Optional[Playwright] = None
        browser: Optional[Browser] = None
        context: Optional[BrowserContext] = None
        page: Optional[Page] = None
        
        try:
            # 启动 Playwright
            logger.debug("启动 Playwright...")
            playwright = sync_playwright().start()
            
            # 获取 Playwright 参数
            pw_args = config.to_playwright_args()
            launch_args = pw_args["launch_args"]
            context_args = pw_args["context_args"]
            
            # 启动浏览器
            mode = "无头" if config.headless else "有头"
            logger.info(f"启动浏览器（{mode}模式）: {config}")
            
            try:
                browser = playwright.chromium.launch(**launch_args)
            except Exception as e:
                raise BrowserCreationError(
                    message="浏览器启动失败",
                    config={"launch_args": launch_args, "config": config.__dict__},
                    original_error=e
                )
            
            # 应用反检测配置
            if use_anti_detection:
                context_args = BrowserManager._apply_anti_detection(context_args)
            
            # 创建上下文
            logger.debug(f"创建浏览器上下文: {context_args}")
            try:
                context = browser.new_context(**context_args)
            except Exception as e:
                raise BrowserCreationError(
                    message="浏览器上下文创建失败",
                    config={"context_args": context_args},
                    original_error=e
                )
            
            # 设置超时
            context.set_default_timeout(pw_args["timeout"])
            context.set_default_navigation_timeout(pw_args["navigation_timeout"])
            
            # 创建页面
            page = context.new_page()
            
            # 注入反检测脚本
            if use_anti_detection:
                BrowserManager._inject_stealth_script(page)
            
            logger.info("✅ 浏览器已启动")
            
            yield page, context
            
        except BrowserCreationError:
            # 重新抛出 BrowserCreationError
            raise
        except Exception as e:
            # 包装其他异常
            raise BrowserCreationError(
                message="浏览器操作失败",
                config=config.__dict__ if config else None,
                original_error=e
            )
        finally:
            # 确保资源被清理
            BrowserManager._cleanup(page, context, browser, playwright)
    
    @staticmethod
    def _apply_anti_detection(context_args: dict) -> dict:
        """
        应用反检测配置
        
        Args:
            context_args: 原始上下文参数
            
        Returns:
            增强后的上下文参数
        """
        from .anti_detection import AntiDetection
        
        # 获取反检测配置
        anti_detection_config = AntiDetection.get_browser_context_options()
        
        # 合并配置（原始配置优先）
        merged = anti_detection_config.copy()
        merged.update(context_args)
        
        return merged
    
    @staticmethod
    def _inject_stealth_script(page: Page) -> None:
        """
        注入反检测脚本
        
        Args:
            page: Playwright Page 对象
        """
        from .anti_detection import AntiDetection
        AntiDetection.inject_stealth_script(page)
        logger.debug("已注入反检测脚本")
    
    @staticmethod
    def _cleanup(
        page: Optional[Page],
        context: Optional[BrowserContext],
        browser: Optional[Browser],
        playwright: Optional[Playwright],
    ) -> None:
        """
        清理浏览器资源
        
        确保即使发生错误也能正确清理所有资源。
        
        Args:
            page: Page 对象
            context: BrowserContext 对象
            browser: Browser 对象
            playwright: Playwright 对象
        """
        cleanup_errors = []
        
        # 关闭页面
        if page is not None:
            try:
                page.close()
                logger.debug("页面已关闭")
            except Exception as e:
                cleanup_errors.append(f"关闭页面失败: {e}")
        
        # 关闭上下文
        if context is not None:
            try:
                context.close()
                logger.debug("上下文已关闭")
            except Exception as e:
                cleanup_errors.append(f"关闭上下文失败: {e}")
        
        # 关闭浏览器
        if browser is not None:
            try:
                browser.close()
                logger.debug("浏览器已关闭")
            except Exception as e:
                cleanup_errors.append(f"关闭浏览器失败: {e}")
        
        # 停止 Playwright
        if playwright is not None:
            try:
                playwright.stop()
                logger.debug("Playwright 已停止")
            except Exception as e:
                cleanup_errors.append(f"停止 Playwright 失败: {e}")
        
        if cleanup_errors:
            logger.warning(f"清理过程中出现错误: {cleanup_errors}")
        else:
            logger.info("✅ 浏览器资源已清理")
