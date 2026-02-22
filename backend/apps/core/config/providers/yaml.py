"""
YAML 文件配置提供者

从 YAML 文件加载配置，支持变量替换和文件监控。
"""

import os
import re
from pathlib import Path
from re import Match
from typing import Any

import yaml

from apps.core.config.exceptions import ConfigException, ConfigFileError
from .base import ConfigProvider


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
        self._last_modified: float | None = None
        self._cached_config: dict[str, Any] | None = None

        # 变量替换模式：${VAR:default}
        self._var_pattern = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")

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

    def load(self) -> dict[str, Any]:
        """
        从 YAML 文件加载配置

        Returns:
            Dict[str, Any]: 配置字典

        Raises:
            ConfigFileError: 文件不存在或格式错误
            ConfigException: 其他配置错误
        """
        if not self.config_path.exists():
            raise ConfigFileError(str(self.config_path), message="配置文件不存在")

        # 检查文件是否需要重新加载
        current_modified = self.config_path.stat().st_mtime
        if self._cached_config is not None and self._last_modified == current_modified:
            return self._cached_config

        try:
            with open(self.config_path, encoding="utf-8") as f:
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
            line_no = getattr(e, "problem_mark", None)
            line_no = line_no.line + 1 if line_no else None
            raise ConfigFileError(str(self.config_path), line=line_no, message=f"YAML 格式错误: {e}") from e
        except Exception as e:
            raise ConfigException(f"加载配置文件失败: {e}") from e

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

        def replace_var(match: Match[str]) -> str:
            var_name = match.group(1)
            default_value = match.group(2) or ""

            # 从环境变量获取值
            env_value = os.getenv(var_name)
            if env_value is not None:
                return env_value

            # 使用默认值
            return default_value

        return self._var_pattern.sub(replace_var, content)

    def _flatten_dict(self, data: dict[str, Any], parent_key: str = "", sep: str = ".") -> dict[str, Any]:
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
        items: list[tuple[str, Any]] = []

        for key, value in data.items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else key

            if isinstance(value, dict):
                # 递归处理嵌套字典
                items.extend(self._flatten_dict(value, new_key, sep).items())
            else:
                items.append((new_key, value))

        return dict(items)

