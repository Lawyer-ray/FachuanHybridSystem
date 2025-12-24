"""
爬虫服务自定义异常

提供清晰、描述性的异常类，帮助调试和错误处理。
"""


class ScraperException(Exception):
    """爬虫服务基础异常"""
    pass


class BrowserCreationError(ScraperException):
    """
    浏览器创建失败异常
    
    当无法创建或启动浏览器时抛出此异常。
    包含详细的错误信息以帮助调试。
    """
    
    def __init__(self, message: str, config: dict = None, original_error: Exception = None):
        """
        初始化异常
        
        Args:
            message: 错误消息
            config: 浏览器配置（用于调试）
            original_error: 原始异常
        """
        self.config = config
        self.original_error = original_error
        
        # 构建详细的错误消息
        detailed_message = f"浏览器创建失败: {message}"
        
        if config:
            detailed_message += f"\n配置: {config}"
        
        if original_error:
            detailed_message += f"\n原始错误: {type(original_error).__name__}: {original_error}"
        
        super().__init__(detailed_message)


class BrowserConfigurationError(ScraperException):
    """
    浏览器配置错误异常
    
    当浏览器配置无效时抛出此异常。
    """
    
    def __init__(self, field: str, value: any, reason: str):
        """
        初始化异常
        
        Args:
            field: 无效的配置字段名
            value: 无效的值
            reason: 为什么无效
        """
        self.field = field
        self.value = value
        self.reason = reason
        
        message = f"配置字段 '{field}' 无效: {reason} (值: {value})"
        super().__init__(message)


class CaptchaRecognitionError(ScraperException):
    """
    验证码识别失败异常
    
    当验证码识别失败且无法恢复时抛出此异常。
    """
    
    def __init__(self, message: str, attempts: int = 0, selector: str = None):
        """
        初始化异常
        
        Args:
            message: 错误消息
            attempts: 尝试次数
            selector: 验证码元素选择器
        """
        self.attempts = attempts
        self.selector = selector
        
        detailed_message = f"验证码识别失败: {message}"
        
        if attempts > 0:
            detailed_message += f" (尝试次数: {attempts})"
        
        if selector:
            detailed_message += f" (选择器: {selector})"
        
        super().__init__(detailed_message)


class CookieLoadError(ScraperException):
    """
    Cookie 加载失败异常
    
    当无法加载或应用 Cookie 时抛出此异常。
    """
    
    def __init__(self, message: str, site_name: str = None, account: str = None):
        """
        初始化异常
        
        Args:
            message: 错误消息
            site_name: 网站名称
            account: 账号
        """
        self.site_name = site_name
        self.account = account
        
        detailed_message = f"Cookie 加载失败: {message}"
        
        if site_name:
            detailed_message += f" (网站: {site_name})"
        
        if account:
            detailed_message += f" (账号: {account})"
        
        super().__init__(detailed_message)


class LoginError(ScraperException):
    """
    登录失败异常
    
    当登录过程失败时抛出此异常。
    """
    
    def __init__(
        self,
        message: str,
        account: str = None,
        reason: str = None,
        screenshot_path: str = None
    ):
        """
        初始化异常
        
        Args:
            message: 错误消息
            account: 账号
            reason: 失败原因
            screenshot_path: 错误截图路径
        """
        self.account = account
        self.reason = reason
        self.screenshot_path = screenshot_path
        
        detailed_message = f"登录失败: {message}"
        
        if account:
            detailed_message += f" (账号: {account})"
        
        if reason:
            detailed_message += f" (原因: {reason})"
        
        if screenshot_path:
            detailed_message += f" (截图: {screenshot_path})"
        
        super().__init__(detailed_message)
