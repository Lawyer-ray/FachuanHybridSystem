"""只读 Admin：快照是审计与救援入口，不允许在后台改内容。"""

from __future__ import annotations

from typing import Any

from django.contrib import admin

from ..models import DocSnapshot


@admin.register(DocSnapshot)
class DocSnapshotAdmin(admin.ModelAdmin[DocSnapshot]):
    list_display = ("owner_kind", "owner_id", "subpath", "seq", "reason", "actor_kind", "created_at")
    list_filter = ("owner_kind", "reason", "actor_kind")
    search_fields = ("subpath",)
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    def get_readonly_fields(self, request: Any, obj: Any = None) -> tuple[str, ...]:
        return tuple(f.name for f in DocSnapshot._meta.fields)

    def has_module_permission(self, request: Any) -> bool:
        """不在主菜单里出现。

        收纳到「其他工具」（automation/admin/tools_hub_admin）里的一张卡片：
        这个页面不是日常操作入口，而是「改坏了来翻版本」时的兜底页，
        占一排菜单只会增加噪声。URL 仍然可达，权限照旧走 ``has_view_permission``。
        """
        return False

    def has_add_permission(self, request: Any) -> bool:
        return False

    def has_change_permission(self, request: Any, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: Any, obj: Any = None) -> bool:
        return False
