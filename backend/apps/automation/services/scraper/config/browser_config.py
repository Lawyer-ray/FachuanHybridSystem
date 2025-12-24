"""
浏览器配置类 - 集中管理所有浏览器相关配置

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 7.1, 7.2, 7.3, 7.4, 7.5
"""
import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("apps.automation")


class ConfigurationError(ValueError):
    """配置验证错误"""
    pass


@dataclass
class BrowserConfig:
    """
    浏览器配置
    
    集中管理所有浏览器相关的配置参数，支持从环境变量加载和验证。
    
    Attributes:
        headless: 是否无头模式
        slow_mo: 操作延迟（毫秒）
        viewport_width: 视口宽度
        viewport_height: 视口高度
        user_agent: User Agent 字符串
        timeout: 默认超时时间（毫秒）
        navigation_timeout: 导航超时时间（毫秒）
        save_screenshots: 是否保存截图
        screenshot_dir: 截图保存目录
    """
    
    # 基础配置
    headless: bool = False
    slow_mo: int = 0
    
    # 视口配置
    viewport_width: int = 1280
    viewport_height: int = 800
    
    # User Agent
    user_agent: str = field(default=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ))

    # 超时配置
    timeout: int = 30000
    navigation_timeout: int = 30000
    
    # 调试配置
    save_screenshots: bool = False
    screenshot_dir: Optional[Path] = None
    
    # 浏览器启动参数
    disable_automation_detection: bool = True
    no_sandbox: bool = True
    
    def __post_init__(self):
        """初始化后处理"""
        # 转换 screenshot_dir 为 Path 对象
        if self.screenshot_dir is not None and not isinstance(self.screenshot_dir, Path):
            self.screenshot_dir = Path(self.screenshot_dir)
    
    @classmethod
    def from_env(cls) -> "BrowserConfig":
        """
        从环境变量加载配置
        
        环境变量映射:
            BROWSER_HEADLESS: bool (true/false)
            BROWSER_SLOW_MO: int
            BROWSER_VIEWPORT_WIDTH: int
            BROWSER_VIEWPORT_HEIGHT: int
            BROWSER_USER_AGENT: str
            BROWSER_TIMEOUT: int
            BROWSER_NAVIGATION_TIMEOUT: int
            BROWSER_SAVE_SCREENSHOTS: bool (true/false)
            BROWSER_SCREENSHOT_DIR: str (path)
            
        Returns:
            BrowserConfig 实例
        """
        def get_bool(key: str, default: bool) -> bool:
            """从环境变量获取布尔值"""
            value = os.environ.get(key)
            if value is None:
                return default
            return value.lower() in ("true", "1", "yes", "on")
        
        def get_int(key: str, default: int) -> int:
            """从环境变量获取整数值"""
            value = os.environ.get(key)
            if value is None:
                return default
            try:
                return int(value)
            except ValueError:
                logger.warning(f"环境变量 {key} 值 '{value}' 不是有效整数，使用默认值 {default}")
                return default
        
        def get_str(key: str, default: str) -> str:
            """从环境变量获取字符串值"""
            return os.environ.get(key, default)
        
        def get_path(key: str, default: Optional[Path]) -> Optional[Path]:
            """从环境变量获取路径值"""
            value = os.environ.get(key)
            if value is None:
                return default
            return Path(value)
        
        # 获取默认实例的默认值
        defaults = cls()
        
        config = cls(
            headless=get_bool("BROWSER_HEADLESS", defaults.headless),
            slow_mo=get_int("BROWSER_SLOW_MO", defaults.slow_mo),
            viewport_width=get_int("BROWSER_VIEWPORT_WIDTH", defaults.viewport_width),
            viewport_height=get_int("BROWSER_VIEWPORT_HEIGHT", defaults.viewport_height),
            user_agent=get_str("BROWSER_USER_AGENT", defaults.user_agent),
            timeout=get_int("BROWSER_TIMEOUT", defaults.timeout),
            navigation_timeout=get_int("BROWSER_NAVIGATION_TIMEOUT", defaults.navigation_timeout),
            save_screenshots=get_bool("BROWSER_SAVE_SCREENSHOTS", defaults.save_screenshots),
            screenshot_dir=get_path("BROWSER_SCREENSHOT_DIR", defaults.screenshot_dir),
        )
        
        logger.debug(f"从环境变量加载配置: headless={config.headless}, slow_mo={config.slow_mo}")
        return config

    def validate(self) -> None:
        """
        验证配置值
        
        Raises:
            ConfigurationError: 当配置值无效时
        """
        errors = []
        
        # 验证 slow_mo
        if self.slow_mo < 0:
            errors.append(f"slow_mo 必须 >= 0，当前值: {self.slow_mo}")
        
        # 验证视口尺寸
        if self.viewport_width <= 0:
            errors.append(f"viewport_width 必须 > 0，当前值: {self.viewport_width}")
        if self.viewport_height <= 0:
            errors.append(f"viewport_height 必须 > 0，当前值: {self.viewport_height}")
        
        # 验证超时时间
        if self.timeout <= 0:
            errors.append(f"timeout 必须 > 0，当前值: {self.timeout}")
        if self.navigation_timeout <= 0:
            errors.append(f"navigation_timeout 必须 > 0，当前值: {self.navigation_timeout}")
        
        # 验证 user_agent
        if not self.user_agent or not self.user_agent.strip():
            errors.append("user_agent 不能为空")
        
        # 验证截图目录（如果启用了截图保存）
        if self.save_screenshots and self.screenshot_dir is not None:
            if not self.screenshot_dir.exists():
                # 尝试创建目录
                try:
                    self.screenshot_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"创建截图目录: {self.screenshot_dir}")
                except OSError as e:
                    errors.append(f"无法创建截图目录 {self.screenshot_dir}: {e}")
        
        if errors:
            error_msg = "配置验证失败:\n" + "\n".join(f"  - {e}" for e in errors)
            logger.error(error_msg)
            raise ConfigurationError(error_msg)
        
        logger.debug("配置验证通过")
    
    def to_playwright_args(self) -> Dict[str, Any]:
        """
        转换为 Playwright 参数
        
        Returns:
            包含 launch_args 和 context_args 的字典
        """
        # 浏览器启动参数
        browser_args = []
        if self.disable_automation_detection:
            browser_args.append("--disable-blink-features=AutomationControlled")
        if self.no_sandbox:
            browser_args.append("--no-sandbox")
        
        launch_args = {
            "headless": self.headless,
            "args": browser_args,
        }
        
        # 只有非零时才添加 slow_mo
        if self.slow_mo > 0:
            launch_args["slow_mo"] = self.slow_mo
        
        # 上下文参数
        context_args = {
            "viewport": {
                "width": self.viewport_width,
                "height": self.viewport_height,
            },
            "user_agent": self.user_agent,
        }
        
        return {
            "launch_args": launch_args,
            "context_args": context_args,
            "timeout": self.timeout,
            "navigation_timeout": self.navigation_timeout,
        }
    
    def __repr__(self) -> str:
        """返回配置的字符串表示"""
        return (
            f"BrowserConfig("
            f"headless={self.headless}, "
            f"slow_mo={self.slow_mo}, "
            f"viewport={self.viewport_width}x{self.viewport_height}, "
            f"timeout={self.timeout}ms"
            f")"
        )
