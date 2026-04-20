"""Rename is_archived to is_filed on Case model."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0009_rename_log_chat_verbose"),
    ]

    operations = [
        migrations.RenameField(
            model_name="case",
            old_name="is_archived",
            new_name="is_filed",
        ),
    ]
