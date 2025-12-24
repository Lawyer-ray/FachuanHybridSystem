"""
数据校验和清洗服务
"""
import logging
from typing import Optional, Dict, Any

from apps.core.interfaces import IValidatorService
from apps.automation.utils.text_utils import TextUtils
from apps.automation.utils.file_utils import FileUtils

logger = logging.getLogger("apps.automation")


class ValidatorService:
    """数据校验服务"""
    
    def __init__(self, text_utils=None, file_utils=None):
        """
        初始化校验服务
        
        Args:
            text_utils: 文本工具（可选，支持依赖注入）
            file_utils: 文件工具（可选，支持依赖注入）
        """
        self._text_utils = text_utils
        self._file_utils = file_utils
    
    @property
    def text_utils(self):
        """延迟加载文本工具"""
        if self._text_utils is None:
            self._text_utils = TextUtils
        return self._text_utils
    
    @property
    def file_utils(self):
        """延迟加载文件工具"""
        if self._file_utils is None:
            self._file_utils = FileUtils
        return self._file_utils
    
    def validate_case_number(self, case_number: str) -> bool:
        """
        校验案号格式
        
        Args:
            case_number: 案号
            
        Returns:
            是否有效
        """
        if not case_number:
            return False
        
        # 规范化后再校验
        normalized = self.text_utils.normalize_case_number(case_number)
        match = self.text_utils.CASE_NUMBER_PATTERN.match(normalized)
        
        is_valid = match is not None
        if not is_valid:
            logger.warning(f"案号格式无效: {case_number}")
        
        return is_valid
    
    def normalize_case_number(self, case_number: str) -> str:
        """
        规范化案号
        
        Args:
            case_number: 原始案号
            
        Returns:
            规范化后的案号
        """
        return self.text_utils.normalize_case_number(case_number)
    
    def validate_file(self, file_path: str, expected_extensions: list = None) -> Dict[str, Any]:
        """
        校验文件
        
        Args:
            file_path: 文件路径
            expected_extensions: 期望的文件扩展名列表
            
        Returns:
            校验结果 {valid: bool, error: str, info: dict}
        """
        return self.file_utils.validate_file_basic(file_path, expected_extensions)
    
    def clean_text(self, text: str) -> str:
        """
        清洗文本
        
        Args:
            text: 原始文本
            
        Returns:
            清洗后的文本
        """
        return self.text_utils.clean_text(text)
    
    def extract_case_numbers(self, text: str) -> list:
        """
        从文本中提取所有案号
        
        Args:
            text: 文本内容
            
        Returns:
            案号列表
        """
        return self.text_utils.extract_case_numbers(text)


class ValidatorServiceAdapter(IValidatorService):
    """
    验证服务适配器
    
    实现 IValidatorService Protocol，将 ValidatorService 适配为标准接口
    """
    
    def __init__(self, service: Optional[ValidatorService] = None):
        self._service = service
    
    @property
    def service(self) -> ValidatorService:
        """延迟加载服务实例"""
        if self._service is None:
            self._service = ValidatorService()
        return self._service
    
    def validate_case_number(self, case_number: str) -> bool:
        """校验案号格式"""
        return self.service.validate_case_number(case_number)
    
    def normalize_case_number(self, case_number: str) -> str:
        """规范化案号"""
        return self.service.normalize_case_number(case_number)
    
    def validate_file(self, file_path: str, expected_extensions: list = None) -> Dict[str, Any]:
        """校验文件"""
        return self.service.validate_file(file_path, expected_extensions)
    
    def clean_text(self, text: str) -> str:
        """清洗文本"""
        return self.service.clean_text(text)
    
    def extract_case_numbers(self, text: str) -> list:
        """从文本中提取所有案号"""
        return self.service.extract_case_numbers(text)
    
    # 内部方法版本，供其他模块调用
    def validate_case_number_internal(self, case_number: str) -> bool:
        """校验案号格式（内部接口，无权限检查）"""
        return self.service.validate_case_number(case_number)
    
    def normalize_case_number_internal(self, case_number: str) -> str:
        """规范化案号（内部接口，无权限检查）"""
        return self.service.normalize_case_number(case_number)
    
    def validate_file_internal(self, file_path: str, expected_extensions: list = None) -> Dict[str, Any]:
        """校验文件（内部接口，无权限检查）"""
        return self.service.validate_file(file_path, expected_extensions)
    
    def clean_text_internal(self, text: str) -> str:
        """清洗文本（内部接口，无权限检查）"""
        return self.service.clean_text(text)
    
    def extract_case_numbers_internal(self, text: str) -> list:
        """从文本中提取所有案号（内部接口，无权限检查）"""
        return self.service.extract_case_numbers(text)


# 注意：不再使用全局单例，请通过 ServiceLocator.get_validator_service() 获取服务实例
