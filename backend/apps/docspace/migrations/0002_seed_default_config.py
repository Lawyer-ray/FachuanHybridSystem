"""Seed default DocSpace configuration entries."""

from __future__ import annotations

from django.db import migrations


def _create_docspace_configs(apps, schema_editor):  # noqa: ARG001
    SystemConfig = apps.get_model("core", "SystemConfig")

    defaults = [
        {
            "key": "DOCSPACE_PORTAL_URL",
            "value": "",
            "category": "docspace",
            "description": "DocSpace Portal 地址，如 https://fachuan.onlyoffice.com",
            "is_secret": False,
            "is_active": True,
        },
        {
            "key": "DOCSPACE_API_TOKEN",
            "value": "",
            "category": "docspace",
            "description": "DocSpace API Token（Bearer Token），在 Settings → Developer Tools 中获取",
            "is_secret": True,
            "is_active": True,
        },
        {
            "key": "DOCSPACE_ROOT_FOLDER_ID",
            "value": "0",
            "category": "docspace",
            "description": "默认上传文件夹 ID（留空则自动从 DocSpace API 获取当前用户的「我的文档」文件夹 ID）",
            "is_secret": False,
            "is_active": True,
        },
    ]

    for item in defaults:
        SystemConfig.objects.get_or_create(key=item["key"], defaults=item)


def _reverse(apps, schema_editor):  # noqa: ARG001
    SystemConfig = apps.get_model("core", "SystemConfig")
    SystemConfig.objects.filter(category="docspace").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("docspace", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_create_docspace_configs, _reverse),
    ]
