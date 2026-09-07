"""Point CaseFolderBinding.storage_account to the new cloud_storage app label.

state-only：FK 目标从 core.cloudstorageaccount 改为 cloud_storage.cloudstorageaccount，
数据库层面表/列均未变化，无需任何数据库操作。
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0031_alter_case_previous_case_and_more"),
        ("cloud_storage", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="casefolderbinding",
                    name="storage_account",
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="cloud_storage.cloudstorageaccount", verbose_name="云存储账号"),
                ),
            ],
            database_operations=[],
        ),
    ]
