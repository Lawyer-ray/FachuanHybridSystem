from typing import Any

from django.db import migrations

from apps.core.model_fields.encrypted import EncryptedTextField


class Migration(migrations.Migration):
    dependencies: list[Any] = [
        ("automation", "0002_initial"),
    ]

    operations: list[Any] = [
        migrations.AlterField(
            model_name="courttoken",
            name="token",
            field=EncryptedTextField(help_text="JWT Token 或其他认证令牌", verbose_name="Token"),
        ),
    ]
