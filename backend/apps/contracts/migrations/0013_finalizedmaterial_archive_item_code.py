"""Add archive_item_code to FinalizedMaterial."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0012_rename_is_archived_to_is_filed"),
    ]

    operations = [
        migrations.AddField(
            model_name="finalizedmaterial",
            name="archive_item_code",
            field=models.CharField(
                blank=True,
                default="",
                help_text="关联归档检查清单的具体编号，如 '4.2.6'、'4.2.16'",
                max_length=20,
                verbose_name="归档清单编号",
            ),
        ),
    ]
