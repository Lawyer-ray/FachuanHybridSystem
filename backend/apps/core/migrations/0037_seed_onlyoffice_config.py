"""Seed OnlyOffice（Document Server）配置项。

这三项是编辑器接入的最小集合：
- DOCSERVER_URL：浏览器可达的 DS 地址（前端加载 api.js 用）
- INTERNAL_URL：DS 容器可达的本服务地址（DS 回来取文件用）
- JWT_SECRET：DS 容器的 JWT_SECRET，用于签发 config token

默认值指向本机开发环境，生产在 Admin 里改。
"""

from __future__ import annotations

from typing import Any

from django.db import migrations


def _create_onlyoffice_configs(apps: Any, schema_editor: Any) -> None:
    SystemConfig = apps.get_model("core", "SystemConfig")

    defaults = [
        {
            "key": "ONLYOFFICE_DOCSERVER_URL",
            "value": "http://127.0.0.1:9980",
            "category": "onlyoffice",
            "description": "Document Server 地址（浏览器可达），如 http://127.0.0.1:9980 或 https://doc.example.com",
            "is_secret": False,
            "is_active": True,
        },
        {
            "key": "ONLYOFFICE_INTERNAL_URL",
            "value": "http://host.docker.internal:8002",
            "category": "onlyoffice",
            "description": "本服务对外地址（DS 容器可达），DS 用它回源取文件与回写回调",
            "is_secret": False,
            "is_active": True,
        },
        {
            "key": "ONLYOFFICE_JWT_SECRET",
            "value": "",
            "category": "onlyoffice",
            "description": "Document Server 的 JWT_SECRET（docker exec <容器> printenv JWT_SECRET）",
            "is_secret": True,
            "is_active": True,
        },
    ]

    for item in defaults:
        SystemConfig.objects.get_or_create(key=item["key"], defaults=item)


def _drop_onlyoffice_configs(apps: Any, schema_editor: Any) -> None:
    SystemConfig = apps.get_model("core", "SystemConfig")
    SystemConfig.objects.filter(
        key__in=[
            "ONLYOFFICE_DOCSERVER_URL",
            "ONLYOFFICE_INTERNAL_URL",
            "ONLYOFFICE_JWT_SECRET",
        ]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0036_add_onlyoffice_config_category"),
    ]

    operations = [
        migrations.RunPython(_create_onlyoffice_configs, _drop_onlyoffice_configs),
    ]
