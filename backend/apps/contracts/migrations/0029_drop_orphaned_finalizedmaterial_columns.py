"""Drop orphaned columns from contracts_finalizedmaterial.

These columns (relative_file_path, storage_root_type, subdir_path) exist in
the database but are not declared in the FinalizedMaterial model. They were
likely added by a migration that was later reverted without cleaning up the DB.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0028_p3_protect_payment_fk"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "ALTER TABLE contracts_finalizedmaterial DROP COLUMN IF EXISTS relative_file_path;",
                "ALTER TABLE contracts_finalizedmaterial DROP COLUMN IF EXISTS storage_root_type;",
                "ALTER TABLE contracts_finalizedmaterial DROP COLUMN IF EXISTS subdir_path;",
            ],
            reverse_sql=[
                "ALTER TABLE contracts_finalizedmaterial ADD COLUMN relative_file_path varchar(1000) NOT NULL DEFAULT '';",
                "ALTER TABLE contracts_finalizedmaterial ADD COLUMN storage_root_type varchar(100) NOT NULL DEFAULT '';",
                "ALTER TABLE contracts_finalizedmaterial ADD COLUMN subdir_path varchar(1000) NOT NULL DEFAULT '';",
            ],
        ),
    ]
