"""
类型验证器

验证配置项的类型正确性，支持基本类型和复杂类型验证。
"""

import re
from typing import Any, Dict, List, Union, get_origin, get_args
from .base import ConfigValidator, ValidationResult, ValidationType


class TypeValidator(ConfigValidator):
    """类型验证器"""
    
    @property
    def validation_type(self) -> ValidationType:
        return ValidationType.TYPE
    
    def validate(self, key: str, value: Any, field_def: Any = None, config: Dict[str, Any] = None) -> ValidationResult:
        """验证配置项类型"""
        result = ValidationResult(is_valid=True)
        
        if field_def is None:
            return result
        
        expected_type = getattr(field_def, 'type', None)
        if expected_type is None:
            return result
        
        # 处理None值
        if value is None:
            if not getattr(field_def, 'required', False):
                return result
            else:
                result.add_error(f"配置项 '{key}' 是必需的，不能为 None")
                return result
        
        # 验证类型
        if not self._is_valid_type(value, expected_type):
            # 尝试类型转换
            converted_value = self._try_convert_type(value, expected_type)
            if converted_value is not None:
                result.add_warning(f"配置项 '{key}' 已从 {type(value).__name__} 转换为 {expected_type.__name__}")
            else:
                result.add_error(
                    f"配置项 '{key}' 类型错误: 期望 {self._get_type_name(expected_type)}, "
                    f"实际 {type(value).__name__}"
                )
        
        return result
    
    def can_validate(self, field_def: Any) -> bool:
        """检查是否可以验证指定字段"""
        return hasattr(field_def, 'type') and field_def.type is not None
    
    def _is_valid_type(self, value: Any, expected_type: type) -> bool:
        """检查值是否为期望类型"""
        # 处理基本类型
        if expected_type in (str, int, float, bool, list, dict):
            return isinstance(value, expected_type)
        
        # 处理Union类型 (如 Optional[str] = Union[str, None])
        origin = get_origin(expected_type)
        if origin is Union:
            args = get_args(expected_type)
            return any(self._is_valid_type(value, arg) for arg in args)
        
        # 处理List类型
        if origin is list or expected_type is list:
            if not isinstance(value, list):
                return False
            
            # 如果有类型参数，验证列表元素类型
            args = get_args(expected_type)
            if args:
                element_type = args[0]
                return all(self._is_valid_type(item, element_type) for item in value)
            return True
        
        # 处理Dict类型
        if origin is dict or expected_type is dict:
            if not isinstance(value, dict):
                return False
            
            # 如果有类型参数，验证键值类型
            args = get_args(expected_type)
            if len(args) == 2:
                key_type, value_type = args
                return all(
                    self._is_valid_type(k, key_type) and self._is_valid_type(v, value_type)
                    for k, v in value.items()
                )
            return True
        
        # 其他类型直接使用isinstance
        try:
            return isinstance(value, expected_type)
        except TypeError:
            # 处理一些特殊的泛型类型
            return False
    
    def _try_convert_type(self, value: Any, expected_type: type) -> Any:
        """尝试类型转换"""
        try:
            # 字符串转换
            if expected_type is str:
                return str(value)
            
            # 数值转换
            elif expected_type is int:
                if isinstance(value, str):
                    # 处理字符串数字
                    if value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
                        return int(value)
                elif isinstance(value, float):
                    return int(value)
            
            elif expected_type is float:
                if isinstance(value, (str, int)):
                    return float(value)
            
            # 布尔转换
            elif expected_type is bool:
                if isinstance(value, str):
                    lower_value = value.lower()
                    if lower_value in ('true', '1', 'yes', 'on'):
                        return True
                    elif lower_value in ('false', '0', 'no', 'off'):
                        return False
                elif isinstance(value, (int, float)):
                    return bool(value)
            
            # 列表转换
            elif expected_type is list:
                if isinstance(value, str):
                    # 尝试解析逗号分隔的字符串
                    if ',' in value:
                        return [item.strip() for item in value.split(',')]
                    # 单个值转为列表
                    return [value]
                elif not isinstance(value, list):
                    return [value]
            
            # 字典转换
            elif expected_type is dict:
                if isinstance(value, str):
                    # 尝试解析简单的键值对格式
                    try:
                        import json
                        return json.loads(value)
                    except:
                        pass
            
        except (ValueError, TypeError):
            pass
        
        return None
    
    def _get_type_name(self, type_obj: type) -> str:
        """获取类型名称的友好表示"""
        origin = get_origin(type_obj)
        
        if origin is Union:
            args = get_args(type_obj)
            # 处理Optional类型 (Union[T, None])
            if len(args) == 2 and type(None) in args:
                non_none_type = next(arg for arg in args if arg is not type(None))
                return f"Optional[{self._get_type_name(non_none_type)}]"
            else:
                arg_names = [self._get_type_name(arg) for arg in args]
                return f"Union[{', '.join(arg_names)}]"
        
        elif origin is list:
            args = get_args(type_obj)
            if args:
                return f"List[{self._get_type_name(args[0])}]"
            return "List"
        
        elif origin is dict:
            args = get_args(type_obj)
            if len(args) == 2:
                return f"Dict[{self._get_type_name(args[0])}, {self._get_type_name(args[1])}]"
            return "Dict"
        
        elif hasattr(type_obj, '__name__'):
            return type_obj.__name__
        
        else:
            return str(type_obj)


class PatternValidator(ConfigValidator):
    """模式验证器，验证字符串是否匹配指定模式"""
    
    @property
    def validation_type(self) -> ValidationType:
        return ValidationType.PATTERN
    
    def validate(self, key: str, value: Any, field_def: Any = None, config: Dict[str, Any] = None) -> ValidationResult:
        """验证字符串模式"""
        result = ValidationResult(is_valid=True)
        
        if field_def is None or not hasattr(field_def, 'pattern'):
            return result
        
        pattern = field_def.pattern
        if pattern is None:
            return result
        
        # 只对字符串进行模式验证
        if not isinstance(value, str):
            return result
        
        try:
            if not re.match(pattern, value):
                result.add_error(f"配置项 '{key}' 不匹配模式 '{pattern}'")
        except re.error as e:
            result.add_error(f"配置项 '{key}' 的模式 '{pattern}' 无效: {e}")
        
        return result
    
    def can_validate(self, field_def: Any) -> bool:
        """检查是否可以验证指定字段"""
        return hasattr(field_def, 'pattern') and field_def.pattern is not None