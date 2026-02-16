from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0003_initial"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="caselog",
            name="cases_casel_reminde_a2637a_idx",
        ),
        migrations.RemoveField(
            model_name="caselog",
            name="reminder_time",
        ),
        migrations.RemoveField(
            model_name="caselog",
            name="reminder_type",
        ),
    ]
