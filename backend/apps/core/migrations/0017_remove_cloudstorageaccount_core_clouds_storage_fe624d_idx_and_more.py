"""Remove CloudStorageAccount state from core (moved to apps.cloud_storage).

state-only：模型迁移到独立 app cloud_storage，数据库表 core_cloudstorageaccount
保持原样（表名在新 app 的 Meta.db_table 中钉死）。本 migration 仅从 Django
状态中移除 core.cloudstorageaccount，不做任何数据库操作。
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0032_alter_casefolderbinding_storage_account"),
        ("contracts", "0037_alter_contractfolderbinding_storage_account_and_more"),
        ("core", "0016_fix_document_parsing_config_category"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveIndex(
                    model_name="cloudstorageaccount",
                    name="core_clouds_storage_fe624d_idx",
                ),
                migrations.RemoveIndex(
                    model_name="cloudstorageaccount",
                    name="core_clouds_is_acti_2cfd68_idx",
                ),
                migrations.DeleteModel(
                    name="CloudStorageAccount",
                ),
            ],
            database_operations=[],
        ),
    ]
