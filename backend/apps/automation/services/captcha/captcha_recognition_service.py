"""
验证码识别服务

提供验证码识别的业务逻辑封装，支持 Base64 图片输入。
"""
import base64
import logging
import time
from io import BytesIO
from typing import Optional, Dict

from PIL import Image

from apps.automation.schemas import CaptchaRecognizeOut
from apps.automation.services.scraper.core.captcha_recognizer import DdddocrRecognizer
from apps.core.interfaces import ICaptchaService

logger = logging.getLogger("apps.automation")


class CaptchaRecognitionService:
    """
    验证码识别服务
    
    封装验证码识别的业务逻辑，包括：
    - Base64 图片解码
    - 图片格式和大小验证
    - 调用识别器执行识别
    - 结果封装
    
    支持依赖注入，所有依赖通过构造函数传递或延迟加载。
    """
    
    def __init__(
        self,
        recognizer: Optional[DdddocrRecognizer] = None,
        config: Optional[Dict] = None
    ):
        """
        初始化服务（支持依赖注入）
        
        Args:
            recognizer: 验证码识别器实例，None 时延迟加载
            config: 配置参数，None 时使用默认配置
        """
        self._recognizer = recognizer
        self._config = config or {}
        
        # 配置常量（可通过config覆盖）
        self.MAX_FILE_SIZE = self._config.get('max_file_size', 5 * 1024 * 1024)  # 5MB
        self.SUPPORTED_FORMATS = self._config.get('supported_formats', {'PNG', 'JPEG', 'GIF', 'BMP'})
        self.TIMEOUT_WARNING_SECONDS = self._config.get('timeout_warning_seconds', 5.0)
    
    @property
    def recognizer(self) -> DdddocrRecognizer:
        """
        获取识别器实例（延迟加载）
        
        使用延迟加载避免重复初始化 ddddocr（初始化耗时约 1-2 秒）
        
        Returns:
            DdddocrRecognizer: 识别器实例
        """
        if self._recognizer is None:
            from ...utils.logging import AutomationLogger
            AutomationLogger.log_business_operation(
                operation="initialize_recognizer",
                resource_type="ddddocr_recognizer",
                success=True
            )
            show_ad = self._config.get('show_ad', False)
            self._recognizer = DdddocrRecognizer(show_ad=show_ad)
        return self._recognizer
    


    def _decode_base64_image(self, image_base64: str) -> bytes:
        """
        解码 Base64 图片
        
        自动处理 data URL 前缀（如 "data:image/png;base64,"）
        
        Args:
            image_base64: Base64 编码的图片字符串
            
        Returns:
            bytes: 解码后的图片字节数据
            
        Raises:
            ValueError: Base64 解码失败
        """
        try:
            # 移除可能的 data URL 前缀
            if ',' in image_base64:
                image_base64 = image_base64.split(',', 1)[1]
            
            # 去除空白字符
            image_base64 = image_base64.strip()
            
            # 解码 Base64
            image_bytes = base64.b64decode(image_base64, validate=True)
            
            from ...utils.logging import AutomationLogger
            AutomationLogger.log_business_operation(
                operation="base64_decode",
                resource_type="captcha_image",
                success=True,
                image_size=len(image_bytes)
            )
            return image_bytes
            
        except Exception as e:
            logger.warning(f"Base64 解码失败: {e}")
            raise ValueError("无效的 Base64 编码")
    
    def _validate_image_size(self, image_bytes: bytes) -> None:
        """
        验证图片大小
        
        Args:
            image_bytes: 图片字节数据
            
        Raises:
            ValueError: 图片大小超过限制
        """
        size_mb = len(image_bytes) / (1024 * 1024)
        
        if len(image_bytes) > self.MAX_FILE_SIZE:
            logger.warning(f"图片大小超过限制: {size_mb:.2f}MB > 5MB")
            raise ValueError("图片大小超过 5MB 限制")
        
        logger.debug(f"图片大小验证通过: {size_mb:.2f}MB")
    
    def _validate_image_format(self, image_bytes: bytes) -> None:
        """
        验证图片格式
        
        支持的格式: PNG, JPEG, GIF, BMP
        
        Args:
            image_bytes: 图片字节数据
            
        Raises:
            ValueError: 图片格式不支持
        """
        try:
            # 使用 PIL 打开图片以验证格式
            image = Image.open(BytesIO(image_bytes))
            image_format = image.format
            
            if image_format not in self.SUPPORTED_FORMATS:
                logger.warning(f"不支持的图片格式: {image_format}")
                raise ValueError(
                    f"不支持的图片格式，仅支持 {', '.join(self.SUPPORTED_FORMATS)}"
                )
            
            logger.debug(f"图片格式验证通过: {image_format}")
            
        except ValueError:
            # 重新抛出我们自己的 ValueError
            raise
        except Exception as e:
            logger.warning(f"图片格式验证失败: {e}")
            raise ValueError("无法识别图片格式")

    def recognize_from_base64(self, image_base64: str) -> CaptchaRecognizeOut:
        """
        从 Base64 编码的图片识别验证码
        
        完整的识别流程：
        1. 解码 Base64 图片
        2. 验证图片大小和格式
        3. 调用识别器执行识别
        4. 封装结果并返回
        
        Args:
            image_base64: Base64 编码的图片字符串
            
        Returns:
            CaptchaRecognizeOut: 识别结果，包含成功状态、文本、处理时间和错误信息
        """
        start_time = time.time()
        
        try:
            # 1. 验证输入
            if not image_base64 or not image_base64.strip():
                logger.warning("收到空的图片数据")
                return CaptchaRecognizeOut(
                    success=False,
                    text=None,
                    processing_time=time.time() - start_time,
                    error="图片数据不能为空"
                )
            
            # 2. 解码 Base64
            try:
                image_bytes = self._decode_base64_image(image_base64)
            except ValueError as e:
                return CaptchaRecognizeOut(
                    success=False,
                    text=None,
                    processing_time=time.time() - start_time,
                    error=str(e)
                )
            
            # 3. 验证图片大小
            try:
                self._validate_image_size(image_bytes)
            except ValueError as e:
                return CaptchaRecognizeOut(
                    success=False,
                    text=None,
                    processing_time=time.time() - start_time,
                    error=str(e)
                )
            
            # 4. 验证图片格式
            try:
                self._validate_image_format(image_bytes)
            except ValueError as e:
                return CaptchaRecognizeOut(
                    success=False,
                    text=None,
                    processing_time=time.time() - start_time,
                    error=str(e)
                )
            
            # 5. 执行识别
            from ...utils.logging import AutomationLogger
            AutomationLogger.log_captcha_recognition_start(image_size=len(image_bytes))
            result = self.recognizer.recognize(image_bytes)
            
            processing_time = time.time() - start_time
            
            # 6. 检查处理时间
            if processing_time > self.TIMEOUT_WARNING_SECONDS:
                AutomationLogger.log_business_operation(
                    operation="captcha_recognition_timeout_warning",
                    resource_type="captcha_image",
                    success=False,
                    processing_time=processing_time,
                    timeout_threshold=self.TIMEOUT_WARNING_SECONDS
                )
            
            # 7. 封装结果
            if result:
                AutomationLogger.log_captcha_recognition_success(
                    processing_time=processing_time,
                    result_length=len(result),
                    image_size=len(image_bytes)
                )
                return CaptchaRecognizeOut(
                    success=True,
                    text=result,
                    processing_time=processing_time,
                    error=None
                )
            else:
                AutomationLogger.log_captcha_recognition_failed(
                    processing_time=processing_time,
                    error_message="无法识别验证码",
                    image_size=len(image_bytes)
                )
                return CaptchaRecognizeOut(
                    success=False,
                    text=None,
                    processing_time=processing_time,
                    error="无法识别验证码"
                )
                
        except Exception as e:
            # 捕获所有未预期的异常
            processing_time = time.time() - start_time
            from ...utils.logging import AutomationLogger
            AutomationLogger.log_captcha_recognition_failed(
                processing_time=processing_time,
                error_message=str(e),
                image_size=len(image_bytes) if 'image_bytes' in locals() else None
            )
            return CaptchaRecognizeOut(
                success=False,
                text=None,
                processing_time=processing_time,
                error="系统错误，请稍后重试"
            )


class CaptchaServiceAdapter(ICaptchaService):
    """
    验证码服务适配器
    
    实现 ICaptchaService Protocol，将 CaptchaRecognitionService 适配为标准接口
    """
    
    def __init__(self, service: Optional[CaptchaRecognitionService] = None):
        """
        初始化适配器
        
        Args:
            service: CaptchaRecognitionService 实例，为 None 时创建新实例
        """
        self._service = service
    
    @property
    def service(self) -> CaptchaRecognitionService:
        """延迟加载服务实例"""
        if self._service is None:
            self._service = CaptchaRecognitionService()
        return self._service
    
    def recognize(self, image_data: bytes) -> str:
        """
        识别验证码（公开接口，包含权限检查）
        
        Args:
            image_data: 验证码图片的二进制数据
            
        Returns:
            识别出的验证码文本
            
        Raises:
            CaptchaRecognitionError: 验证码识别失败
        """
        # 权限检查逻辑可以在这里添加
        return self.recognize_internal(image_data)
    
    def recognize_internal(self, image_data: bytes) -> str:
        """
        识别验证码（内部接口，无权限检查，供其他模块调用）
        
        Args:
            image_data: 验证码图片的二进制数据
            
        Returns:
            识别出的验证码文本
            
        Raises:
            CaptchaRecognitionError: 验证码识别失败
        """
        try:
            # 将二进制数据转换为 Base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # 调用原服务的识别方法
            result = self.service.recognize_from_base64(image_base64)
            
            if result.success and result.text:
                return result.text
            else:
                # 抛出标准化异常
                from apps.core.exceptions import AutomationExceptions
                error_msg = result.error or "验证码识别失败"
                raise AutomationExceptions.captcha_recognition_failed(
                    details=error_msg,
                    processing_time=getattr(result, 'processing_time', None)
                )
                
        except Exception as e:
            # 如果不是我们的自定义异常，包装为标准异常
            from apps.core.exceptions import ValidationException
            from apps.core.exceptions import AutomationExceptions
            if not isinstance(e, ValidationException):
                raise AutomationExceptions.captcha_recognition_error(
                    error_message=str(e)
                )
            else:
                raise
    
    def recognize_from_base64(self, image_base64: str):
        """
        从 Base64 编码的图片识别验证码（适配器方法）
        
        直接委托给底层服务的 recognize_from_base64 方法
        
        Args:
            image_base64: Base64 编码的图片数据
            
        Returns:
            CaptchaRecognizeOut: 识别结果对象
        """
        return self.service.recognize_from_base64(image_base64)
