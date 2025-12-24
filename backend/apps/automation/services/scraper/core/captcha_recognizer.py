"""
验证码识别器接口

提供可插拔的验证码识别功能，支持多种识别服务。
"""
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger("apps.automation")


class CaptchaRecognizer(ABC):
    """
    验证码识别器抽象接口
    
    定义验证码识别的标准接口，允许不同的识别服务实现。
    所有实现必须提供两个核心方法：
    1. recognize() - 从字节流识别验证码
    2. recognize_from_element() - 从页面元素识别验证码
    
    实现者应该：
    - 在识别失败时返回 None 而不是抛出异常
    - 记录详细的错误日志以便调试
    - 处理所有可能的异常情况
    """
    
    @abstractmethod
    def recognize(self, image_bytes: bytes) -> Optional[str]:
        """
        从图片字节流识别验证码
        
        Args:
            image_bytes: 图片的字节数据
            
        Returns:
            识别出的验证码文本，识别失败返回 None
            
        Note:
            - 实现应该处理所有异常并返回 None
            - 不应该抛出异常到调用者
            - 应该记录错误日志以便调试
        """
        pass
    
    @abstractmethod
    def recognize_from_element(self, page, selector: str) -> Optional[str]:
        """
        从页面元素识别验证码
        
        Args:
            page: Playwright Page 对象
            selector: 验证码图片元素的 CSS 选择器
            
        Returns:
            识别出的验证码文本，识别失败返回 None
            
        Note:
            - 实现应该处理元素定位失败、截图失败等异常
            - 不应该抛出异常到调用者
            - 应该记录错误日志以便调试
        """
        pass


class DdddocrRecognizer(CaptchaRecognizer):
    """
    使用 ddddocr 库实现的验证码识别器
    
    ddddocr 是一个开源的 OCR 库，专门用于识别验证码。
    这个实现提供了基本的验证码识别功能，适用于大多数简单验证码。
    
    Attributes:
        ocr: ddddocr.DdddOcr 实例，用于执行实际的识别工作
        
    Example:
        >>> recognizer = DdddocrRecognizer()
        >>> with open('captcha.png', 'rb') as f:
        ...     image_bytes = f.read()
        >>> result = recognizer.recognize(image_bytes)
        >>> print(result)  # '1234'
    """
    
    def __init__(self, show_ad: bool = False):
        """
        初始化 ddddocr 识别器
        
        Args:
            show_ad: 是否显示 ddddocr 的广告信息，默认 False
            
        Raises:
            ImportError: 如果 ddddocr 库未安装
        """
        try:
            import ddddocr
            self.ocr = ddddocr.DdddOcr(show_ad=show_ad)
            logger.info("✅ DdddocrRecognizer 初始化成功")
        except ImportError as e:
            logger.error("❌ ddddocr 未安装，请运行: pip install ddddocr")
            raise ImportError(
                "ddddocr 库未安装。请运行: pip install ddddocr"
            ) from e
    
    def recognize(self, image_bytes: bytes) -> Optional[str]:
        """
        从图片字节流识别验证码
        
        Args:
            image_bytes: 图片的字节数据
            
        Returns:
            识别出的验证码文本（已去除空格），识别失败返回 None
        """
        if not image_bytes:
            logger.warning("⚠️ 图片字节流为空")
            return None
        
        try:
            result = self.ocr.classification(image_bytes)
            # 清理结果：去除空格
            cleaned_result = result.strip().replace(" ", "")
            logger.info(f"✅ 验证码识别成功: {cleaned_result}")
            return cleaned_result
        except Exception as e:
            logger.error(f"❌ 验证码识别失败: {e}", exc_info=True)
            return None
    
    def recognize_from_element(self, page, selector: str) -> Optional[str]:
        """
        从页面元素识别验证码
        
        Args:
            page: Playwright Page 对象
            selector: 验证码图片元素的 CSS 选择器
            
        Returns:
            识别出的验证码文本，识别失败返回 None
        """
        try:
            # 定位元素
            element = page.locator(selector)
            
            # 等待元素可见
            element.wait_for(state="visible", timeout=5000)
            
            # 截取元素截图
            image_bytes = element.screenshot()
            
            # 使用 recognize 方法识别
            return self.recognize(image_bytes)
            
        except Exception as e:
            logger.error(
                f"❌ 从页面元素获取验证码失败 (selector: {selector}): {e}",
                exc_info=True
            )
            return None
