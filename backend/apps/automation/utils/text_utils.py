"""
文本处理工具类

纯工具方法，不包含业务逻辑
"""
import re
import logging
from typing import List

logger = logging.getLogger("apps.automation")


class TextUtils:
    """文本处理相关工具方法"""
    
    # 案号正则（支持多种格式）
    # 标准案号格式：（2025）粤0606执保38607号
    # 必须以括号包裹的年份开头，后跟法院代码和案件类型
    CASE_NUMBER_PATTERN = re.compile(
        r'[（(〔\[]\d{4}[）)\]〕]\s*[\u4e00-\u9fa5]{1,10}\d+[\u4e00-\u9fa5]{1,5}\d+号?'
    )
    
    # 日期格式正则（用于排除误匹配）
    DATE_PATTERN = re.compile(
        r'\d{4}年\d{1,2}月\d{1,2}[日号]'
    )
    
    @staticmethod
    def normalize_case_number(case_number: str) -> str:
        """
        规范化案号
        
        Args:
            case_number: 原始案号
            
        Returns:
            规范化后的案号
        """
        if not case_number:
            return ""
        
        # 统一括号
        result = case_number.replace("(", "（").replace(")", "）")
        result = result.replace("〔", "（").replace("〕", "）")
        result = result.replace("[", "（").replace("]", "）")
        
        # 删除空格
        result = result.replace(" ", "").replace("\u3000", "")
        
        # 补全"号"字
        if result and not result.endswith("号"):
            result += "号"
        
        return result
    
    @staticmethod
    def clean_text(text: str) -> str:
        """
        清洗文本
        
        Args:
            text: 原始文本
            
        Returns:
            清洗后的文本
        """
        if not text:
            return ""
        
        # 去除多余空白
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        # 去除特殊字符
        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', text)
        
        return text
    
    @staticmethod
    def extract_case_numbers(text: str) -> List[str]:
        """
        从文本中提取所有案号
        
        Args:
            text: 文本内容
            
        Returns:
            案号列表
        """
        matches = TextUtils.CASE_NUMBER_PATTERN.findall(text)
        
        # 规范化并去重，同时排除日期格式
        case_numbers = []
        for m in matches:
            normalized = TextUtils.normalize_case_number(m)
            # 排除日期格式（如 2025年12月17号）
            if TextUtils.DATE_PATTERN.match(m):
                logger.debug(f"排除日期格式: {m}")
                continue
            if normalized and normalized not in case_numbers:
                case_numbers.append(normalized)
        
        if case_numbers:
            logger.info(f"提取到 {len(case_numbers)} 个案号: {case_numbers}")
        
        return case_numbers