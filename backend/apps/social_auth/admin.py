"""社交账号后台。

存在的意义：登录只放行已绑定的社交身份，所以这里是排查「律师说扫码进不去」
的第一现场——能反查某个飞书/微信身份对应哪位律师，也能替律师解绑换号。
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin

from .models import SocialAccount


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):  # pragma: no cover
    list_display = ("id", "provider", "display_name", "user", "provider_uid", "created_at")
    list_filter = ("provider",)
    search_fields = ("display_name", "provider_uid", "user__username", "user__real_name", "user__phone")
    list_select_related = ("user",)
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    readonly_fields = (
        "user",
        "provider",
        "provider_uid",
        "display_name",
        "avatar_url",
        "raw_profile",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request: Any) -> bool:
        # 绑定关系只能由本人扫码产生；后台手工新增会造出指向错误律师的记录
        return False
