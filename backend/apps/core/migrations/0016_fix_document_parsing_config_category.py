"""回填文档解析相关配置项的 category 到 document_parsing

历史遗留问题：在 0011_add_document_parsing_category（2026-06-11）之前，
SystemConfig.category 的 default 是 general。如果在 0011 之前执行过
init_system_config，TEXTIN_APP_ID / TEXTIN_SECRET_CODE / DOCUMENT_PARSING_BACKEND
/ MINERU_API_KEY 等记录会被创建成 category=general，导致 Admin 分组显示时
它们被归到「通用配置」而不是「文档解析配置」。

种子代码（_document_parsing_configs.py）的 category 一直是 document_parsing，
但 get_or_create 不会回填已存在记录的 category，所以必须用 data migration 修正。
"""

import logging
from typing import Any

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

logger = logging.getLogger(__name__)

# 文档解析相关的所有 SystemConfig key
DOCUMENT_PARSING_KEYS = [
    "DOCUMENT_PARSING_BACKEND",
    "MINERU_API_KEY",
    "TEXTIN_APP_ID",
    "TEXTIN_SECRET_CODE",
]


def fix_category(apps: Any, schema_editor: BaseDatabaseSchemaEditor) -> None:  # pragma: no cover
    """把文档解析相关配置项的 category 改为 document_parsing"""
    SystemConfig = apps.get_model("core", "SystemConfig")
    updated = SystemConfig.objects.filter(
        key__in=DOCUMENT_PARSING_KEYS,
    ).exclude(category="document_parsing").update(category="document_parsing")
    if updated:
        logger.info("已回填 %d 条文档解析配置项的 category 到 document_parsing", updated)


def reverse_migration(apps: Any, schema_editor: BaseDatabaseSchemaEditor) -> None:  # pragma: no cover
    """反向迁移：不做任何操作（category 修正不可逆，原值无意义）"""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0015_redisqueuetool"),
    ]

    operations = [
        migrations.RunPython(fix_category, reverse_migration),
    ]
