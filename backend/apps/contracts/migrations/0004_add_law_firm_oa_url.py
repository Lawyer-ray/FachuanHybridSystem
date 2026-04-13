"""Add law_firm_oa_url to contract."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contracts", "0003_contractfolderscansession"),
    ]

    operations = [
        migrations.AddField(
            model_name="contract",
            name="law_firm_oa_url",
            field=models.URLField(
                blank=True,
                help_text="跳转至律所OA系统中该合同的页面",
                max_length=500,
                null=True,
                verbose_name="律所OA链接",
            ),
        ),
    ]
