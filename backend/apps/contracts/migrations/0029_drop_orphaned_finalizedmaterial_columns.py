"""Drop orphaned columns from contracts_finalizedmaterial.

These columns (relative_file_path, storage_root_type, subdir_path) exist in
the database but are not declared in the FinalizedMaterial model. They were
likely added by a migration that was later reverted without cleaning up the DB.

注意：原先用裸 ``RunSQL`` + ``DROP COLUMN IF EXISTS``，那是 PostgreSQL 专有语法。
E2E 走 ``DB_ENGINE=sqlite``（见 backend-ci.yml 的 backend-e2e-nightly），
SQLite 不认 ``DROP COLUMN IF EXISTS``，迁移链在建表阶段直接
``sqlite3.OperationalError: near "EXISTS": syntax error``，导致 E2E 全量 ERROR。
这里改成 ``RunPython`` + introspection 判列，两种后端都能跑，且保持幂等。
"""

from __future__ import annotations

from typing import Any

from django.db import migrations

TABLE_NAME = "contracts_finalizedmaterial"

# 列名 -> 列定义（回滚时据此重建）。与历史 ADD COLUMN 语句保持一致。
ORPHANED_COLUMNS = {
    "relative_file_path": "varchar(1000) NOT NULL DEFAULT ''",
    "storage_root_type": "varchar(100) NOT NULL DEFAULT ''",
    "subdir_path": "varchar(1000) NOT NULL DEFAULT ''",
}


def _existing_columns(schema_editor: Any, table_name: str) -> set[str]:
    """返回表的实际列名集合；表不存在时返回空集合。"""
    connection = schema_editor.connection
    introspection = connection.introspection
    with connection.cursor() as cursor:
        if table_name not in set(introspection.table_names(cursor)):
            return set()
        description = introspection.get_table_description(cursor, table_name)
    return {column.name for column in description}


def drop_orphaned_columns(apps: Any, schema_editor: Any) -> None:
    existing = _existing_columns(schema_editor, TABLE_NAME)
    if not existing:
        return
    qn = schema_editor.quote_name
    for column_name in ORPHANED_COLUMNS:
        if column_name in existing:
            schema_editor.execute(f"ALTER TABLE {qn(TABLE_NAME)} DROP COLUMN {qn(column_name)}")


def restore_orphaned_columns(apps: Any, schema_editor: Any) -> None:
    existing = _existing_columns(schema_editor, TABLE_NAME)
    if not existing:
        return
    qn = schema_editor.quote_name
    for column_name, definition in ORPHANED_COLUMNS.items():
        if column_name not in existing:
            schema_editor.execute(f"ALTER TABLE {qn(TABLE_NAME)} ADD COLUMN {qn(column_name)} {definition}")


class Migration(migrations.Migration):
    dependencies = [
        ("contracts", "0028_p3_protect_payment_fk"),
    ]

    operations = [
        migrations.RunPython(drop_orphaned_columns, restore_orphaned_columns),
    ]
