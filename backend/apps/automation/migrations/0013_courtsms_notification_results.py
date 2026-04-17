"""Add notification_results field to CourtSMS and migrate old feishu data"""

from django.db import migrations, models


def migrate_feishu_data_to_notification_results(apps, schema_editor):
    """将旧的 feishu_sent_at/feishu_error 数据迁移到 notification_results"""
    CourtSMS = apps.get_model("automation", "CourtSMS")
    for sms in CourtSMS.objects.filter(feishu_sent_at__isnull=False).exclude(
        feishu_sent_at=None
    ).iterator():
        sms.notification_results = {
            "feishu": {
                "success": True,
                "chat_id": None,
                "sent_at": sms.feishu_sent_at.isoformat() if sms.feishu_sent_at else None,
                "file_count": 0,
                "sent_file_count": 0,
                "error": sms.feishu_error if sms.feishu_error else None,
            }
        }
        sms.save(update_fields=["notification_results"])

    # 也迁移 feishu_error 但没有 feishu_sent_at 的记录
    for sms in (
        CourtSMS.objects.filter(feishu_sent_at__isnull=True, feishu_error__isnull=False)
        .exclude(feishu_error=None)
        .exclude(feishu_error="")
        .iterator()
    ):
        sms.notification_results = {
            "feishu": {
                "success": False,
                "chat_id": None,
                "sent_at": None,
                "file_count": 0,
                "sent_file_count": 0,
                "error": sms.feishu_error,
            }
        }
        sms.save(update_fields=["notification_results"])


def reverse_migration(apps, schema_editor):
    """反向迁移：清空 notification_results"""
    CourtSMS = apps.get_model("automation", "CourtSMS")
    CourtSMS.objects.filter(notification_results__isnull=False).update(
        notification_results=None
    )


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0012_courtsms_dedup_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="courtsms",
            name="notification_results",
            field=models.JSONField(blank=True, default=None, null=True, verbose_name="多平台通知结果"),
        ),
        migrations.RunPython(
            migrate_feishu_data_to_notification_results,
            reverse_migration,
        ),
    ]
