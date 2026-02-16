from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0002_initial"),
    ]

    operations = [
        migrations.DeleteModel(
            name="ContractReminder",
        ),
    ]
