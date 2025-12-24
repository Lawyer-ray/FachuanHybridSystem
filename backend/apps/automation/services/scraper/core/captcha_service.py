"""
验证码识别服务
"""
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger("apps.automation")


class CaptchaService:
    """验证码识别服务"""
    
    def __init__(self):
        """初始化 ddddocr"""
        try:
            import ddddocr
            self.ocr = ddddocr.DdddOcr(show_ad=False)
            logger.info("ddddocr 初始化成功")
        except ImportError:
            logger.warning("ddddocr 未安装，验证码识别功能不可用")
            self.ocr = None
    
    def recognize_from_bytes(self, image_bytes: bytes) -> Optional[str]:
        """
        从字节流识别验证码
        
        Args:
            image_bytes: 图片字节流
            
        Returns:
            识别结果，失败返回 None
        """
        if not self.ocr:
            logger.error("ddddocr 未初始化")
            return None
        
        try:
            result = self.ocr.classification(image_bytes)
            logger.info(f"验证码识别结果: {result}")
            return result
        except Exception as e:
            logger.error(f"验证码识别失败: {e}")
            return None
    
    def recognize_from_file(self, file_path: str) -> Optional[str]:
        """
        从文件识别验证码
        
        Args:
            file_path: 图片文件路径
            
        Returns:
            识别结果，失败返回 None
        """
        try:
            with open(file_path, "rb") as f:
                image_bytes = f.read()
            return self.recognize_from_bytes(image_bytes)
        except Exception as e:
            logger.error(f"读取验证码文件失败: {e}")
            return None
    
    def recognize_from_element(self, page, selector: str) -> Optional[str]:
        """
        从页面元素识别验证码
        
        Args:
            page: Playwright Page 对象
            selector: 验证码图片的选择器
            
        Returns:
            识别结果，失败返回 None
        """
        if not self.ocr:
            logger.error("ddddocr 未初始化")
            return None
        
        try:
            # 截取验证码图片
            element = page.locator(selector)
            image_bytes = element.screenshot()
            return self.recognize_from_bytes(image_bytes)
        except Exception as e:
            logger.error(f"截取验证码失败: {e}")
            return None


# 注意：不再使用全局单例，请通过 ServiceLocator.get_captcha_service() 获取服务实例
