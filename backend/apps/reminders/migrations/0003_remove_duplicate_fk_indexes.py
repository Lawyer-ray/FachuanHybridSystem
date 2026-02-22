"""Remove duplicate indexes on contract and case_log (ForeignKey auto-creates them)."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("reminders", "0002_reminder_updated_at"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="reminder",
            name="reminders_r_contrac_f13768_idx",
        ),
        migrations.RemoveIndex(
            model_name="reminder",
            name="reminders_r_case_lo_5b9d79_idx",
        ),
    ]
