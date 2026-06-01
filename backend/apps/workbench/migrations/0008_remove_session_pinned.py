"""Remove phantom pinned and tags columns from workbench_session."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("workbench", "0007_backfill_session_storage_bytes"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "ALTER TABLE workbench_session DROP COLUMN IF EXISTS pinned;",
                "ALTER TABLE workbench_session DROP COLUMN IF EXISTS tags;",
            ],
            reverse_sql=[
                "ALTER TABLE workbench_session ADD COLUMN pinned boolean DEFAULT false NOT NULL;",
                "ALTER TABLE workbench_session ADD COLUMN tags jsonb DEFAULT '[]'::jsonb NOT NULL;",
            ],
        ),
    ]
