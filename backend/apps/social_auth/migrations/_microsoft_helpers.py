"""迁移 0007：微软账号登录的默认配置行。

独立模块（迁移文件名以数字开头无法被单测 import），签名沿用迁移
``RunPython(apps, schema_editor)`` 约定——迁移执行时传 historical models 的
registry，单测可直接传 ``django.apps.apps``。数据在此**固化**
（不 import 运行时 PROVIDER_SPECS），保证迁移行为不随代码演进变化。
"""

from __future__ import annotations

from typing import Any


def add_microsoft_provider(apps: Any, schema_editor: Any) -> None:
    """为微软账号登录插入默认配置行。

    client_id/secret 留空 → ``_build_config`` 判定未配置完成，登录页不显示，
    管理员在「社交登录」后台填入 Azure App 注册的 Client ID/Secret 后即出现。
    """
    SocialAuthProvider = apps.get_model("social_auth", "SocialAuthProvider")
    SocialAuthProvider.objects.update_or_create(
        name="microsoft",
        defaults={
            "display_name": "微软",
            "enabled": True,
            # 与 admin 列表口径一致：GitHub(20) < Google(30) < 微软(35) < 微信(40)
            "priority": 35,
        },
    )


def remove_microsoft_provider(apps: Any, schema_editor: Any) -> None:
    SocialAuthProvider = apps.get_model("social_auth", "SocialAuthProvider")
    SocialAuthProvider.objects.filter(name="microsoft").delete()
