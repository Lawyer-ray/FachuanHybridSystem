"""Module for analyzer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from apps.core.path import Path


@dataclass(frozen=True)
class DjangoSettingsAnalysis:
    total_configs: int
    config_types: dict[str, int]
    sensitive_configs: list[str]
    complex_configs: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_configs": self.total_configs,
            "config_types": self.config_types,
            "sensitive_configs": self.sensitive_configs,
            "complex_configs": self.complex_configs,
        }


class DjangoSettingsAnalyzer:
    def __init__(self, *, backup_dir: str) -> None:
        self.backup_dir = backup_dir

    def analyze_and_persist(self, *, migration_id: str, django_configs: dict[str, Any]) -> DjangoSettingsAnalysis:
        config_types: dict[str, int] = {}
        sensitive_configs: list[str] = []
        complex_configs: list[str] = []

        for key, value in django_configs.items():
            config_type = type(value).__name__
            config_types[config_type] = config_types.get(config_type, 0) + 1

            if self.is_sensitive_key(key):
                sensitive_configs.append(key)

            if isinstance(value, (dict, list)) and len(str(value)) > 100:
                complex_configs.append(key)

        analysis = DjangoSettingsAnalysis(
            total_configs=len(django_configs),
            config_types=config_types,
            sensitive_configs=sensitive_configs,
            complex_configs=complex_configs,
        )

        analysis_file = str(Path(self.backup_dir) / f"{migration_id}_analysis.json")
        with open(analysis_file, "w", encoding="utf-8") as f:
            json.dump(analysis.to_dict(), f, ensure_ascii=False, indent=2, default=str)

        return analysis

    def is_sensitive_key(self, key: str) -> bool:
        sensitive_keywords = [
            "SECRET",
            "KEY",
            "PASSWORD",
            "TOKEN",
            "CREDENTIAL",
            "PRIVATE",
            "AUTH",
            "API_KEY",
            "ACCESS_KEY",
        ]
        key_upper = key.upper()
        return any(keyword in key_upper for keyword in sensitive_keywords)
