"""Add updated_at field to Reminder model."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reminders", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="reminder",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, verbose_name="更新时间"),
        ),
    ]
