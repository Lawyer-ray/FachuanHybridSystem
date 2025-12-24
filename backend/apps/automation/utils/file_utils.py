"""
文件处理工具类

纯工具方法，不包含业务逻辑
"""
import os
import logging
from typing import Dict, Any
from pathlib import Path

logger = logging.getLogger("apps.automation")


class FileUtils:
    """文件处理相关工具方法"""
    
    @staticmethod
    def validate_file_basic(file_path: str, expected_extensions: list = None) -> Dict[str, Any]:
        """
        基础文件校验
        
        Args:
            file_path: 文件路径
            expected_extensions: 期望的文件扩展名列表
            
        Returns:
            校验结果 {valid: bool, error: str, info: dict}
        """
        result = {"valid": True, "error": None, "info": {}}
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            result["valid"] = False
            result["error"] = "文件不存在"
            return result
        
        # 检查文件大小
        file_size = os.path.getsize(file_path)
        result["info"]["size"] = file_size
        
        if file_size == 0:
            result["valid"] = False
            result["error"] = "文件为空"
            return result
        
        # 检查文件扩展名
        ext = Path(file_path).suffix.lower()
        result["info"]["extension"] = ext
        
        if expected_extensions and ext not in expected_extensions:
            result["valid"] = False
            result["error"] = f"文件类型不匹配，期望: {expected_extensions}"
            return result
        
        # 检查文件是否损坏（简单检查）
        try:
            with open(file_path, "rb") as f:
                f.read(1024)  # 尝试读取前1KB
        except Exception as e:
            result["valid"] = False
            result["error"] = f"文件可能损坏: {str(e)}"
            return result
        
        logger.info(f"文件校验通过: {file_path} ({file_size} bytes)")
        return result