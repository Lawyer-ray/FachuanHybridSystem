"""
范围验证器

验证配置项的取值范围，支持数值范围、字符串长度、列表大小验证。
"""

from typing import Any, Dict, List, Union
from .base import ConfigValidator, ValidationResult, ValidationType


class RangeValidator(ConfigValidator):
    """范围验证器"""
    
    @property
    def validation_type(self) -> ValidationType:
        return ValidationType.RANGE
    
    def validate(self, key: str, value: Any, field_def: Any = None, config: Dict[str, Any] = None) -> ValidationResult:
        """验证配置项范围"""
        result = ValidationResult(is_valid=True)
        
        if field_def is None:
            return result
        
        # 验证最小值
        min_value = getattr(field_def, 'min_value', None)
        if min_value is not None:
            min_result = self._validate_min_value(key, value, min_value)
            result.merge(min_result)
        
        # 验证最大值
        max_value = getattr(field_def, 'max_value', None)
        if max_value is not None:
            max_result = self._validate_max_value(key, value, max_value)
            result.merge(max_result)
        
        # 验证选择项
        choices = getattr(field_def, 'choices', None)
        if choices is not None:
            choices_result = self._validate_choices(key, value, choices)
            result.merge(choices_result)
        
        return result
    
    def can_validate(self, field_def: Any) -> bool:
        """检查是否可以验证指定字段"""
        return (
            hasattr(field_def, 'min_value') and field_def.min_value is not None or
            hasattr(field_def, 'max_value') and field_def.max_value is not None or
            hasattr(field_def, 'choices') and field_def.choices is not None
        )
    
    def _validate_min_value(self, key: str, value: Any, min_value: Any) -> ValidationResult:
        """验证最小值"""
        result = ValidationResult(is_valid=True)
        
        try:
            # 数值类型
            if isinstance(value, (int, float)) and isinstance(min_value, (int, float)):
                if value < min_value:
                    result.add_error(f"配置项 '{key}' 的值 {value} 小于最小值 {min_value}")
            
            # 字符串长度
            elif isinstance(value, str) and isinstance(min_value, int):
                if len(value) < min_value:
                    result.add_error(f"配置项 '{key}' 的长度 {len(value)} 小于最小长度 {min_value}")
            
            # 列表/字典大小
            elif isinstance(value, (list, dict)) and isinstance(min_value, int):
                if len(value) < min_value:
                    type_name = "列表" if isinstance(value, list) else "字典"
                    result.add_error(f"配置项 '{key}' 的{type_name}大小 {len(value)} 小于最小大小 {min_value}")
            
            # 类型不匹配的警告
            elif not self._are_comparable_types(value, min_value):
                result.add_warning(
                    f"配置项 '{key}' 的类型 {type(value).__name__} 与最小值类型 {type(min_value).__name__} 不匹配，跳过最小值验证"
                )
        
        except (TypeError, ValueError) as e:
            result.add_error(f"配置项 '{key}' 最小值验证失败: {e}")
        
        return result
    
    def _validate_max_value(self, key: str, value: Any, max_value: Any) -> ValidationResult:
        """验证最大值"""
        result = ValidationResult(is_valid=True)
        
        try:
            # 数值类型
            if isinstance(value, (int, float)) and isinstance(max_value, (int, float)):
                if value > max_value:
                    result.add_error(f"配置项 '{key}' 的值 {value} 大于最大值 {max_value}")
            
            # 字符串长度
            elif isinstance(value, str) and isinstance(max_value, int):
                if len(value) > max_value:
                    result.add_error(f"配置项 '{key}' 的长度 {len(value)} 大于最大长度 {max_value}")
            
            # 列表/字典大小
            elif isinstance(value, (list, dict)) and isinstance(max_value, int):
                if len(value) > max_value:
                    type_name = "列表" if isinstance(value, list) else "字典"
                    result.add_error(f"配置项 '{key}' 的{type_name}大小 {len(value)} 大于最大大小 {max_value}")
            
            # 类型不匹配的警告
            elif not self._are_comparable_types(value, max_value):
                result.add_warning(
                    f"配置项 '{key}' 的类型 {type(value).__name__} 与最大值类型 {type(max_value).__name__} 不匹配，跳过最大值验证"
                )
        
        except (TypeError, ValueError) as e:
            result.add_error(f"配置项 '{key}' 最大值验证失败: {e}")
        
        return result
    
    def _validate_choices(self, key: str, value: Any, choices: List[Any]) -> ValidationResult:
        """验证选择项"""
        result = ValidationResult(is_valid=True)
        
        if not isinstance(choices, (list, tuple, set)):
            result.add_error(f"配置项 '{key}' 的选择项必须是列表、元组或集合")
            return result
        
        if value not in choices:
            choices_str = ", ".join(str(choice) for choice in choices)
            result.add_error(f"配置项 '{key}' 的值 '{value}' 不在允许的选择项中: [{choices_str}]")
        
        return result
    
    def _are_comparable_types(self, value1: Any, value2: Any) -> bool:
        """检查两个值是否可以比较"""
        # 数值类型之间可以比较
        if isinstance(value1, (int, float)) and isinstance(value2, (int, float)):
            return True
        
        # 字符串与整数（用于长度比较）
        if isinstance(value1, str) and isinstance(value2, int):
            return True
        
        # 列表/字典与整数（用于大小比较）
        if isinstance(value1, (list, dict)) and isinstance(value2, int):
            return True
        
        # 相同类型
        if type(value1) == type(value2):
            return True
        
        return False


class NumericRangeValidator(ConfigValidator):
    """数值范围验证器，专门用于数值类型的范围验证"""
    
    @property
    def validation_type(self) -> ValidationType:
        return ValidationType.RANGE
    
    def validate(self, key: str, value: Any, field_def: Any = None, config: Dict[str, Any] = None) -> ValidationResult:
        """验证数值范围"""
        result = ValidationResult(is_valid=True)
        
        if not isinstance(value, (int, float)):
            return result
        
        if field_def is None:
            return result
        
        # 验证数值范围
        min_val = getattr(field_def, 'min_value', None)
        max_val = getattr(field_def, 'max_value', None)
        
        if min_val is not None and isinstance(min_val, (int, float)):
            if value < min_val:
                result.add_error(f"数值配置项 '{key}' 的值 {value} 小于最小值 {min_val}")
        
        if max_val is not None and isinstance(max_val, (int, float)):
            if value > max_val:
                result.add_error(f"数值配置项 '{key}' 的值 {value} 大于最大值 {max_val}")
        
        # 验证步长
        step = getattr(field_def, 'step', None)
        if step is not None and isinstance(step, (int, float)) and step > 0:
            if min_val is not None:
                remainder = (value - min_val) % step
                if abs(remainder) > 1e-10:  # 浮点数精度处理
                    result.add_error(f"数值配置项 '{key}' 的值 {value} 不符合步长 {step} 的要求")
        
        return result
    
    def can_validate(self, field_def: Any) -> bool:
        """检查是否可以验证指定字段"""
        return (
            hasattr(field_def, 'type') and 
            field_def.type in (int, float) and
            (
                (hasattr(field_def, 'min_value') and field_def.min_value is not None) or
                (hasattr(field_def, 'max_value') and field_def.max_value is not None) or
                (hasattr(field_def, 'step') and field_def.step is not None)
            )
        )


class StringLengthValidator(ConfigValidator):
    """字符串长度验证器"""
    
    @property
    def validation_type(self) -> ValidationType:
        return ValidationType.RANGE
    
    def validate(self, key: str, value: Any, field_def: Any = None, config: Dict[str, Any] = None) -> ValidationResult:
        """验证字符串长度"""
        result = ValidationResult(is_valid=True)
        
        if not isinstance(value, str):
            return result
        
        if field_def is None:
            return result
        
        min_length = getattr(field_def, 'min_length', None)
        max_length = getattr(field_def, 'max_length', None)
        
        value_length = len(value)
        
        if min_length is not None and isinstance(min_length, int):
            if value_length < min_length:
                result.add_error(f"字符串配置项 '{key}' 的长度 {value_length} 小于最小长度 {min_length}")
        
        if max_length is not None and isinstance(max_length, int):
            if value_length > max_length:
                result.add_error(f"字符串配置项 '{key}' 的长度 {value_length} 大于最大长度 {max_length}")
        
        return result
    
    def can_validate(self, field_def: Any) -> bool:
        """检查是否可以验证指定字段"""
        return (
            hasattr(field_def, 'type') and 
            field_def.type is str and
            (
                (hasattr(field_def, 'min_length') and field_def.min_length is not None) or
                (hasattr(field_def, 'max_length') and field_def.max_length is not None)
            )
        )