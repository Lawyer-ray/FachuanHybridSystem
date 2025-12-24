"""
YAML 文件配置提供者

从 YAML 文件加载配置，支持变量替换和文件监控。
"""

import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from .base import ConfigProvider
from ..exceptions import ConfigFileError, ConfigException


class YamlProvider(ConfigProvider):
    """YAML 文件配置提供者"""
    
    def __init__(self, config_path: str, watch_file: bool = True):
        """
        初始化 YAML 提供者
        
        Args:
            config_path: YAML 配置文件路径
            watch_file: 是否监控文件变化
        """
        self.config_path = Path(config_path)
        self.watch_file = watch_file
        self._last_modified = None
        self._cached_config = None
        
        # 变量替换模式：${VAR:default}
        self._var_pattern = re.compile(r'\$\{([^}:]+)(?::([^}]*))?\}')
    
    @property
    def priority(self) -> int:
        """YAML 文件具有中等优先级"""
        return 50
    
    def supports_reload(self) -> bool:
        """YAML 文件支持热重载"""
        return True
    
    def get_file_path(self) -> str:
        """
        获取配置文件路径
        
        Returns:
            str: 文件路径
        """
        return str(self.config_path)
    
    def load(self) -> Dict[str, Any]:
        """
        从 YAML 文件加载配置
        
        Returns:
            Dict[str, Any]: 配置字典
            
        Raises:
            ConfigFileError: 文件不存在或格式错误
            ConfigException: 其他配置错误
        """
        if not self.config_path.exists():
            raise ConfigFileError(
                str(self.config_path), 
                message="配置文件不存在"
            )
        
        # 检查文件是否需要重新加载
        current_modified = self.config_path.stat().st_mtime
        if (self._cached_config is not None and 
            self._last_modified == current_modified):
            return self._cached_config
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 执行变量替换
            content = self._substitute_variables(content)
            
            # 解析 YAML
            config = yaml.safe_load(content) or {}
            
            # 扁平化嵌套字典
            flattened_config = self._flatten_dict(config)
            
            # 更新缓存
            self._cached_config = flattened_config
            self._last_modified = current_modified
            
            return flattened_config
            
        except yaml.YAMLError as e:
            line_no = getattr(e, 'problem_mark', None)
            line_no = line_no.line + 1 if line_no else None
            raise ConfigFileError(
                str(self.config_path),
                line=line_no,
                message=f"YAML 格式错误: {e}"
            )
        except Exception as e:
            raise ConfigException(f"加载配置文件失败: {e}")
    
    def _substitute_variables(self, content: str) -> str:
        """
        执行变量替换
        
        支持语法：${VAR:default}
        - VAR: 环境变量名
        - default: 默认值（可选）
        
        Args:
            content: 原始内容
            
        Returns:
            str: 替换后的内容
        """
        def replace_var(match):
            var_name = match.group(1)
            default_value = match.group(2) or ""
            
            # 从环境变量获取值
            env_value = os.getenv(var_name)
            if env_value is not None:
                return env_value
            
            # 使用默认值
            return default_value
        
        return self._var_pattern.sub(replace_var, content)
    
    def _flatten_dict(self, data: Dict[str, Any], parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
        """
        扁平化嵌套字典
        
        将嵌套字典转换为点号分隔的扁平字典：
        {'a': {'b': 1}} -> {'a.b': 1}
        
        Args:
            data: 嵌套字典
            parent_key: 父键名
            sep: 分隔符
            
        Returns:
            Dict[str, Any]: 扁平化后的字典
        """
        items = []
        
        for key, value in data.items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else key
            
            if isinstance(value, dict):
                # 递归处理嵌套字典
                items.extend(self._flatten_dict(value, new_key, sep).items())
            else:
                items.append((new_key, value))
        
        return dict(items)
    
    def _unflatten_dict(self, data: Dict[str, Any], sep: str = '.') -> Dict[str, Any]:
        """
        反扁平化字典
        
        将点号分隔的扁平字典转换为嵌套字典：
        {'a.b': 1} -> {'a': {'b': 1}}
        
        Args:
            data: 扁平字典
            sep: 分隔符
            
        Returns:
            Dict[str, Any]: 嵌套字典
        """
        result = {}
        
        for key, value in data.items():
            keys = key.split(sep)
            current = result
            
            # 创建嵌套结构
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                current = current[k]
            
            # 设置最终值
            current[keys[-1]] = value
        
        return result
    
    def save_config(self, config: Dict[str, Any]) -> None:
        """
        保存配置到 YAML 文件
        
        Args:
            config: 配置字典
            
        Raises:
            ConfigFileError: 文件写入失败
        """
        try:
            # 反扁平化配置
            nested_config = self._unflatten_dict(config)
            
            # 确保目录存在
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(
                    nested_config,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    indent=2,
                    sort_keys=True
                )
            
            # 清除缓存
            self._cached_config = None
            self._last_modified = None
            
        except Exception as e:
            raise ConfigFileError(
                str(self.config_path),
                message=f"保存配置文件失败: {e}"
            )
    
    def is_file_changed(self) -> bool:
        """
        检查文件是否已变更
        
        Returns:
            bool: 文件是否已变更
        """
        if not self.config_path.exists():
            return False
        
        current_modified = self.config_path.stat().st_mtime
        return self._last_modified != current_modified
    
    def generate_template(self, config_schema: Dict[str, Any]) -> str:
        """
        根据配置模式生成 YAML 模板
        
        Args:
            config_schema: 配置模式定义
            
        Returns:
            str: YAML 模板内容
        """
        template_config = {}
        
        for key, field_info in config_schema.items():
            # 反扁平化键名
            keys = key.split('.')
            current = template_config
            
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                current = current[k]
            
            # 设置默认值和注释
            default_value = field_info.get('default', '')
            description = field_info.get('description', '')
            
            # 如果是敏感配置，使用环境变量语法
            if field_info.get('sensitive', False):
                env_var = field_info.get('env_var', key.upper().replace('.', '_'))
                current[keys[-1]] = f"${{{env_var}}}"
            else:
                current[keys[-1]] = default_value
        
        # 转换为 YAML 字符串
        return yaml.dump(
            template_config,
            default_flow_style=False,
            allow_unicode=True,
            indent=2,
            sort_keys=True
        )