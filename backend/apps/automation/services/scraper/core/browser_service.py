"""
浏览器服务 - 单例模式管理 Playwright 浏览器实例
"""
import logging
from typing import Optional, Any
from playwright.sync_api import Browser, BrowserContext, sync_playwright, Playwright

from apps.core.interfaces import IBrowserService

logger = logging.getLogger("apps.automation")


class BrowserService:
    """
    浏览器服务单例
    
    全局复用 Browser 实例，每个任务创建独立的 Context
    """
    _instance: Optional["BrowserService"] = None
    _playwright: Optional[Playwright] = None
    _browser: Optional[Browser] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 避免重复初始化
        if not hasattr(self, "_initialized"):
            self._initialized = True
            logger.info("BrowserService 初始化")
    
    def start_browser(self, headless: bool = None) -> Browser:
        """
        启动浏览器（如果尚未启动）
        
        Args:
            headless: 是否无头模式（None 则从配置读取，默认开发环境 False，生产环境 True）
            
        Returns:
            Browser 实例
        """
        if self._browser is None:
            # 从配置读取默认值
            if headless is None:
                from django.conf import settings
                headless = getattr(settings, "SCRAPER_HEADLESS", not settings.DEBUG)
            
            mode = "无头" if headless else "有头"
            logger.info(f"启动 Playwright 浏览器（{mode}模式）...")
            
            self._playwright = sync_playwright().start()
            
            launch_options = {
                "headless": headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",  # 反爬虫检测
                    "--no-sandbox",
                ],
            }
            
            # 开发模式下减慢操作速度，方便观察
            if not headless:
                launch_options["slow_mo"] = 500
            
            self._browser = self._playwright.chromium.launch(**launch_options)
            logger.info(f"浏览器启动成功（{mode}模式）")
        return self._browser
    
    def get_browser(self) -> Browser:
        """获取浏览器实例（自动启动）"""
        if self._browser is None:
            self.start_browser()
        return self._browser
    
    def create_context(self, use_anti_detection: bool = True, **kwargs) -> BrowserContext:
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
        logger.info("创建新的浏览器上下文（反检测: %s）", use_anti_detection)
        return context
    
    def close(self):
        """关闭浏览器和 Playwright"""
        if self._browser:
            logger.info("关闭浏览器...")
            self._browser.close()
            self._browser = None
        
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        
        logger.info("浏览器已关闭")
    
    def __del__(self):
        """析构时自动关闭"""
        self.close()


class BrowserServiceAdapter(IBrowserService):
    """
    浏览器服务适配器
    
    实现 IBrowserService Protocol，将 BrowserService 适配为标准接口
    """
    
    def __init__(self, service: Optional[BrowserService] = None):
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
    
    def close_browser(self) -> None:
        """
        关闭浏览器（同步版本）
        """
        self.service.close()
    
    def create_context(self, use_anti_detection: bool = True, **kwargs) -> BrowserContext:
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
