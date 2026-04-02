"""InboxMessage Admin — 统一收件箱。"""

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib import admin
from django.http import FileResponse, HttpRequest
from django.urls import path
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext_lazy as _

from apps.message_hub.models import InboxMessage


@admin.register(InboxMessage)
class InboxMessageAdmin(admin.ModelAdmin[InboxMessage]):
    class Media:
        css = {"all": ("admin/css/inbox_message_admin.css",)}

    list_display = ["subject_display", "source_badge", "recipient_display", "received_at", "attachments_display"]
    list_display_links = ["subject_display"]
    list_filter: ClassVar = ["source", "has_attachments", "received_at"]
    search_fields: ClassVar = ("subject", "sender", "body_text")
    readonly_fields: ClassVar = ["source", "message_id", "sender", "received_at", "has_attachments", "attachments_meta", "created_at", "body_preview", "attachments_actions"]
    date_hierarchy = "received_at"
    list_per_page = 50
    ordering: ClassVar = ["-received_at"]
    list_select_related: ClassVar = ["source", "source__credential"]

    fieldsets: ClassVar = (
        (_("基本信息"), {"fields": ("source", "message_id", "sender", "received_at", "created_at")}),
        (_("正文"), {"fields": ("body_preview",)}),
        (_("附件"), {"fields": ("has_attachments", "attachments_actions")}),
    )

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        custom = [
            path("<int:pk>/attachment/<int:part_index>/download/", self.admin_site.admin_view(self._attachment_view), {"inline": False}, name="message_hub_attachment_download"),
            path("<int:pk>/attachment/<int:part_index>/preview/", self.admin_site.admin_view(self._attachment_view), {"inline": True}, name="message_hub_attachment_preview"),
        ]
        return custom + urls

    def _attachment_view(self, request: HttpRequest, pk: int, part_index: int, inline: bool = False) -> FileResponse:
        from apps.message_hub.services import get_fetcher

        msg = InboxMessage.objects.select_related("source__credential").get(pk=pk)
        fetcher = get_fetcher(msg.source.source_type)
        content, filename, content_type = fetcher.download_attachment(msg.source, msg.message_id, part_index)
        response = FileResponse(
            iter([content]),
            content_type=content_type,
            as_attachment=not inline,
            filename=filename,
        )
        disposition = "inline" if inline else "attachment"
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response

    @admin.display(description=_("来源"))
    def source_badge(self, obj: InboxMessage) -> SafeString:
        colors = {"imap": "#0d6efd", "court_inbox": "#6f42c1"}
        st = obj.source.source_type
        color = colors.get(st, "#6c757d")
        return mark_safe(
            f'<span style="display:inline-flex;align-items:center;gap:4px;background:{color};color:#fff;'
            f'padding:3px 10px;border-radius:12px;font-size:11px;white-space:nowrap">'
            f'{obj.source.display_name}</span>'
        )

    @admin.display(description=_("收件人"))
    def recipient_display(self, obj: InboxMessage) -> str:
        account: str = obj.source.credential.account
        return account

    @admin.display(description=_("主题"))
    def subject_display(self, obj: InboxMessage) -> SafeString:
        subject = obj.subject or _("(无主题)")
        return format_html('<span style="display:inline-block;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{}</span>', subject)

    @admin.display(description=_("附件"))
    def attachments_display(self, obj: InboxMessage) -> SafeString:
        if not obj.has_attachments:
            return mark_safe('<span style="color:#ccc">—</span>')
        count = len(obj.attachments_meta)
        return format_html('<span style="color:#007bff">{} 个附件</span>', count)

    @admin.display(description=_("正文"))
    def body_preview(self, obj: InboxMessage) -> SafeString:
        content = obj.body_html or obj.body_text or ""
        if not content:
            return mark_safe('<span style="color:#999">无正文</span>')
        if obj.body_html:
            # 用 srcdoc iframe 隔离，阻止加载外部资源
            import html
            escaped = html.escape(obj.body_html)
            return mark_safe(
                f'<iframe srcdoc="{escaped}" sandbox="" '
                f'style="width:100%;height:400px;border:1px solid #ddd;background:#fff" '
                f'loading="lazy"></iframe>'
            )
        return mark_safe(
            '<div style="border:1px solid #ddd;padding:12px;max-height:400px;overflow:auto;background:#fff;white-space:pre-wrap">'
            + content
            + "</div>"
        )

    @admin.display(description=_("附件操作"))
    def attachments_actions(self, obj: InboxMessage) -> SafeString:
        if not obj.attachments_meta:
            return mark_safe('<span style="color:#999">无附件</span>')
        from django.urls import reverse
        parts = []
        for att in obj.attachments_meta:
            idx = att["part_index"]
            name = att["filename"]
            size_kb = att["size"] // 1024
            ct = att.get("content_type", "")
            dl_url = reverse("admin:message_hub_attachment_download", args=[obj.pk, idx])
            pv_url = reverse("admin:message_hub_attachment_preview", args=[obj.pk, idx])
            can_preview = "pdf" in ct or "image" in ct
            preview_html = (
                f'<a href="{pv_url}" target="_blank" style="background:#28a745;color:#fff;padding:3px 8px;border-radius:4px;text-decoration:none;font-size:11px;margin-left:4px">预览</a>'
                if can_preview else ""
            )
            parts.append(
                f'<div style="margin:4px 0">{name} ({size_kb}KB) '
                f'<a href="{dl_url}" style="background:#007bff;color:#fff;padding:3px 8px;border-radius:4px;text-decoration:none;font-size:11px">下载</a>'
                f'{preview_html}</div>'
            )
        return mark_safe("".join(parts))
