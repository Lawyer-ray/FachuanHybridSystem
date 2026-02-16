"""
配置字段定义模块

定义配置项的结构和约束
"""
from dataclasses import dataclass, field
from typing import Any, List, Optional, Union, Callable


@dataclass
class ConfigField:
    """
    配置字段定义
    
    定义单个配置项的类型、默认值、验证规则等属性
    """
    
    name: str
    """配置字段名称，支持点号路径（如 'database.host'）"""
    
    type: type
    """配置字段类型（str, int, bool, float, list, dict 等）"""
    
    default: Any = None
    """默认值，当配置项不存在时使用"""
    
    required: bool = False
    """是否为必需字段，True 表示必须提供值"""
    
    sensitive: bool = False
    """是否为敏感字段，敏感字段在生产环境必须通过环境变量设置"""
    
    description: str = ""
    """字段描述，用于生成配置文档和模板"""
    
    min_value: Optional[Union[int, float]] = None
    """最小值限制（适用于数值类型）"""
    
    max_value: Optional[Union[int, float]] = None
    """最大值限制（适用于数值类型）"""
    
    min_length: Optional[int] = None
    """最小长度限制（适用于字符串和列表类型）"""
    
    max_length: Optional[int] = None
    """最大长度限制（适用于字符串和列表类型）"""
    
    pattern: Optional[str] = None
    """正则表达式模式（适用于字符串类型）"""
    
    choices: Optional[List[Any]] = None
    """可选值列表，值必须在此列表中"""
    
    depends_on: Optional[List[str]] = None
    """依赖的配置项列表，这些配置项必须存在"""
    
    env_var: Optional[str] = None
    """对应的环境变量名，如果设置则优先从环境变量读取"""
    
    validator: Optional[Callable[[Any], bool]] = None
    """自定义验证函数，接收配置值并返回是否有效"""
    
    transformer: Optional[Callable[[Any], Any]] = None
    """值转换函数，用于在设置配置值时进行转换"""
    
    def __post_init__(self):
        """初始化后处理"""
        # 如果没有设置 depends_on，初始化为空列表
        if self.depends_on is None:
            self.depends_on = []
        
        # 如果没有设置 choices，初始化为空列表
        if self.choices is None:
            self.choices = []
        
        # 验证字段定义的一致性
        self._validate_field_definition()
    
    def _validate_field_definition(self):
        """验证字段定义的一致性"""
        # 检查数值范围设置是否合理
        if self.min_value is not None and self.max_value is not None:
            if self.min_value > self.max_value:
                raise ValueError(f"字段 '{self.name}' 的 min_value ({self.min_value}) 不能大于 max_value ({self.max_value})")
        
        # 检查长度范围设置是否合理
        if self.min_length is not None and self.max_length is not None:
            if self.min_length > self.max_length:
                raise ValueError(f"字段 '{self.name}' 的 min_length ({self.min_length}) 不能大于 max_length ({self.max_length})")
        
        # 检查必需字段是否有默认值
        if self.required and self.default is not None:
            raise ValueError(f"字段 '{self.name}' 不能同时设置为必需字段和提供默认值")
    
    def is_valid_type(self, value: Any) -> bool:
        """
        检查值是否符合字段类型
        
        Args:
            value: 要检查的值
            
        Returns:
            bool: 是否符合类型要求
        """
        if value is None:
            return not self.required
        
        # 基本类型检查
        if not isinstance(value, self.type):
            # 尝试类型转换
            try:
                if self.type == bool and isinstance(value, str):
                    # 字符串到布尔值的特殊处理
                    return value.lower() in ('true', 'false', '1', '0', 'yes', 'no')
                elif self.type in (int, float) and isinstance(value, str):
                    # 字符串到数值的转换检查
                    self.type(value)
                    return True
                else:
                    return False
            except (ValueError, TypeError):
                return False
        
        return True
    
    def is_valid_value(self, value: Any) -> bool:
        """
        检查值是否符合字段的所有约束
        
        Args:
            value: 要检查的值
            
        Returns:
            bool: 是否符合所有约束
        """
        if not self.is_valid_type(value):
            return False
        
        if value is None:
            return not self.required
        
        # 检查可选值限制
        if self.choices and value not in self.choices:
            return False
        
        # 检查数值范围
        if isinstance(value, (int, float)):
            if self.min_value is not None and value < self.min_value:
                return False
            if self.max_value is not None and value > self.max_value:
                return False
        
        # 检查长度限制
        if hasattr(value, '__len__'):
            length = len(value)
            if self.min_length is not None and length < self.min_length:
                return False
            if self.max_length is not None and length > self.max_length:
                return False
        
        # 检查正则表达式模式
        if self.pattern and isinstance(value, str):
            import re
            if not re.match(self.pattern, value):
                return False
        
        # 执行自定义验证
        if self.validator and not self.validator(value):
            return False
        
        return True
    
    def transform_value(self, value: Any) -> Any:
        """
        转换配置值
        
        Args:
            value: 原始值
            
        Returns:
            Any: 转换后的值
        """
        if value is None:
            return self.default
        
        # 执行自定义转换
        if self.transformer:
            value = self.transformer(value)
        
        # 执行类型转换
        if not isinstance(value, self.type):
            try:
                if self.type == bool and isinstance(value, str):
                    # 字符串到布尔值的转换
                    return value.lower() in ('true', '1', 'yes', 'on')
                else:
                    return self.type(value)
            except (ValueError, TypeError):
                # 转换失败，返回原值
                pass
        
        return value
    
    def get_env_var_name(self) -> Optional[str]:
        """
        获取环境变量名
        
        Returns:
            Optional[str]: 环境变量名，如果没有设置则返回 None
        """
        return self.env_var
    
    def to_dict(self) -> dict:
        """
        转换为字典表示
        
        Returns:
            dict: 字段定义的字典表示
        """
        return {
            'name': self.name,
            'type': self.type.__name__,
            'default': self.default,
            'required': self.required,
            'sensitive': self.sensitive,
            'description': self.description,
            'min_value': self.min_value,
            'max_value': self.max_value,
            'min_length': self.min_length,
            'max_length': self.max_length,
            'pattern': self.pattern,
            'choices': self.choices,
            'depends_on': self.depends_on,
            'env_var': self.env_var
        }