"""Remove 'closed' from ContractStatus choices and migrate existing data.

合同状态流转调整为：未签约 → 在办 → 已归档，
删除不再使用的"已结案"状态，已有 closed 数据迁移为 archived。
"""

from django.db import migrations, models


def migrate_closed_to_archived(apps, schema_editor):
    Contract = apps.get_model("contracts", "Contract")
    Contract.objects.filter(status="closed").update(status="archived")


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0022_alter_finalizedmaterial_default_category"),
    ]

    operations = [
        # 先将已有的 closed 合同数据迁移为 archived
        migrations.RunPython(migrate_closed_to_archived, migrations.RunPython.noop),
        # 再从 choices 中移除 closed
        migrations.AlterField(
            model_name="contract",
            name="status",
            field=models.CharField(
                choices=[("unsigned", "未签约"), ("active", "在办"), ("archived", "已归档")],
                default="active",
                max_length=32,
                verbose_name="合同状态",
            ),
        ),
    ]
