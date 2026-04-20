"""Rename is_archived to is_filed on Contract model."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0011_alter_contract_status"),
    ]

    operations = [
        migrations.RenameField(
            model_name="contract",
            old_name="is_archived",
            new_name="is_filed",
        ),
    ]
