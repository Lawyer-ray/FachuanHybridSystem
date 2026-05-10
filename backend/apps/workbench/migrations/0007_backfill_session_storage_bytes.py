"""Backfill storage_bytes for existing sessions."""

from django.db import migrations


def backfill_storage_bytes(apps, schema_editor):
    WorkbenchSession = apps.get_model("workbench", "WorkbenchSession")
    WorkbenchMessage = apps.get_model("workbench", "WorkbenchMessage")

    for session in WorkbenchSession.objects.iterator():
        total = 0
        for msg in WorkbenchMessage.objects.filter(session_id=session.id).iterator():
            total += len((msg.content or "").encode("utf-8"))
            total += len(str(msg.tool_input or {}).encode("utf-8"))
            total += len(str(msg.tool_output or {}).encode("utf-8"))
            total += len(str(msg.metadata or {}).encode("utf-8"))
        if total:
            WorkbenchSession.objects.filter(id=session.id).update(storage_bytes=total)


def reverse(apps, schema_editor):
    WorkbenchSession = apps.get_model("workbench", "WorkbenchSession")
    WorkbenchSession.objects.update(storage_bytes=0)


class Migration(migrations.Migration):
    dependencies = [
        ("workbench", "0006_add_session_storage_bytes"),
    ]

    operations = [
        migrations.RunPython(backfill_storage_bytes, reverse),
    ]
