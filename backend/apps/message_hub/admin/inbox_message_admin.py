"""InboxMessage Admin — 统一收件箱。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

from django.contrib import admin
from django.http import FileResponse, HttpRequest, HttpResponseNotAllowed, JsonResponse
from django.urls import path
from django.utils.html import escape, escapejs, format_html
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext_lazy as _

from apps.message_hub.models import InboxMessage

logger = logging.getLogger("apps.message_hub")


@admin.register(InboxMessage)
class InboxMessageAdmin(admin.ModelAdmin[InboxMessage]):
    class Media:
        css = {"all": ("admin/css/inbox_message_admin.css",)}

    list_display = ["subject_display", "source_badge", "recipient_display", "received_at", "attachments_display"]
    list_display_links = ["subject_display"]
    list_filter: ClassVar = ["source", "has_attachments", "received_at"]
    search_fields: ClassVar = ("subject", "sender", "body_text")
    readonly_fields: ClassVar = [
        "source",
        "message_id",
        "sender",
        "received_at",
        "has_attachments",
        "created_at",
        "body_preview",
        "attachments_actions",
    ]
    date_hierarchy = "received_at"
    list_per_page = 50
    ordering: ClassVar = ["-received_at"]
    list_select_related: ClassVar = ["source", "source__credential"]

    fieldsets: ClassVar = (
        (_("基本信息"), {"fields": ("source", "message_id", "sender", "received_at", "created_at")}),
        (_("正文"), {"fields": ("body_preview",)}),
        (
            _("附件"),
            {
                "fields": ("attachments_actions",),
                "description": _("可直接调整附件下载名；留空则使用原始文件名。"),
            },
        ),
    )

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/attachment/<int:part_index>/download/",
                self.admin_site.admin_view(self._attachment_view),
                {"inline": False},
                name="message_hub_attachment_download",
            ),
            path(
                "<int:pk>/attachment/<int:part_index>/preview/",
                self.admin_site.admin_view(self._attachment_view),
                {"inline": True},
                name="message_hub_attachment_preview",
            ),
            path(
                "<int:pk>/attachment/<int:part_index>/rename/",
                self.admin_site.admin_view(self._rename_attachment),
                name="message_hub_attachment_rename",
            ),
        ]
        return custom + urls

    @staticmethod
    def _resolve_download_filename(msg: InboxMessage, part_index: int, fallback: str) -> str:
        for att in msg.attachments_meta or []:
            if int(att.get("part_index", -1)) != part_index:
                continue
            custom_name = str(att.get("custom_filename", "")).strip()
            original_name = str(att.get("original_filename") or att.get("filename") or "").strip()
            if custom_name:
                return custom_name
            if original_name:
                return original_name
        return fallback

    @staticmethod
    def _apply_original_extension(custom_filename: str, original_filename: str, content_type: str = "") -> str:
        custom_clean = custom_filename.strip()
        if not custom_clean:
            return ""
        if Path(custom_clean).suffix:
            return custom_clean

        suffix = "".join(Path(original_filename).suffixes)
        if not suffix and content_type:
            content_type_lower = content_type.lower()
            if "pdf" in content_type_lower:
                suffix = ".pdf"
            elif "png" in content_type_lower:
                suffix = ".png"
            elif "jpeg" in content_type_lower or "jpg" in content_type_lower:
                suffix = ".jpg"
            elif "gif" in content_type_lower:
                suffix = ".gif"
            elif "webp" in content_type_lower:
                suffix = ".webp"

        return f"{custom_clean}{suffix}" if suffix else custom_clean

    @staticmethod
    def _normalize_attachments_meta_for_save(
        current_meta: list[dict[str, Any]],
        original_meta: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        original_by_part: dict[int, dict[str, Any]] = {}
        for item in original_meta:
            part_index = int(item.get("part_index", -1))
            original_by_part[part_index] = item

        normalized: list[dict[str, Any]] = []
        for item in current_meta:
            part_index = int(item.get("part_index", -1))
            old_item = original_by_part.get(part_index)

            old_original_name = ""
            if old_item is not None:
                old_original_name = str(old_item.get("original_filename") or old_item.get("filename") or "").strip()

            current_filename = str(item.get("filename", "")).strip()
            current_custom_name = str(item.get("custom_filename", "")).strip()

            original_name = old_original_name or str(item.get("original_filename") or current_filename).strip()

            current_content_type = str(item.get("content_type", ""))
            current_custom_name = InboxMessageAdmin._apply_original_extension(
                current_custom_name, original_name, current_content_type
            )
            if not original_name:
                original_name = current_filename or f"attachment_{part_index}"

            # 兼容用户直接改 filename 的场景：自动转为 custom_filename
            if (
                old_original_name
                and current_filename
                and current_filename != old_original_name
                and not current_custom_name
            ):
                current_custom_name = current_filename

            normalized_item = dict(item)
            normalized_item["filename"] = original_name
            normalized_item["original_filename"] = original_name
            if current_custom_name and current_custom_name != original_name:
                normalized_item["custom_filename"] = current_custom_name
            else:
                normalized_item.pop("custom_filename", None)

            normalized.append(normalized_item)

        return normalized

    def save_model(self, request: HttpRequest, obj: InboxMessage, form: Any, change: bool) -> None:
        if isinstance(obj.attachments_meta, list):
            current_meta = [item for item in obj.attachments_meta if isinstance(item, dict)]
        else:
            current_meta = []

        original_meta: list[dict[str, Any]] = []
        if change and obj.pk:
            old_obj = InboxMessage.objects.filter(pk=obj.pk).only("attachments_meta").first()
            if old_obj and isinstance(old_obj.attachments_meta, list):
                original_meta = [item for item in old_obj.attachments_meta if isinstance(item, dict)]

        obj.attachments_meta = self._normalize_attachments_meta_for_save(current_meta, original_meta)
        super().save_model(request, obj, form, change)

    def _rename_attachment(
        self, request: HttpRequest, pk: int, part_index: int
    ) -> JsonResponse | HttpResponseNotAllowed:
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])

        custom_filename_input = str(request.POST.get("custom_filename", "")).strip()

        msg = InboxMessage.objects.filter(pk=pk).first()
        if msg is None:
            return JsonResponse({"ok": False, "message": _("消息不存在")}, status=404)

        meta_list = msg.attachments_meta if isinstance(msg.attachments_meta, list) else []
        for att in meta_list:
            if int(att.get("part_index", -1)) != part_index:
                continue
            original_name = str(att.get("original_filename") or att.get("filename") or "").strip()
            if not original_name:
                original_name = f"attachment_{part_index}"

            content_type = str(att.get("content_type", ""))
            custom_filename = self._apply_original_extension(custom_filename_input, original_name, content_type)
            if len(custom_filename) > 255:
                return JsonResponse({"ok": False, "message": _("新文件名过长（最多255字符）")}, status=400)

            att["filename"] = original_name
            att["original_filename"] = original_name
            if custom_filename and custom_filename != original_name:
                att["custom_filename"] = custom_filename
            else:
                att.pop("custom_filename", None)
            msg.attachments_meta = meta_list
            msg.save(update_fields=["attachments_meta"])
            logger.info(
                "收件箱附件重命名: message_pk=%s part_index=%s custom_filename=%s", pk, part_index, custom_filename
            )
            return JsonResponse(
                {
                    "ok": True,
                    "message": _("保存成功"),
                    "original_filename": original_name,
                    "custom_filename": custom_filename,
                    "effective_filename": custom_filename or original_name,
                }
            )

        return JsonResponse({"ok": False, "message": _("附件不存在")}, status=404)

    def _attachment_view(self, request: HttpRequest, pk: int, part_index: int, inline: bool = False) -> FileResponse:
        from apps.message_hub.services import get_fetcher

        msg = InboxMessage.objects.select_related("source__credential").get(pk=pk)
        fetcher = get_fetcher(msg.source.source_type)
        content, filename, content_type = fetcher.download_attachment(msg.source, msg.message_id, part_index)
        download_filename = self._resolve_download_filename(msg, part_index, filename)
        response = FileResponse(
            iter([content]),
            content_type=content_type,
            as_attachment=not inline,
            filename=download_filename,
        )
        if not inline:
            response["Content-Type"] = "application/octet-stream"
            response["X-Content-Type-Options"] = "nosniff"
        return response

    @admin.display(description=_("来源"))
    def source_badge(self, obj: InboxMessage) -> SafeString:
        colors = {"imap": "#0d6efd", "court_inbox": "#6f42c1"}
        st = obj.source.source_type
        color = colors.get(st, "#6c757d")
        return mark_safe(
            f'<span style="display:inline-flex;align-items:center;gap:4px;background:{color};color:#fff;'
            f'padding:3px 10px;border-radius:12px;font-size:11px;white-space:nowrap">'
            f"{obj.source.display_name}</span>"
        )

    @admin.display(description=_("收件人"))
    def recipient_display(self, obj: InboxMessage) -> str:
        account: str = obj.source.credential.account
        return account

    @admin.display(description=_("主题"))
    def subject_display(self, obj: InboxMessage) -> SafeString:
        subject = obj.subject or _("(无主题)")
        return format_html(
            '<span style="display:inline-block;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{}</span>',
            subject,
        )

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

        title_effective = _("当前下载名")
        placeholder_custom = _("输入下载文件名，留空则使用原始文件名")
        btn_save = _("保存")
        btn_reset = _("恢复原名")
        btn_download = _("下载")
        btn_preview = _("预览")
        save_ok = _("保存成功")
        save_failed = _("保存失败")

        parts: list[str] = ['<div id="mh-attachments-rename-panel" class="mh-attachments-panel">']

        for att in obj.attachments_meta:
            idx = int(att.get("part_index", -1))
            if idx < 0:
                continue

            original_name = str(att.get("original_filename") or att.get("filename") or "").strip()
            custom_name = str(att.get("custom_filename", "")).strip()
            ct = str(att.get("content_type", ""))
            normalized_custom_name = self._apply_original_extension(custom_name, original_name, ct)
            effective_name = normalized_custom_name or original_name
            size_kb = max(1, (int(att.get("size", 0)) + 1023) // 1024) if int(att.get("size", 0)) > 0 else 0
            size_text = f"{size_kb} KB" if size_kb else _("未知大小")

            rename_url = reverse("admin:message_hub_attachment_rename", args=[obj.pk, idx])
            dl_url = reverse("admin:message_hub_attachment_download", args=[obj.pk, idx])
            pv_url = reverse("admin:message_hub_attachment_preview", args=[obj.pk, idx])
            can_preview = "pdf" in ct or "image" in ct
            preview_html = (
                f'<a href="{pv_url}" target="_blank" class="mh-btn mh-btn-success">{escape(btn_preview)}</a>'
                if can_preview
                else ""
            )

            parts.append(
                f'<div data-row class="mh-attachment-card">'
                f'<div class="mh-attachment-header">'
                f'<div class="mh-attachment-title">'
                f'<span class="mh-attachment-name">{escape(original_name)}</span>'
                f'<span class="mh-attachment-size">{escape(str(size_text))}</span>'
                f"</div>"
                f'<div class="mh-attachment-effective">{escape(title_effective)}：<strong data-effective>{escape(effective_name)}</strong></div>'
                f"</div>"
                f'<div class="mh-attachment-editor">'
                f'<input type="text" data-custom-input value="{escape(normalized_custom_name)}" placeholder="{escape(placeholder_custom)}" class="mh-attachment-input" />'
                f'<div class="mh-attachment-actions">'
                f'<button type="button" data-rename-url="{rename_url}" data-action="save" class="mh-btn mh-btn-primary">{escape(btn_save)}</button>'
                f'<button type="button" data-rename-url="{rename_url}" data-action="reset" class="mh-btn mh-btn-secondary">{escape(btn_reset)}</button>'
                f'<a href="{dl_url}" data-download-link class="mh-btn mh-btn-info" download="{escape(effective_name)}">{escape(btn_download)}</a>'
                f"{preview_html}"
                f"</div>"
                f"</div>"
                f'<div data-msg class="mh-attachment-msg"></div>'
                f"</div>"
            )

        parts.append("</div>")
        parts.append(
            f"""
            <script>
            (function() {{
              if (window.__mhRenameInit) {{ return; }}
              window.__mhRenameInit = true;
              const getCookie = function(name) {{
                const parts = document.cookie ? document.cookie.split('; ') : [];
                for (const p of parts) {{
                  const idx = p.indexOf('=');
                  const k = idx >= 0 ? p.substring(0, idx) : p;
                  if (k === name) {{ return decodeURIComponent(p.substring(idx + 1)); }}
                }}
                return '';
              }};
              document.addEventListener('click', async function(ev) {{
                const target = ev.target;
                if (!(target instanceof HTMLElement)) {{ return; }}
                const button = target.closest('button[data-rename-url]');
                if (!button) {{ return; }}
                const row = button.closest('[data-row]');
                if (!row) {{ return; }}
                const input = row.querySelector('input[data-custom-input]');
                const msg = row.querySelector('[data-msg]');
                const effective = row.querySelector('[data-effective]');
                const downloadLink = row.querySelector('[data-download-link]');
                if (!(input instanceof HTMLInputElement) || !(msg instanceof HTMLElement) || !(effective instanceof HTMLElement)) {{ return; }}

                const action = button.getAttribute('data-action');
                const renameUrl = button.getAttribute('data-rename-url') || '';
                const customFilename = action === 'reset' ? '' : input.value.trim();
                const formData = new FormData();
                formData.append('custom_filename', customFilename);

                button.setAttribute('disabled', 'disabled');
                msg.style.color = '#6b7280';
                msg.textContent = '...';
                try {{
                  const resp = await fetch(renameUrl, {{
                    method: 'POST',
                    headers: {{ 'X-CSRFToken': getCookie('csrftoken') }},
                    body: formData,
                  }});
                  const data = await resp.json();
                  if (!resp.ok || !data.ok) {{
                    msg.style.color = '#dc2626';
                    msg.textContent = data.message || '{escapejs(str(save_failed))}';
                    return;
                  }}
                  input.value = data.custom_filename || '';
                  effective.textContent = data.effective_filename || data.original_filename || '';
                  if (downloadLink instanceof HTMLAnchorElement) {{
                    downloadLink.setAttribute('download', data.effective_filename || data.original_filename || 'attachment');
                  }}
                  msg.style.color = '#059669';
                  msg.textContent = data.message || '{escapejs(str(save_ok))}';
                }} catch (_) {{
                  msg.style.color = '#dc2626';
                  msg.textContent = '{escapejs(str(save_failed))}';
                }} finally {{
                  button.removeAttribute('disabled');
                }}
              }});
            }})();
            </script>
            """
        )

        return mark_safe("".join(parts))
