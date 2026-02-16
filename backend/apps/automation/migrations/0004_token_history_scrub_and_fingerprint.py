from typing import Any

from django.db import migrations, models


def forwards(apps, schema_editor) -> None:
    TokenAcquisitionHistory = apps.get_model("automation", "TokenAcquisitionHistory")
    from apps.core.security.scrub import fingerprint_sha256, mask_secret, scrub_for_storage, scrub_text

    for record in TokenAcquisitionHistory.objects.exclude(token_preview__isnull=True).exclude(token_preview="").iterator():
        preview = record.token_preview
        if not preview:
            continue
        if not record.token_fingerprint:
            record.token_fingerprint = fingerprint_sha256(preview)
        if not record.token_redacted:
            record.token_redacted = mask_secret(preview)
        record.token_preview = None
        record.save(update_fields=["token_fingerprint", "token_redacted", "token_preview"])

    for record in TokenAcquisitionHistory.objects.exclude(error_details__isnull=True).iterator():
        details = record.error_details
        if details is None:
            continue
        scrubbed = scrub_for_storage(details)
        if scrubbed != details:
            record.error_details = scrubbed
            update_fields=[],
            if record.error_message:
                record.error_message = scrub_text(str(record.error_message))
                update_fields.append("error_message")
            record.save(update_fields=update_fields)


def backwards(apps, schema_editor) -> None:
    return


class Migration(migrations.Migration):
    dependencies: list[Any] = [
        ("automation", "0003_encrypt_courttoken"),
    ]

    operations: list[Any] = [
        migrations.AddField(
            model_name="tokenacquisitionhistory",
            name="token_fingerprint",
            field=models.CharField(
                blank=True,
                help_text="Token的SHA256指纹(用于排查重复/归因,不可反推Token)",
                max_length=64,
                null=True,
                verbose_name="Token指纹",
            ),
        ),
        migrations.AddField(
            model_name="tokenacquisitionhistory",
            name="token_redacted",
            field=models.CharField(
                blank=True,
                help_text="脱敏后的Token摘要(仅用于人工排查)",
                max_length=32,
                null=True,
                verbose_name="Token脱敏摘要",
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
