from __future__ import annotations

from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps


def _build_legacy_task_model() -> type[models.Model]:
    """与 0006 一致的精简历史模型。

    迁移内禁止 import 当前活模型（apps.document_recognition.models）：
    活模型随代码演进会包含后续迁移才添加的字段（degraded / llm_* /
    party_names / date_confirmation_status / source_court_sms 等），用它建表
    会让全新库提前出现这些列，随后 document_recognition.0003/0004 的
    AddField 因列已存在而失败（CI 全新库 migrate 必炸，2026-09-29 复现修复）。
    """

    # 类名须与 0006 的 LegacyDocumentRecognitionTask 不同：迁移内定义的模型
    # 会注册进全局 app registry，同名同类 app 在一次 migrate 里二次注册即冲突。
    class RestoredLegacyDocumentRecognitionTask(models.Model):
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

    return RestoredLegacyDocumentRecognitionTask


def _create_legacy_document_recognition_table(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """恢复 document_recognition 仍在使用的历史表。"""
    model = _build_legacy_task_model()
    table_name = model._meta.db_table
    existing_tables = set(schema_editor.connection.introspection.table_names())
    if table_name in existing_tables:
        return

    schema_editor.create_model(model)

    qn = schema_editor.quote_name
    schema_editor.execute(
        f"CREATE INDEX {qn('automation__status_b57405_idx')} ON {qn(table_name)} ({qn('status')}, {qn('created_at')})"
    )
    schema_editor.execute(f"CREATE INDEX {qn('automation__case_id_13ae57_idx')} ON {qn(table_name)} ({qn('case_id')})")
    schema_editor.execute(
        f"CREATE INDEX {qn('automation__notific_6b9b00_idx')} ON {qn(table_name)} ({qn('notification_sent')})"
    )


def _drop_legacy_document_recognition_table(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    model = _build_legacy_task_model()
    table_name = model._meta.db_table
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

    schema_editor.delete_model(model)


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
