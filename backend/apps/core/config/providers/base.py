"""
配置提供者基类

定义配置提供者的抽象接口，所有具体的配置提供者都需要继承此基类。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class ConfigProvider(ABC):
    """配置提供者抽象基类"""
    
    @property
    @abstractmethod
    def priority(self) -> int:
        """
        提供者优先级，数值越大优先级越高
        
        优先级规则：
        - 环境变量: 100 (最高优先级)
        - YAML文件: 50 (中等优先级)
        - Django Settings: 10 (最低优先级，向后兼容)
        
        Returns:
            int: 优先级数值
        """
        pass
    
    @abstractmethod
    def load(self) -> Dict[str, Any]:
        """
        加载配置数据
        
        Returns:
            Dict[str, Any]: 配置键值对字典
            
        Raises:
            ConfigException: 配置加载失败时抛出
        """
        pass
    
    @abstractmethod
    def supports_reload(self) -> bool:
        """
        是否支持热重载
        
        Returns:
            bool: True表示支持热重载，False表示不支持
        """
        pass
    
    def get_name(self) -> str:
        """
        获取提供者名称
        
        Returns:
            str: 提供者名称
        """
        return self.__class__.__name__
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"{self.get_name()}(priority={self.priority})"
    
    def __repr__(self) -> str:
        """调试表示"""
        return f"<{self.__class__.__name__} priority={self.priority} reload={self.supports_reload()}>"