from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from apps.cases.admin.base import BaseTabularInline
from apps.cases.admin.mixins import CaseAdminServiceMixin
from apps.cases.models import CaseChat


@admin.register(CaseChat)
class CaseChatAdmin(CaseAdminServiceMixin, admin.ModelAdmin[CaseChat]):
    """案件群聊管理"""

    list_display = ("name", "chat_id_display", "platform_display", "case_link", "status_display", "created_at")

    list_filter = ("platform", "is_active", "created_at")

    search_fields = ("name", "chat_id", "case__name")

    readonly_fields = ("chat_id", "created_at", "updated_at")

    fields = ("case", "platform", "chat_id", "name", "is_active", "created_at", "updated_at")

    ordering = ("-created_at",)

    actions = ["unbind_selected_chats"]

    change_form_template = "admin/cases/casechat/change_form.html"

    def chat_id_display(self, obj: CaseChat) -> str:
        """显示群聊ID（截断显示）"""
        chat_id: str = obj.chat_id
        if chat_id:
            if len(chat_id) > 20:
                return f"{chat_id[:20]}..."
            return chat_id
        return "-"

    chat_id_display.short_description = _("群聊ID")  # type: ignore[attr-defined]

    def platform_display(self, obj: CaseChat) -> str:
        """显示平台（带图标）"""
        platform_icons = {"feishu": "🚀", "dingtalk": "📱", "wechat_work": "💬", "telegram": "✈️", "slack": "💼"}
        icon = platform_icons.get(obj.platform, "📢")
        display = obj.get_platform_display()
        return f"{icon} {display}"

    platform_display.short_description = _("平台")  # type: ignore[attr-defined]

    def case_link(self, obj: CaseChat) -> SafeString:
        """案件链接"""
        case_id = getattr(obj, "case_id", None)
        if case_id:
            url = reverse("admin:cases_case_change", args=[case_id])
            case_name = getattr(obj.case, "name", str(case_id))
            return format_html('<a href="{}" target="_blank">{}</a>', url, case_name)
        return format_html('<span>{}</span>', "-")

    case_link.short_description = _("关联案件")  # type: ignore[attr-defined]

    def status_display(self, obj: CaseChat) -> SafeString:
        """状态显示"""
        if obj.is_active:
            return format_html('<span style="color: green;">●</span> {}', "有效")
        else:
            return format_html('<span style="color: red;">●</span> {}', "已解绑")

    status_display.short_description = _("状态")  # type: ignore[attr-defined]

    def unbind_selected_chats(self, request: HttpRequest, queryset: QuerySet[CaseChat, CaseChat]) -> None:
        """批量解除绑定群聊"""
        service = self._get_case_chat_service()
        success_count = 0

        for chat in queryset.filter(is_active=True):
            try:
                if service.unbind_chat(chat.id):
                    success_count += 1
            except Exception as e:
                msg = _("解除绑定群聊 %(chat)s 失败: %(error)s") % {
                    "chat": chat.name,
                    "error": str(e),
                }
                messages.error(request, msg)

        if success_count > 0:
            messages.success(request, _("成功解除绑定 %d 个群聊") % success_count)

    unbind_selected_chats.short_description = _("解除绑定选中的群聊")  # type: ignore[attr-defined]

    def has_add_permission(self, request: HttpRequest) -> bool:
        """禁止直接添加群聊记录"""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: CaseChat | None = None) -> bool:
        """禁止删除群聊记录"""
        return False

    def response_change(self, request: HttpRequest, obj: CaseChat) -> HttpResponse:
        """处理自定义操作"""
        if "_unbind_chat" in request.POST:
            service = self._get_case_chat_service()
            try:
                if service.unbind_chat(obj.id):
                    messages.success(request, _("成功解除绑定群聊: %s") % obj.name)
                else:
                    messages.error(request, _("解除绑定群聊失败: %s") % obj.name)
            except Exception as e:
                messages.error(request, _("解除绑定群聊时发生错误: %s") % str(e))

            return HttpResponseRedirect(reverse("admin:cases_casechat_changelist"))

        return super().response_change(request, obj)


class CaseChatInline(BaseTabularInline):
    """案件群聊内联管理"""

    model = CaseChat
    extra = 0

    fields = ("platform_display", "name", "chat_id_display", "status_display", "created_at")

    readonly_fields = ("platform_display", "name", "chat_id_display", "status_display", "created_at")

    ordering = ("platform", "-created_at")

    def platform_display(self, obj: CaseChat) -> str:
        """显示平台（带图标）"""
        if not obj.pk:
            return ""

        platform_icons = {"feishu": "🚀", "dingtalk": "📱", "wechat_work": "💬", "telegram": "✈️", "slack": "💼"}
        icon = platform_icons.get(obj.platform, "📢")
        display = obj.get_platform_display()
        return f"{icon} {display}"

    platform_display.short_description = _("平台")  # type: ignore[attr-defined]

    def chat_id_display(self, obj: CaseChat) -> str:
        """显示群聊ID（截断显示）"""
        if not obj.pk or not obj.chat_id:
            return ""

        chat_id: str = obj.chat_id
        if len(chat_id) > 15:
            return f"{chat_id[:15]}..."
        return chat_id

    chat_id_display.short_description = _("群聊ID")  # type: ignore[attr-defined]

    def status_display(self, obj: CaseChat) -> SafeString:
        """状态显示"""
        if not obj.pk:
            return format_html('<span>{}</span>', "")

        if obj.is_active:
            return format_html('<span style="color: green;">●</span> {}', "有效")
        else:
            return format_html('<span style="color: red;">●</span> {}', "已解绑")

    status_display.short_description = _("状态")  # type: ignore[attr-defined]

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """禁止直接添加群聊记录"""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """禁止删除群聊记录"""
        return False
