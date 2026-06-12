"""清理 SiliconFlow 相关配置项

移除已废弃的 SILICONFLOW_* 配置项，这些配置不再被任何代码读取。
"""

from django.db import migrations


def remove_siliconflow_configs(apps, schema_editor):  # pragma: no cover
    """删除所有 SILICONFLOW_* 配置项"""
    SystemConfig = apps.get_model("core", "SystemConfig")
    deleted, _ = SystemConfig.objects.filter(key__startswith="SILICONFLOW_").delete()
    if deleted:
        print(f"  已删除 {deleted} 条 SILICONFLOW_* 配置项")


def reverse_migration(apps, schema_editor):  # pragma: no cover
    """反向迁移：不做任何操作（删除的数据无法恢复）"""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_migrate_paddleocr_v2_job_api"),
    ]

    operations = [
        migrations.RunPython(remove_siliconflow_configs, reverse_migration),
    ]
