from __future__ import annotations

from django.db import migrations


def _create_legacy_document_recognition_table(apps, schema_editor) -> None:
    """恢复 document_recognition 仍在使用的历史表。"""
    from apps.document_recognition.models import DocumentRecognitionTask

    table_name = DocumentRecognitionTask._meta.db_table
    existing_tables = set(schema_editor.connection.introspection.table_names())
    if table_name in existing_tables:
        return

    schema_editor.create_model(DocumentRecognitionTask)

    qn = schema_editor.quote_name
    schema_editor.execute(
        f"CREATE INDEX {qn('automation__status_b57405_idx')} "
        f"ON {qn(table_name)} ({qn('status')}, {qn('created_at')})"
    )
    schema_editor.execute(
        f"CREATE INDEX {qn('automation__case_id_13ae57_idx')} "
        f"ON {qn(table_name)} ({qn('case_id')})"
    )
    schema_editor.execute(
        f"CREATE INDEX {qn('automation__notific_6b9b00_idx')} "
        f"ON {qn(table_name)} ({qn('notification_sent')})"
    )


def _drop_legacy_document_recognition_table(apps, schema_editor) -> None:
    from apps.document_recognition.models import DocumentRecognitionTask

    table_name = DocumentRecognitionTask._meta.db_table
    existing_tables = set(schema_editor.connection.introspection.table_names())
    if table_name not in existing_tables:
        return

    qn = schema_editor.quote_name
    for index_name in (
        "automation__status_b57405_idx",
        "automation__case_id_13ae57_idx",
        "automation__notific_6b9b00_idx",
    ):
        try:
            schema_editor.execute(f"DROP INDEX {qn(index_name)}")
        except Exception:
            pass

    schema_editor.delete_model(DocumentRecognitionTask)


class Migration(migrations.Migration):
    dependencies = [
        ("automation", "0004_remove_documentrecognitiontask_automation__status_b57405_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(
            code=_create_legacy_document_recognition_table,
            reverse_code=_drop_legacy_document_recognition_table,
        ),
    ]

