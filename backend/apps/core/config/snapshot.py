"""
配置快照管理

提供配置快照的创建、恢复、列表和删除功能.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import yaml

from .exceptions import ConfigException, ConfigFileError, ConfigValidationError

logger = logging.getLogger(__name__)


class SnapshotManager:
    """配置快照管理器"""

    def __init__(self, snapshot_dir: str | None = None) -> None:
        """
        初始化快照管理器

        Args:
            snapshot_dir: 快照目录路径,如果为None则使用默认目录
        """
        self._snapshot_dir = snapshot_dir or self._get_default_snapshot_directory()

    def create_snapshot(self, config_data: dict[str, Any], name: str | None = None, description: str = "") -> str:
        """
        创建配置快照

        Args:
            config_data: 要保存的配置数据
            name: 快照名称,如果为None则自动生成
            description: 快照描述

        Returns:
            str: 快照ID

        Raises:
            ConfigException: 创建快照失败
        """
        try:
            # 生成快照ID和名称
            timestamp = datetime.now()
            snapshot_id = timestamp.strftime("%Y%m%d_%H%M%S")
            if name:
                snapshot_name = f"{snapshot_id}_{name}"
            else:
                snapshot_name = snapshot_id

            # 创建快照数据
            snapshot_data = {
                "id": snapshot_id,
                "name": snapshot_name,
                "description": description,
                "created_at": timestamp.isoformat(),
                "config_count": len(config_data),
                "config": config_data.copy(),
            }

            # 确保快照目录存在
            Path(self._snapshot_dir).mkdir(parents=True, exist_ok=True)

            # 保存快照
            snapshot_path = Path(self._snapshot_dir) / f"{snapshot_name}.yaml"
            with open(snapshot_path, "w", encoding="utf-8") as f:
                yaml.dump(snapshot_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False, indent=2)

            logger.info(f"配置快照已创建: {snapshot_id}")
            return snapshot_id

        except Exception as e:
            raise ConfigException(f"创建配置快照失败: {e}") from e

    def restore_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        """
        从快照恢复配置

        Args:
            snapshot_id: 快照ID或名称

        Returns:
            dict[str, Any]: 快照中的配置数据

        Raises:
            ConfigException: 恢复失败
            ConfigFileError: 快照文件不存在
        """
        try:
            # 查找快照文件
            snapshot_path = self._find_snapshot_file(snapshot_id)
            if not snapshot_path:
                raise ConfigFileError(snapshot_id, message="快照不存在")

            # 加载快照数据
            with open(snapshot_path, encoding="utf-8") as f:
                snapshot_data = yaml.safe_load(f)

            # 验证快照数据
            self._validate_snapshot_data(snapshot_data)

            # 提取配置数据
            config_data = snapshot_data["config"]

            logger.info(f"配置快照已恢复: {snapshot_id}")
            return cast(dict[str, Any], config_data)

        except Exception as e:
            if isinstance(e, (ConfigException, ConfigFileError)):
                raise
            else:
                raise ConfigException(f"恢复配置快照失败: {e}") from e

    def list_snapshots(self) -> list[dict[str, Any]]:
        """
        列出所有快照

        Returns:
            list[dict[str, Any]]: 快照信息列表
        """
        snapshots: list[Any] = []
        snapshot_dir = Path(self._snapshot_dir)

        if not snapshot_dir.exists():
            return snapshots

        try:
            for file_path in snapshot_dir.glob("*.yaml"):
                try:
                    with open(file_path, encoding="utf-8") as f:
                        snapshot_data = yaml.safe_load(f)

                    # 提取快照信息
                    snapshot_info = {
                        "id": snapshot_data.get("id", ""),
                        "name": snapshot_data.get("name", ""),
                        "description": snapshot_data.get("description", ""),
                        "created_at": snapshot_data.get("created_at", ""),
                        "config_count": snapshot_data.get("config_count", 0),
                        "file_path": str(file_path),
                    }
                    snapshots.append(snapshot_info)

                except (OSError, ValueError, KeyError):
                    # 忽略损坏的快照文件
                    continue

            # 按创建时间排序
            snapshots.sort(key=lambda x: x["created_at"], reverse=True)

        except (OSError, ValueError) as e:
            raise ConfigException(f"列出快照失败: {e}") from e

        return snapshots

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """
        删除快照

        Args:
            snapshot_id: 快照ID或名称

        Returns:
            bool: 是否成功删除
        """
        try:
            snapshot_path = self._find_snapshot_file(snapshot_id)
            if snapshot_path and Path(snapshot_path).exists():
                Path(snapshot_path).unlink()
                logger.info(f"配置快照已删除: {snapshot_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"删除快照失败: {e}")
            return False

    def _get_default_snapshot_directory(self) -> str:
        """
        获取默认快照目录路径

        Returns:
            str: 快照目录路径
        """
        # 默认在当前工作目录下的 .config_snapshots 目录
        return str(Path.cwd() / ".config_snapshots")

    def _find_snapshot_file(self, snapshot_id: str) -> str | None:
        """
        查找快照文件

        Args:
            snapshot_id: 快照ID或名称

        Returns:
            str | None: 快照文件路径,如果不存在则返回None
        """
        snapshot_dir = Path(self._snapshot_dir)
        if not snapshot_dir.exists():
            return None

        # 尝试直接匹配文件名
        direct_path = snapshot_dir / f"{snapshot_id}.yaml"
        if direct_path.exists():
            return str(direct_path)

        # 搜索包含ID的文件
        for file_path in snapshot_dir.glob("*.yaml"):
            if snapshot_id in file_path.name:
                return str(file_path)

        return None

    def _validate_snapshot_data(self, snapshot_data: dict[str, Any]) -> None:
        """
        验证快照数据

        Args:
            snapshot_data: 快照数据

        Raises:
            ConfigValidationError: 快照数据无效
        """
        required_fields = ["id", "name", "created_at", "config"]
        errors: list[Any] = []

        for field in required_fields:
            if field not in snapshot_data:
                errors.append(f"快照数据缺少必需字段: {field}")

        if "config" in snapshot_data and not isinstance(snapshot_data["config"], dict):
            errors.append("快照配置数据必须是字典格式")

        if errors:
            raise ConfigValidationError(errors)
