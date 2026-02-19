"""
配置导入导出

提供配置的导入和导出功能,支持YAML和JSON格式.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .exceptions import ConfigException, ConfigFileError, ConfigValidationError
from .schema.schema import ConfigSchema
from .validators.base import ConfigValidator

logger = logging.getLogger(__name__)


class ImportExportManager:
    """配置导入导出管理器"""

    def __init__(self, schema: ConfigSchema | None = None, validator: ConfigValidator | None = None) -> None:
        """
        初始化导入导出管理器

        Args:
            schema: 配置模式
            validator: 配置验证器
        """
        self._schema = schema
        self._validator = validator

    def export(
        self,
        config_data: dict[str, Any],
        path: str,
        format: str = "yaml",
        mask_sensitive: bool = True,
        include_metadata: bool = True,
    ) -> None:
        """
        导出配置到文件

        Args:
            config_data: 要导出的配置数据
            path: 导出文件路径
            format: 导出格式 ('yaml', 'json')
            mask_sensitive: 是否对敏感信息进行脱敏处理
            include_metadata: 是否包含元数据信息

        Raises:
            ConfigException: 导出失败
        """
        try:
            # 准备导出数据
            export_data = self._prepare_export_data(config_data, mask_sensitive, include_metadata)

            # 确保目录存在
            Path(path).parent.mkdir(parents=True, exist_ok=True)

            # 根据格式导出
            if format.lower() == "yaml":
                self._export_yaml(path, export_data)
            elif format.lower() == "json":
                self._export_json(path, export_data)
            else:
                raise ConfigException(f"不支持的导出格式: {format}")

            logger.info(f"配置已导出到: {path}")

        except Exception as e:
            raise ConfigException(f"导出配置失败: {e}") from e

    def import_config(self, path: str, format: str | None = None, validate: bool = True) -> dict[str, Any]:
        """
        从文件导入配置

        Args:
            path: 导入文件路径
            format: 文件格式 ('yaml', 'json'),如果为None则根据文件扩展名自动检测
            validate: 是否验证导入的配置

        Returns:
            dict[str, Any]: 导入的配置数据(扁平化格式)

        Raises:
            ConfigException: 导入失败
            ConfigFileError: 文件读取失败
            ConfigValidationError: 配置验证失败
        """
        if not Path(path).exists():
            raise ConfigFileError(path, message="文件不存在")

        try:
            # 自动检测格式
            if format is None:
                format = self._detect_file_format(path)

            # 读取文件数据
            import_data = self._load_import_file(path, format)

            # 验证导入数据结构
            self._validate_import_data(import_data)

            # 提取配置数据
            config_data = self._extract_config_data(import_data)

            # 验证配置完整性和有效性
            if validate:
                self._validate_imported_config(config_data)

            logger.info(f"配置已从 {path} 导入")
            return config_data

        except Exception as e:
            if isinstance(e, (ConfigException, ConfigFileError, ConfigValidationError)):
                raise
            else:
                raise ConfigException(f"导入配置失败: {e}") from e

    def _prepare_export_data(
        self, config_data: dict[str, Any], mask_sensitive: bool, include_metadata: bool
    ) -> dict[str, Any]:
        """
        准备导出数据

        Args:
            config_data: 配置数据
            mask_sensitive: 是否脱敏敏感信息
            include_metadata: 是否包含元数据

        Returns:
            dict[str, Any]: 准备好的导出数据
        """
        export_data = {}

        # 添加元数据
        if include_metadata:
            export_data["_metadata"] = {
                "export_time": datetime.now().isoformat(),
                "config_manager_version": "1.0.0",
                "total_configs": len(config_data),
                "masked_sensitive": mask_sensitive,
            }

        # 处理配置数据
        processed_config = {}
        for key, value in config_data.items():
            # 检查是否为敏感配置
            is_sensitive = self._is_sensitive_config(key)

            if is_sensitive and mask_sensitive:
                # 脱敏处理
                processed_config[key] = self._mask_sensitive_value(value)
            else:
                processed_config[key] = value

        # 将扁平化的配置转换为嵌套结构
        export_data["config"] = self._flatten_to_nested(processed_config)

        return export_data

    def _is_sensitive_config(self, key: str) -> bool:
        """
        检查配置项是否为敏感配置

        Args:
            key: 配置键

        Returns:
            bool: 是否为敏感配置
        """
        if self._schema:
            field = self._schema.get_field(key)
            if field and field.sensitive:
                return True

        # 基于键名的启发式判断
        sensitive_keywords = [
            "password",
            "secret",
            "key",
            "token",
            "credential",
            "private",
            "auth",
            "api_key",
            "access_key",
        ]

        key_lower = key.lower()
        return any(keyword in key_lower for keyword in sensitive_keywords)

    def _mask_sensitive_value(self, value: Any) -> str | None:
        """
        对敏感值进行脱敏处理

        Args:
            value: 原始值

        Returns:
            str: 脱敏后的值
        """
        if value is None:
            return None

        str_value = str(value)
        if len(str_value) <= 4:
            return "***"
        elif len(str_value) <= 8:
            return str_value[:2] + "***" + str_value[-1:]
        else:
            return str_value[:3] + "***" + str_value[-2:]

    def _flatten_to_nested(self, flat_config: dict[str, Any]) -> dict[str, Any]:
        """
        将扁平化配置转换为嵌套结构

        Args:
            flat_config: 扁平化的配置字典

        Returns:
            dict[str, Any]: 嵌套结构的配置字典
        """
        nested: dict[str, Any] = {}

        for key, value in flat_config.items():
            keys = key.split(".")
            current = nested

            # 构建嵌套结构
            for _i, k in enumerate(keys[:-1]):
                if k not in current:
                    current[k] = {}
                current = current[k]

            # 设置最终值
            current[keys[-1]] = value

        return nested

    def _export_yaml(self, path: str, data: dict[str, Any]) -> None:
        """
        导出为YAML格式

        Args:
            path: 文件路径
            data: 导出数据
        """
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False, indent=2)

    def _export_json(self, path: str, data: dict[str, Any]) -> None:
        """
        导出为JSON格式

        Args:
            path: 文件路径
            data: 导出数据
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)

    def _detect_file_format(self, path: str) -> str:
        """
        根据文件扩展名检测格式

        Args:
            path: 文件路径

        Returns:
            str: 文件格式
        """
        ext = Path(path).suffix.lower()
        if ext in [".yaml", ".yml"]:
            return "yaml"
        elif ext == ".json":
            return "json"
        else:
            raise ConfigException(f"无法检测文件格式: {path}")

    def _load_import_file(self, path: str, format: str) -> dict[str, Any]:
        """
        加载导入文件

        Args:
            path: 文件路径
            format: 文件格式

        Returns:
            dict[str, Any]: 文件数据
        """
        try:
            with open(path, encoding="utf-8") as f:
                if format == "yaml":
                    return yaml.safe_load(f) or {}
                elif format == "json":
                    return json.load(f) or {}
                else:
                    raise ConfigException(f"不支持的文件格式: {format}")
        except yaml.YAMLError as e:
            raise ConfigFileError(path, message=f"YAML格式错误: {e}") from e
        except json.JSONDecodeError as e:
            raise ConfigFileError(path, line=e.lineno, message=f"JSON格式错误: {e.msg}") from e
        except Exception as e:
            raise ConfigFileError(path, message=f"文件读取失败: {e}") from e

    def _validate_import_data(self, data: dict[str, Any]) -> None:
        """
        验证导入数据结构

        Args:
            data: 导入的数据

        Raises:
            ConfigValidationError: 数据结构无效
        """
        if not isinstance(data, dict):
            raise ConfigValidationError(["导入数据必须是字典格式"])

        # 检查是否包含配置数据
        if "config" not in data and "_metadata" not in data:
            # 可能是直接的配置数据
            return

        if "config" in data and not isinstance(data["config"], dict):
            raise ConfigValidationError(["配置数据必须是字典格式"])

    def _extract_config_data(self, import_data: dict[str, Any]) -> dict[str, Any]:
        """
        从导入数据中提取配置

        Args:
            import_data: 导入的数据

        Returns:
            dict[str, Any]: 扁平化的配置数据
        """
        if "config" in import_data:
            # 标准格式,包含元数据
            config_data = import_data["config"]
        else:
            # 直接的配置数据
            config_data = import_data

        # 将嵌套结构转换为扁平化
        return self._nested_to_flatten(config_data)

    def _nested_to_flatten(self, nested_config: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        """
        将嵌套配置转换为扁平化结构

        Args:
            nested_config: 嵌套的配置字典
            prefix: 键前缀

        Returns:
            dict[str, Any]: 扁平化的配置字典
        """
        flat_config = {}

        for key, value in nested_config.items():
            full_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                # 递归处理嵌套字典
                flat_config.update(self._nested_to_flatten(value, full_key))
            else:
                flat_config[full_key] = value

        return flat_config

    def _validate_imported_config(self, config_data: dict[str, Any]) -> None:
        """
        验证导入的配置

        Args:
            config_data: 配置数据

        Raises:
            ConfigValidationError: 验证失败
        """
        errors: list[Any] = []

        # 使用模式验证
        if self._schema:
            for key, value in config_data.items():
                field = self._schema.get_field(key)
                if field and not field.is_valid_value(value):
                    errors.append(f"配置项 '{key}' 值无效: {value}")

        # 使用验证器验证
        if self._validator:
            for key, value in config_data.items():
                field_def = self._schema.get_field(key) if self._schema else None
                result = self._validator.validate(key, value, field_def, config_data)
                if not result.is_valid:
                    errors.extend(result.errors)

        if errors:
            raise ConfigValidationError(errors)
