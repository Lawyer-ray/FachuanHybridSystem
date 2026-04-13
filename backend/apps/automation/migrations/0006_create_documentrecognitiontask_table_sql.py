from __future__ import annotations

from django.db import migrations, models


def _build_legacy_task_model() -> type[models.Model]:
    class LegacyDocumentRecognitionTask(models.Model):
        file_path = models.CharField(max_length=1024)
        original_filename = models.CharField(max_length=256)
        status = models.CharField(max_length=32, default="pending")
        document_type = models.CharField(max_length=32, null=True, blank=True)
        case_number = models.CharField(max_length=128, null=True, blank=True)
        key_time = models.DateTimeField(null=True, blank=True)
        confidence = models.FloatField(null=True, blank=True)
        extraction_method = models.CharField(max_length=32, null=True, blank=True)
        raw_text = models.TextField(null=True, blank=True)
        renamed_file_path = models.CharField(max_length=1024, null=True, blank=True)
        binding_success = models.BooleanField(null=True)
        case = models.ForeignKey(
            "cases.Case",
            on_delete=models.SET_NULL,
            null=True,
            blank=True,
            db_constraint=False,
            related_name="+",
        )
        case_log = models.ForeignKey(
            "cases.CaseLog",
            on_delete=models.SET_NULL,
            null=True,
            blank=True,
            db_constraint=False,
            related_name="+",
        )
        binding_message = models.CharField(max_length=512, null=True, blank=True)
        binding_error_code = models.CharField(max_length=64, null=True, blank=True)
        error_message = models.TextField(null=True, blank=True)
        notification_sent = models.BooleanField(default=False)
        notification_sent_at = models.DateTimeField(null=True, blank=True)
        notification_error = models.TextField(null=True, blank=True)
        notification_file_sent = models.BooleanField(default=False)
        created_at = models.DateTimeField(auto_now_add=True)
        started_at = models.DateTimeField(null=True, blank=True)
        finished_at = models.DateTimeField(null=True, blank=True)

        class Meta:
            app_label = "automation"
            db_table = "automation_documentrecognitiontask"
            managed = True

    return LegacyDocumentRecognitionTask


def _create_table(apps, schema_editor) -> None:
    model = _build_legacy_task_model()
    table_name = model._meta.db_table
    existing_tables = set(schema_editor.connection.introspection.table_names())
    if table_name in existing_tables:
        return

    schema_editor.create_model(model)
    schema_editor.add_index(
        model,
        models.Index(fields=["status", "created_at"], name="automation__status_b57405_idx"),
    )
    schema_editor.add_index(
        model,
        models.Index(fields=["case"], name="automation__case_id_13ae57_idx"),
    )
    schema_editor.add_index(
        model,
        models.Index(fields=["notification_sent"], name="automation__notific_6b9b00_idx"),
    )


def _drop_table(apps, schema_editor) -> None:
    model = _build_legacy_task_model()
    table_name = model._meta.db_table
    existing_tables = set(schema_editor.connection.introspection.table_names())
    if table_name not in existing_tables:
        return
    schema_editor.delete_model(model)


class Migration(migrations.Migration):
    dependencies = [
        ("automation", "0005_restore_documentrecognitiontask_table"),
    ]

    operations = [
        migrations.RunPython(_create_table, _drop_table),
    ]
