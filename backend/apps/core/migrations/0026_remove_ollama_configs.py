"""清理 Ollama 相关配置项

2026-09 Ollama 全面下线：本地后端代码与配置读取入口已删除，
LLM 供给统一收敛到 AI 平台表（LLMProvider）。本迁移移除不再被
任何代码读取的 OLLAMA_* 与 LLM_BACKEND_OLLAMA_* SystemConfig 项。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import migrations

logger = logging.getLogger(__name__)

_OLLAMA_KEY_PREFIXES = ("OLLAMA_", "LLM_BACKEND_OLLAMA_")


def remove_ollama_configs(apps: Any, schema_editor: Any) -> None:  # pragma: no cover
    """删除所有 Ollama 相关配置项"""
    SystemConfig = apps.get_model("core", "SystemConfig")
    total = 0
    for prefix in _OLLAMA_KEY_PREFIXES:
        deleted, _ = SystemConfig.objects.filter(key__startswith=prefix).delete()
        total += deleted
    if total:
        logger.info("已删除 %d 条 Ollama 相关配置项（OLLAMA_* / LLM_BACKEND_OLLAMA_*）", total)


def reverse_migration(apps: Any, schema_editor: Any) -> None:  # pragma: no cover
    """反向迁移：不做任何操作（删除的数据无法恢复）"""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0025_alter_systemconfig_category"),
    ]

    operations = [
        migrations.RunPython(remove_ollama_configs, reverse_migration),
    ]
