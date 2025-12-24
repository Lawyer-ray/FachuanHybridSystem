"""
配置模式管理模块

提供配置模式的注册、查询和模板生成功能
"""
from typing import Dict, List, Optional, Any, Set
from .field import ConfigField
from ..exceptions import ConfigValidationError, ConfigNotFoundError


class ConfigSchema:
    """
    配置模式管理器
    
    负责管理所有配置字段的定义，提供验证和模板生成功能
    """
    
    def __init__(self):
        """初始化配置模式"""
        self._fields: Dict[str, ConfigField] = {}
        self._field_groups: Dict[str, List[str]] = {}
    
    def register(self, field: ConfigField) -> None:
        """
        注册配置字段
        
        Args:
            field: 配置字段定义
            
        Raises:
            ValueError: 如果字段名已存在
        """
        if field.name in self._fields:
            raise ValueError(f"配置字段 '{field.name}' 已存在")
        
        self._fields[field.name] = field
        
        # 自动分组（根据点号分隔的前缀）
        if '.' in field.name:
            group = field.name.split('.')[0]
            if group not in self._field_groups:
                self._field_groups[group] = []
            self._field_groups[group].append(field.name)
    
    def register_multiple(self, fields: List[ConfigField]) -> None:
        """
        批量注册配置字段
        
        Args:
            fields: 配置字段列表
        """
        for field in fields:
            self.register(field)
    
    def unregister(self, name: str) -> None:
        """
        取消注册配置字段
        
        Args:
            name: 字段名称
        """
        if name in self._fields:
            del self._fields[name]
            
            # 从分组中移除
            for group, field_names in self._field_groups.items():
                if name in field_names:
                    field_names.remove(name)
                    if not field_names:
                        del self._field_groups[group]
                    break
    
    def get_field(self, key: str) -> Optional[ConfigField]:
        """
        获取字段定义
        
        Args:
            key: 字段名称
            
        Returns:
            Optional[ConfigField]: 字段定义，如果不存在则返回 None
        """
        return self._fields.get(key)
    
    def has_field(self, key: str) -> bool:
        """
        检查字段是否存在
        
        Args:
            key: 字段名称
            
        Returns:
            bool: 字段是否存在
        """
        return key in self._fields
    
    def get_all_fields(self) -> Dict[str, ConfigField]:
        """
        获取所有字段定义
        
        Returns:
            Dict[str, ConfigField]: 所有字段定义的字典
        """
        return self._fields.copy()
    
    def get_fields_by_group(self, group: str) -> List[ConfigField]:
        """
        获取指定分组的字段
        
        Args:
            group: 分组名称
            
        Returns:
            List[ConfigField]: 该分组的字段列表
        """
        field_names = self._field_groups.get(group, [])
        return [self._fields[name] for name in field_names]
    
    def get_groups(self) -> List[str]:
        """
        获取所有分组名称
        
        Returns:
            List[str]: 分组名称列表
        """
        return list(self._field_groups.keys())
    
    def get_required_fields(self) -> List[ConfigField]:
        """
        获取所有必需字段
        
        Returns:
            List[ConfigField]: 必需字段列表
        """
        return [field for field in self._fields.values() if field.required]
    
    def get_sensitive_fields(self) -> List[ConfigField]:
        """
        获取所有敏感字段
        
        Returns:
            List[ConfigField]: 敏感字段列表
        """
        return [field for field in self._fields.values() if field.sensitive]
    
    def get_fields_with_env_vars(self) -> List[ConfigField]:
        """
        获取所有有环境变量映射的字段
        
        Returns:
            List[ConfigField]: 有环境变量映射的字段列表
        """
        return [field for field in self._fields.values() if field.env_var]
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """
        验证配置数据
        
        Args:
            config: 配置数据字典
            
        Returns:
            List[str]: 验证错误列表，空列表表示验证通过
        """
        errors = []
        
        # 检查必需字段
        for field in self.get_required_fields():
            if field.name not in config:
                errors.append(f"缺少必需配置项: {field.name}")
        
        # 检查字段值的有效性
        for key, value in config.items():
            field = self.get_field(key)
            if field is None:
                # 未定义的字段，发出警告但不阻止
                continue
            
            if not field.is_valid_value(value):
                errors.append(f"配置项 '{key}' 的值无效: {value}")
        
        # 检查依赖关系
        for field in self._fields.values():
            if field.depends_on and field.name in config:
                for dependency in field.depends_on:
                    if dependency not in config:
                        errors.append(f"配置项 '{field.name}' 依赖的配置项 '{dependency}' 不存在")
        
        return errors
    
    def validate_and_raise(self, config: Dict[str, Any]) -> None:
        """
        验证配置数据，如果有错误则抛出异常
        
        Args:
            config: 配置数据字典
            
        Raises:
            ConfigValidationError: 如果验证失败
        """
        errors = self.validate_config(config)
        if errors:
            raise ConfigValidationError(errors)
    
    def get_suggestions(self, key: str, max_suggestions: int = 5) -> List[str]:
        """
        获取配置项名称建议
        
        Args:
            key: 输入的配置项名称
            max_suggestions: 最大建议数量
            
        Returns:
            List[str]: 建议的配置项名称列表
        """
        suggestions = []
        key_lower = key.lower()
        
        # 精确匹配（忽略大小写）
        for field_name in self._fields:
            if field_name.lower() == key_lower:
                suggestions.append(field_name)
        
        # 前缀匹配
        if len(suggestions) < max_suggestions:
            for field_name in self._fields:
                if field_name.lower().startswith(key_lower) and field_name not in suggestions:
                    suggestions.append(field_name)
                    if len(suggestions) >= max_suggestions:
                        break
        
        # 包含匹配
        if len(suggestions) < max_suggestions:
            for field_name in self._fields:
                if key_lower in field_name.lower() and field_name not in suggestions:
                    suggestions.append(field_name)
                    if len(suggestions) >= max_suggestions:
                        break
        
        return suggestions
    
    def generate_template(self, include_comments: bool = True, 
                         include_sensitive: bool = False,
                         group_filter: Optional[Set[str]] = None) -> str:
        """
        生成配置模板
        
        Args:
            include_comments: 是否包含注释
            include_sensitive: 是否包含敏感字段
            group_filter: 只包含指定分组的字段
            
        Returns:
            str: YAML 格式的配置模板
        """
        lines = []
        
        if include_comments:
            lines.append("# 统一配置管理系统配置文件")
            lines.append("# 此文件由系统自动生成，请根据实际需要修改配置值")
            lines.append("")
        
        # 按分组生成配置
        for group in sorted(self.get_groups()):
            if group_filter and group not in group_filter:
                continue
                
            fields = self.get_fields_by_group(group)
            if not fields:
                continue
            
            # 过滤敏感字段
            if not include_sensitive:
                fields = [f for f in fields if not f.sensitive]
            
            if not fields:
                continue
            
            if include_comments:
                lines.append(f"# {group.upper()} 配置")
            
            lines.append(f"{group}:")
            
            for field in fields:
                field_name = field.name.split('.', 1)[1] if '.' in field.name else field.name
                
                if include_comments and field.description:
                    lines.append(f"  # {field.description}")
                
                if field.sensitive:
                    if include_comments:
                        lines.append(f"  # 敏感配置项，建议通过环境变量 {field.env_var or field.name.upper().replace('.', '_')} 设置")
                    value = f"${{{field.env_var or field.name.upper().replace('.', '_')}}}"
                else:
                    value = self._format_value(field.default)
                
                lines.append(f"  {field_name}: {value}")
                
                if include_comments:
                    lines.append("")
            
            lines.append("")
        
        # 处理没有分组的字段
        ungrouped_fields = [f for f in self._fields.values() if '.' not in f.name]
        if not include_sensitive:
            ungrouped_fields = [f for f in ungrouped_fields if not f.sensitive]
        
        if ungrouped_fields:
            if include_comments:
                lines.append("# 通用配置")
            
            for field in ungrouped_fields:
                if include_comments and field.description:
                    lines.append(f"# {field.description}")
                
                if field.sensitive:
                    if include_comments:
                        lines.append(f"# 敏感配置项，建议通过环境变量 {field.env_var or field.name.upper()} 设置")
                    value = f"${{{field.env_var or field.name.upper()}}}"
                else:
                    value = self._format_value(field.default)
                
                lines.append(f"{field.name}: {value}")
                
                if include_comments:
                    lines.append("")
        
        return '\n'.join(lines)
    
    def _format_value(self, value: Any) -> str:
        """
        格式化配置值为 YAML 格式
        
        Args:
            value: 配置值
            
        Returns:
            str: 格式化后的值
        """
        if value is None:
            return "null"
        elif isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, str):
            # 如果字符串包含特殊字符，需要加引号
            if any(char in value for char in [' ', ':', '#', '\n', '\t']):
                return f'"{value}"'
            return value
        elif isinstance(value, (list, dict)):
            # 复杂类型暂时用注释形式
            return f"# {value}"
        else:
            return str(value)
    
    def get_field_count(self) -> int:
        """
        获取字段总数
        
        Returns:
            int: 字段总数
        """
        return len(self._fields)
    
    def clear(self) -> None:
        """清空所有字段定义"""
        self._fields.clear()
        self._field_groups.clear()