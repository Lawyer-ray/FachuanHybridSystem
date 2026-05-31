"""Remove SmartFillProxy model (merged into DocumentTemplate changeform)."""

from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0010_add_smart_fill_proxy"),
    ]

    operations = [
        migrations.DeleteModel(
            name="SmartFillProxy",
        ),
    ]
