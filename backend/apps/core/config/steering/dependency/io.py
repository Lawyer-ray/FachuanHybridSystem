"""Module for io."""

import logging
from typing import Any

import yaml

from apps.core.path import Path

from .model import SpecificationMetadata

logger = logging.getLogger(__name__)


class SteeringMetadataLoader:
    def __init__(self, *, steering_root: Path) -> None:
        self.steering_root = steering_root

    def load_all(self) -> dict[str, SpecificationMetadata]:
        cache: dict[str, SpecificationMetadata] = {}
        if not self.steering_root.exists():
            return cache

        for spec_file in self.steering_root.rglob("*.md"):
            try:
                rel_path = spec_file.relative_to(self.steering_root)
                spec_path = str(rel_path)
                metadata = self.load_one(spec_path)
                if metadata:
                    cache[spec_path] = metadata
            except Exception as e:
                logger.warning(f"加载规范元数据失败 {spec_file}: {e}")
        return cache

    def load_one(self, spec_path: str) -> SpecificationMetadata | None:
        full_path = self.steering_root / spec_path
        if not full_path.exists():
            return None

        try:
            with open(full_path, encoding="utf-8") as f:
                content = f.read()

            metadata_dict: dict[str, Any] = {}
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    try:
                        metadata_dict = yaml.safe_load(parts[1]) or {}
                    except yaml.YAMLError as e:
                        logger.warning(f"解析 front-matter 失败 {spec_path}: {e}")

            return SpecificationMetadata(
                path=spec_path,
                name=metadata_dict.get("name", spec_path),
                version=metadata_dict.get("version", "1.0.0"),
                priority=metadata_dict.get("priority", 0),
                tags=metadata_dict.get("tags", []),
                description=metadata_dict.get("description", ""),
                author=metadata_dict.get("author", ""),
                created_at=metadata_dict.get("created_at"),
                updated_at=metadata_dict.get("updated_at"),
                inherits=self._normalize_dependency_list(metadata_dict.get("inherits", [])),
                requires=self._normalize_dependency_list(metadata_dict.get("requires", [])),
                optional_deps=self._normalize_dependency_list(metadata_dict.get("optional", [])),
                conflicts=self._normalize_dependency_list(metadata_dict.get("conflicts", [])),
                inclusion=metadata_dict.get("inclusion", "manual"),
                file_match_pattern=metadata_dict.get("fileMatchPattern"),
                load_condition=metadata_dict.get("loadCondition"),
            )
        except Exception as e:
            logger.error(f"加载规范元数据失败 {spec_path}: {e}")
            return None

    def _normalize_dependency_list(self, deps: Any) -> list[str]:
        if isinstance(deps, str):
            return [deps]
        if isinstance(deps, list):
            return [str(dep) for dep in deps]
        return []
