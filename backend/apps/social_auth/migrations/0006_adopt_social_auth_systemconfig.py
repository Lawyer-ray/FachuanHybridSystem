"""收养 SystemConfig 中的社交登录 KV 配置到 SocialAuthProvider 表。

逻辑在 ``_adopt_helpers``（单测锁定行为）。

``migrate`` 后旧行即删；如需回滚数据，应先从 SocialAuthProvider 表导出再降级
（reverse 为 no-op——新表是权威数据源，自动写回旧格式反而会造成双源）。
"""

from django.db import migrations

from ._adopt_helpers import adopt_social_auth_configs


def rollback_noop(apps, schema_editor):  # type: ignore[no-untyped-def]
    """数据收养不可自动逆：回滚前请先导出 SocialAuthProvider 数据。"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0032_alter_systemconfig_category"),
        ("social_auth", "0005_socialauthprovider"),
    ]

    operations = [
        migrations.RunPython(adopt_social_auth_configs, rollback_noop),
    ]
