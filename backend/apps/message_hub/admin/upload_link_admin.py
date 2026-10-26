"""客户上传链接 Admin：只读 + 作废（token 哈希存储，明文仅业务端创建/换发响应可见）。"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from apps.message_hub.models import ClientUploadLink
from apps.message_hub.services.client_upload_service import link_state


@admin.register(ClientUploadLink)
class ClientUploadLinkAdmin(admin.ModelAdmin):
    """客户上传链接管理（token 哈希只读展示，不暴露明文）。"""

    list_display = (
        "id",
        "title",
        "client_name",
        "created_by",
        "contract",
        "status",
        "state",
        "pack_count",
        "used_bytes",
        "expires_at",
    )
    list_filter = ("status",)
    search_fields = ("title", "client_name", "created_by__username")
    readonly_fields = (
        "title",
        "note",
        "client_name",
        "token_hash",
        "created_by",
        "contract",
        "expires_at",
        "quota_total_bytes",
        "quota_max_packs",
        "used_bytes",
        "pack_count",
        "last_uploaded_at",
        "created_at",
        "updated_at",
    )
    actions = ("action_revoke",)

    @admin.display(description="状态")
    def state(self, obj: ClientUploadLink) -> str:
        state = link_state(obj)
        return {"open": "可收", "expired": "已过期", "revoked": "已作废", "full": "已收满"}.get(state, state)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False  # 链接必须由律师在业务端生成（token 明文只在创建响应出现一次）

    @admin.action(description="作废选中链接")
    def action_revoke(self, request: HttpRequest, queryset: Any) -> None:
        for link in queryset:
            link.status = "revoked"
            link.save(update_fields=["status", "updated_at"])
        self.message_user(request, f"已作废 {queryset.count()} 条链接")
