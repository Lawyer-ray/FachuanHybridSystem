"""ErrorAnalyzer - 分析和分类mypy错误"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class ErrorRecord:
    """错误记录数据类"""
    file_path: str
    line: int
    column: int
    error_code: str
    message: str
    severity: Literal['critical', 'high', 'medium', 'low']
    fixable: bool
    fix_pattern: str | None


class ErrorAnalyzer:
    """分析mypy错误并生成统计报告"""
    
    # 错误类型优先级映射
    ERROR_SEVERITY_MAP: dict[str, Literal['critical', 'high', 'medium', 'low']] = {
        # Critical - 可能导致运行时错误
        'name-defined': 'critical',
        'attr-defined': 'critical',
        'call-arg': 'critical',
        'index': 'critical',
        
        # High - 类型安全问题
        'no-untyped-def': 'high',
        'no-untyped-call': 'high',
        'arg-type': 'high',
        'return-value': 'high',
        'assignment': 'high',
        
        # Medium - 类型注解不完整
        'type-arg': 'medium',
        'no-any-return': 'medium',
        'return': 'medium',
        'var-annotated': 'medium',
        
        # Low - 其他类型问题
        'misc': 'low',
        'override': 'low',
        'union-attr': 'low',
    }
    
    # 可批量修复的错误模式
    FIXABLE_PATTERNS: dict[str, str] = {
        'type-arg': 'add_generic_params',
        'no-untyped-def': 'add_type_annotations',
    }
    
    def __init__(self) -> None:
        """初始化ErrorAnalyzer"""
        self._error_pattern = re.compile(
            r'^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s+'
            r'(?P<severity>\w+):\s+(?P<message>.+?)\s+\[(?P<code>[^\]]+)\]'
        )
    
    def analyze(self, mypy_output: str) -> list[ErrorRecord]:
        """
        解析mypy输出并返回错误记录列表
        
        Args:
            mypy_output: mypy命令的输出文本
            
        Returns:
            错误记录列表
        """
        lines = mypy_output.strip().split('\n')
        errors: list[ErrorRecord] = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            match = self._error_pattern.match(line)
            if match:
                groups = match.groupdict()
                error_code = groups['code']
                
                error = ErrorRecord(
                    file_path=groups['file'],
                    line=int(groups['line']),
                    column=int(groups['col']),
                    error_code=error_code,
                    message=groups['message'],
                    severity=self._get_severity(error_code),
                    fixable=error_code in self.FIXABLE_PATTERNS,
                    fix_pattern=self.FIXABLE_PATTERNS.get(error_code),
                )
                errors.append(error)
            else:
                # 无法解析的行，记录警告
                if 'error:' in line.lower() or 'warning:' in line.lower():
                    logger.warning(f"无法解析的mypy输出行: {line}")
        
        logger.info(f"成功解析 {len(errors)} 个错误")
        return errors
    
    def categorize_by_type(self, errors: list[ErrorRecord]) -> dict[str, list[ErrorRecord]]:
        """
        按错误类型分类
        
        Args:
            errors: 错误记录列表
            
        Returns:
            按错误类型分组的字典
        """
        categories: dict[str, list[ErrorRecord]] = defaultdict(list)
        for error in errors:
            categories[error.error_code].append(error)
        
        result = dict(categories)
        logger.info(f"按类型分类: {len(result)} 种错误类型")
        return result
    
    def categorize_by_module(self, errors: list[ErrorRecord]) -> dict[str, list[ErrorRecord]]:
        """
        按模块分类
        
        Args:
            errors: 错误记录列表
            
        Returns:
            按模块分组的字典
        """
        categories: dict[str, list[ErrorRecord]] = defaultdict(list)
        for error in errors:
            module = self._get_module_from_file(error.file_path)
            categories[module].append(error)
        
        result = dict(categories)
        logger.info(f"按模块分类: {len(result)} 个模块")
        return result
    
    def identify_fixable(self, errors: list[ErrorRecord]) -> list[ErrorRecord]:
        """
        识别可批量修复的错误
        
        Args:
            errors: 错误记录列表
            
        Returns:
            可批量修复的错误列表
        """
        fixable = [e for e in errors if e.fixable]
        logger.info(f"识别出 {len(fixable)} 个可批量修复的错误")
        return fixable
    
    def get_sorted_by_count(
        self, 
        categorized: dict[str, list[ErrorRecord]]
    ) -> list[tuple[str, int]]:
        """
        按错误数量排序分类结果
        
        Args:
            categorized: 分类后的错误字典
            
        Returns:
            排序后的(类型, 数量)元组列表
        """
        sorted_items = sorted(
            [(key, len(errors)) for key, errors in categorized.items()],
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_items
    
    def _get_severity(self, error_code: str) -> Literal['critical', 'high', 'medium', 'low']:
        """获取错误严重程度"""
        return self.ERROR_SEVERITY_MAP.get(error_code, 'low')
    
    def _get_module_from_file(self, file_path: str) -> str:
        """从文件路径提取模块名"""
        if file_path.startswith('apps/'):
            parts = file_path.split('/')
            if len(parts) >= 2:
                return parts[1]
        return 'other'
