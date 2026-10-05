"""社交账号后台。

存在的意义：登录只放行已绑定的社交身份，所以这里是排查「律师说扫码进不去」
的第一现场——能反查某个飞书/微信身份对应哪位律师，也能替律师解绑换号。

``SocialAuthProvider`` 是各登录平台的接入配置（凭证/回调/开关），从
``SystemConfig`` 的 19 行 KV 独立成表后的管理入口。
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin

from .models import PasskeyCredential, SocialAccount, SocialAuthProvider
from .providers import ProviderRegistry


class SocialAuthProviderForm(forms.ModelForm):
    """平台配置表单：name 必须与代码注册的 Provider 一致，否则登录链路永远找不到它。

    页面不放说明文字——模型 help_text 留作代码文档，表单层统一清空。
    """

    class Meta:
        model = SocialAuthProvider
        fields = "__all__"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.help_text = ""

    def clean_name(self) -> str:
        name = str(self.cleaned_data.get("name") or "").strip()
        if name and not ProviderRegistry.has(name):
            raise forms.ValidationError(f"未注册的平台标识：{name}。可用的有：{'、'.join(ProviderRegistry.names())}")
        return name


@admin.register(SocialAuthProvider)
class SocialAuthProviderAdmin(admin.ModelAdmin):  # pragma: no cover
    form = SocialAuthProviderForm

    list_display = ("name", "display_name", "client_id_brief", "has_secret", "enabled", "priority", "updated_at")
    list_filter = ("enabled",)
    # 安全审计 E-17 同款约束：client_secret 不进 search_fields——搜索词会进查询串/访问日志，泄露密钥片段
    search_fields = ("name", "display_name", "redirect_uri")
    ordering = ("priority", "name")
    # 不用 list_editable：列表页只做排查浏览，启停/排序进详情页改，避免误触批量保存
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("基本信息", {"fields": ("name", "display_name", "enabled", "priority")}),
        ("凭证", {"fields": ("client_id", "client_secret")}),
        ("回调与授权范围", {"fields": ("redirect_uri", "scope")}),
        ("时间", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def client_id_brief(self, obj: SocialAuthProvider) -> str:
        """client_id 截断展示，避免撑爆列表页。"""
        value = str(obj.client_id or "")
        if not value:
            return "—（未配置）"
        return value if len(value) <= 24 else f"{value[:21]}..."

    client_id_brief.short_description = "Client ID"  # type: ignore[attr-defined]

    def has_secret(self, obj: SocialAuthProvider) -> bool:
        return bool(obj.client_secret)

    has_secret.short_description = "已配密钥"  # type: ignore[attr-defined]
    has_secret.boolean = True  # type: ignore[attr-defined]


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


@admin.register(PasskeyCredential)
class PasskeyCredentialAdmin(admin.ModelAdmin):  # pragma: no cover
    """通行密钥排查入口：看谁注册了哪把密钥、何时用过；删除 = 吊销该设备。"""

    list_display = ("id", "name", "rp_id", "user", "backed_up", "last_used_at", "created_at")
    list_filter = ("rp_id", "backed_up")
    search_fields = ("name", "user__username", "user__real_name", "user__phone")
    list_select_related = ("user",)
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    # 公钥不是秘密（本来就要给服务器验签用），但也无展示价值，全部只读
    readonly_fields = (
        "user",
        "name",
        "credential_id",
        "public_key",
        "sign_count",
        "rp_id",
        "backed_up",
        "created_at",
        "last_used_at",
    )

    def has_add_permission(self, request: Any) -> bool:
        # 凭据只能由本人设备经 WebAuthn ceremony 产生，后台手工新增必然是坏数据
        return False
