"""
环境变量配置提供者

从环境变量加载配置，支持类型转换和前缀过滤。
"""

import os
from typing import Any, Dict, Optional, Set
from .base import ConfigProvider
from ..exceptions import ConfigException


class EnvProvider(ConfigProvider):
    """环境变量配置提供者"""
    
    def __init__(self, prefix: Optional[str] = None, type_mapping: Optional[Dict[str, type]] = None):
        """
        初始化环境变量提供者
        
        Args:
            prefix: 环境变量前缀，如 "DJANGO_"
            type_mapping: 类型映射字典，键为环境变量名，值为目标类型
        """
        self.prefix = prefix or ""
        self.type_mapping = type_mapping or {}
        self._sensitive_vars: Set[str] = {
            'SECRET_KEY', 'DB_PASSWORD', 'API_KEY', 'TOKEN', 'PRIVATE_KEY'
        }
    
    @property
    def priority(self) -> int:
        """环境变量具有最高优先级"""
        return 100
    
    def supports_reload(self) -> bool:
        """环境变量不支持热重载（需要重启进程）"""
        return False
    
    def load(self) -> Dict[str, Any]:
        """
        从环境变量加载配置
        
        Returns:
            Dict[str, Any]: 配置字典
            
        Raises:
            ConfigException: 类型转换失败时抛出
        """
        config = {}
        
        for key, value in os.environ.items():
            # 应用前缀过滤
            if self.prefix and not key.startswith(self.prefix):
                continue
                
            # 移除前缀得到配置键名
            config_key = key[len(self.prefix):] if self.prefix else key
            
            # 转换为小写并用点号分隔（如 DB_HOST -> db.host）
            config_key = self._normalize_key(config_key)
            
            # 类型转换
            try:
                converted_value = self._convert_type(key, value)
                config[config_key] = converted_value
            except Exception as e:
                raise ConfigException(f"环境变量 {key} 类型转换失败: {e}")
        
        return config
    
    def _normalize_key(self, key: str) -> str:
        """
        标准化配置键名
        
        将环境变量名转换为配置键名：
        - 转换为小写
        - 下划线转换为点号
        
        Args:
            key: 原始键名
            
        Returns:
            str: 标准化后的键名
        """
        return key.lower().replace('_', '.')
    
    def _convert_type(self, key: str, value: str) -> Any:
        """
        类型转换
        
        Args:
            key: 环境变量名
            value: 环境变量值
            
        Returns:
            Any: 转换后的值
            
        Raises:
            ValueError: 类型转换失败
        """
        # 检查是否有指定的类型映射
        target_type = self.type_mapping.get(key)
        if target_type:
            return self._cast_to_type(value, target_type)
        
        # 自动类型推断
        return self._auto_cast(value)
    
    def _cast_to_type(self, value: str, target_type: type) -> Any:
        """
        转换到指定类型
        
        Args:
            value: 字符串值
            target_type: 目标类型
            
        Returns:
            Any: 转换后的值
        """
        if target_type == bool:
            return self._parse_bool(value)
        elif target_type == int:
            return int(value)
        elif target_type == float:
            return float(value)
        elif target_type == list:
            return self._parse_list(value)
        elif target_type == dict:
            return self._parse_dict(value)
        else:
            return str(value)
    
    def _auto_cast(self, value: str) -> Any:
        """
        自动类型推断和转换
        
        Args:
            value: 字符串值
            
        Returns:
            Any: 推断并转换后的值
        """
        # 布尔值
        if value.lower() in ('true', 'false', 'yes', 'no', '1', '0'):
            return self._parse_bool(value)
        
        # 整数
        if value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
            return int(value)
        
        # 浮点数
        try:
            if '.' in value:
                return float(value)
        except ValueError:
            pass
        
        # 列表（逗号分隔）
        if ',' in value:
            return self._parse_list(value)
        
        # 默认为字符串
        return value
    
    def _parse_bool(self, value: str) -> bool:
        """
        解析布尔值
        
        Args:
            value: 字符串值
            
        Returns:
            bool: 布尔值
        """
        return value.lower() in ('true', 'yes', '1', 'on', 'enabled')
    
    def _parse_list(self, value: str) -> list:
        """
        解析列表（逗号分隔）
        
        Args:
            value: 字符串值
            
        Returns:
            list: 列表
        """
        return [item.strip() for item in value.split(',') if item.strip()]
    
    def _parse_dict(self, value: str) -> dict:
        """
        解析字典（key1=val1,key2=val2格式）
        
        Args:
            value: 字符串值
            
        Returns:
            dict: 字典
        """
        result = {}
        for pair in value.split(','):
            if '=' in pair:
                key, val = pair.split('=', 1)
                result[key.strip()] = val.strip()
        return result
    
    def is_sensitive(self, key: str) -> bool:
        """
        检查是否为敏感配置
        
        Args:
            key: 配置键名
            
        Returns:
            bool: 是否为敏感配置
        """
        return any(sensitive in key.upper() for sensitive in self._sensitive_vars)
    
    def add_sensitive_pattern(self, pattern: str) -> None:
        """
        添加敏感配置模式
        
        Args:
            pattern: 敏感配置模式
        """
        self._sensitive_vars.add(pattern.upper())