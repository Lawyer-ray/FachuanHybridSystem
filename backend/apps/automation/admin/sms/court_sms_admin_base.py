"""
法院短信 Admin 基础配置

包含列表显示、字段配置、筛选器等基础 Admin 配置.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext_lazy as _

from apps.automation.models import CourtSMS, CourtSMSStatus, CourtSMSType
from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService

logger = logging.getLogger("apps.automation")


def _get_case_service() -> Any:
    """获取案件服务实例(工厂函数)"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_case_service()


class CourtSMSAdminBase(admin.ModelAdmin[CourtSMS]):
    """法院短信管理基础配置"""

    # 列表显示字段
    list_display = [
        "id",
        "status_display",
        "case_display",
        "content_preview",
        "received_at",
        "has_download_links",
        "case_numbers_display",
        "party_names_display",
        "notification_status",
        "retry_count",
    ]

    # 列表筛选器
    list_filter = [
        "status",
        "received_at",
        ("case", admin.RelatedFieldListFilter),
        ("scraper_task", admin.RelatedFieldListFilter),
    ]

    # 搜索字段
    search_fields = [
        "content",
        "case__name",
    ]

    # 自动完成字段（搜索+下拉）
    autocomplete_fields = ["case"]

    # 排序
    ordering: ClassVar[tuple[str, ...]] = ()

    # 分页
    list_per_page = 20

    # 只读字段
    readonly_fields: ClassVar[list[str]] = [
        "id",
        "created_at",
        "updated_at",
        "download_links_display",
        "case_numbers_display",
        "party_names_display",
        "scraper_task_link",
        "case_log_link",
        "documents_display",
        "notification_details",
        "retry_button",
    ]

    # 字段分组
    fieldsets = (
        (
            _("基本信息"),
            {
                "fields": (
                    "id",
                    "content",
                    "received_at",
                    "status",
                    "sms_type",
                )
            },
        ),
        (
            _("解析结果"),
            {
                "fields": (
                    "download_links_display",
                    "case_numbers_display",
                    "party_names_display",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("关联信息"),
            {
                "fields": (
                    "case",
                    "scraper_task_link",
                    "case_log_link",
                    "documents_display",
                )
            },
        ),
        (
            _("处理状态"),
            {
                "fields": (
                    "error_message",
                    "retry_count",
                    "retry_button",
                )
            },
        ),
        (
            _("通知状态"),
            {
                "fields": ("notification_details",),
                "classes": ("collapse",),
            },
        ),
        (
            _("时间戳"),
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description=_("处理状态"))
    def status_display(self, obj: CourtSMS) -> SafeString:
        """状态显示(带颜色)"""
        status_colors: dict[str, str] = {
            CourtSMSStatus.PENDING: "orange",
            CourtSMSStatus.PARSING: "blue",
            CourtSMSStatus.DOWNLOADING: "blue",
            CourtSMSStatus.DOWNLOAD_FAILED: "red",
            CourtSMSStatus.MATCHING: "blue",
            CourtSMSStatus.PENDING_MANUAL: "orange",
            CourtSMSStatus.RENAMING: "blue",
            CourtSMSStatus.NOTIFYING: "blue",
            CourtSMSStatus.COMPLETED: "green",
            CourtSMSStatus.FAILED: "red",
        }
        color = status_colors.get(obj.status, "gray")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    @admin.display(description=_("短信类型"))
    def sms_type_display(self, obj: CourtSMS) -> str:
        """短信类型显示"""
        if not obj.sms_type:
            return "-"

        type_icons: dict[str, str] = {
            CourtSMSType.DOCUMENT_DELIVERY: "📄",
            CourtSMSType.INFO_NOTIFICATION: "📢",
            CourtSMSType.FILING_NOTIFICATION: "📋",
        }
        icon = type_icons.get(obj.sms_type, "❓")
        return f"{icon} {obj.get_sms_type_display()}"

    @admin.display(description=_("关联案件"))
    def case_display(self, obj: CourtSMS) -> SafeString | str:
        """案件显示"""
        if obj.case:
            url = reverse("admin:cases_case_change", args=[obj.case.id])
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                url,
                obj.case.name[:50] + ("..." if len(obj.case.name) > 50 else ""),
            )
        elif obj.status == CourtSMSStatus.PENDING_MANUAL:
            change_url = reverse("admin:automation_courtsms_change", args=[obj.id])
            return format_html(
                '<a href="{}" style="color: orange; font-weight: bold;">手动关联</a>', change_url
            )
        return "-"

    @admin.display(description=_("短信内容"))
    def content_preview(self, obj: CourtSMS) -> str:
        """短信内容预览"""
        preview = obj.content[:100]
        if len(obj.content) > 100:
            preview += "..."
        return str(preview)

    @admin.display(description=_("下载链接"))
    def has_download_links(self, obj: CourtSMS) -> SafeString:
        """是否有下载链接"""
        if obj.download_links:
            return format_html('<span style="color: green;">✓ {} 个链接</span>', len(obj.download_links))
        return format_html('<span style="color: gray;">{}</span>', "✗ 无链接")

    @admin.display(description=_("提取的案号"))
    def case_numbers_display(self, obj: CourtSMS) -> SafeString | str:
        """案号显示"""
        if obj.case_numbers:
            parts = [format_html("{}", n) for n in obj.case_numbers]
            return mark_safe("<br>".join(str(p) for p in parts))
        return "-"

    @admin.display(description=_("提取的当事人"))
    def party_names_display(self, obj: CourtSMS) -> SafeString | str:
        """当事人显示"""
        if obj.party_names:
            parts = [format_html("{}", n) for n in obj.party_names]
            return mark_safe("<br>".join(str(p) for p in parts))
        return "-"

    @admin.display(description=_("下载链接"))
    def download_links_display(self, obj: CourtSMS) -> SafeString | str:
        """下载链接显示"""
        if obj.download_links:
            parts = [
                format_html('<p><strong>链接 {}:</strong><br><a href="{}" target="_blank">{}</a></p>', i, link, link)
                for i, link in enumerate(obj.download_links, 1)
            ]
            return format_html_join("", "{}", ((p,) for p in parts))
        return "-"

    @admin.display(description=_("下载任务"))
    def scraper_task_link(self, obj: CourtSMS) -> SafeString | str:
        """爬虫任务链接"""
        if obj.scraper_task:
            url = reverse("admin:automation_scrapertask_change", args=[obj.scraper_task.id])
            return format_html(
                '<a href="{}" target="_blank">任务 #{} - {}</a>',
                url,
                obj.scraper_task.id,
                obj.scraper_task.get_status_display(),
            )
        return "-"

    @admin.display(description=_("案件日志"))
    def case_log_link(self, obj: CourtSMS) -> SafeString | str:
        """案件日志链接"""
        if obj.case_log:
            url = reverse("admin:cases_caselog_change", args=[obj.case_log.id])
            return format_html('<a href="{}" target="_blank">日志 #{}</a>', url, obj.case_log.id)
        return "-"

    @admin.display(description=_("关联文书"))
    def documents_display(self, obj: CourtSMS) -> SafeString | str:
        """关联文书显示（支持手动重命名，仅允许修改文件名）"""
        references = CourtSMSDocumentReferenceService().collect(obj)
        if not references:
            return "-"

        source_labels = {
            "court_document": _("文书记录"),
            "sms_reference": _("短信引用"),
            "task_result": _("任务结果"),
            "case_log_attachment": _("案件日志附件"),
        }

        parts: list[SafeString] = [
            format_html(
                "<div style='margin:6px 0 10px;'>"
                "<a class='button' href='{}'>📦 批量下载全部文书</a>"
                "</div>",
                reverse("admin:automation_courtsms_download_all_documents", args=[obj.id]),
            )
        ]
        for index, ref in enumerate(references):
            source_label = source_labels.get(ref.source, ref.source)
            status_display = ref.download_status_display or _("已下载")
            file_name = Path(ref.file_path).name
            file_stem = Path(file_name).stem
            file_suffix = Path(file_name).suffix

            open_url = reverse(
                "admin:automation_courtsms_open_document",
                args=[obj.id, index],
            )
            download_url = f"{open_url}?download=1"
            rename_url = reverse(
                "admin:automation_courtsms_rename_document",
                args=[obj.id, index],
            )

            doc_link_html = ""
            if ref.court_document_id:
                doc_url = reverse("admin:automation_courtdocument_change", args=[ref.court_document_id])
                doc_link_html = format_html(
                    '<a href="{}" target="_blank" style="margin-right:8px;">🔗 文书记录</a>',
                    doc_url,
                )

            parts.append(
                format_html(
                    "<div style='margin:8px 0;padding:8px 10px;border:1px solid #e6eaf2;border-radius:6px;'>"
                    "<div style='margin-bottom:6px;'>"
                    "<a href='{}' target='_blank'>{}</a>"
                    " <span style='color:#666;'>[{}/{}]</span>"
                    "</div>"
                    "<div style='margin-bottom:8px;'>"
                    "{}"
                    "<a href='{}' target='_blank'>📥 下载</a>"
                    "</div>"
                    "<div data-doc-rename-wrap='1' style='display:flex;align-items:center;gap:6px;flex-wrap:wrap;'>"
                    "<input data-rename-stem='1' type='text' value='{}' class='vTextField' style='width:280px;max-width:100%;' />"
                    "<span style='color:#666;'>{}</span>"
                    "<button type='button' class='button' data-rename-url='{}'>重命名</button>"
                    "<span style='color:#999;'>仅修改文件名，不改文件格式</span>"
                    "</div>"
                    "</div>",
                    open_url,
                    file_name,
                    source_label,
                    status_display,
                    doc_link_html,
                    download_url,
                    file_stem,
                    file_suffix,
                    rename_url,
                )
            )

        script = mark_safe(
            "<script>"
            "(function(){"
            " if(window.__courtSmsDocRenameBound){return;}"
            " window.__courtSmsDocRenameBound = true;"
            " const getCookie = function(name){"
            "   const value = '; ' + document.cookie;"
            "   const parts = value.split('; ' + name + '=');"
            "   if(parts.length === 2){ return parts.pop().split(';').shift() || ''; }"
            "   return '';"
            " };"
            " document.addEventListener('click', function(event){"
            "   const target = event.target;"
            "   if(!(target instanceof HTMLElement)){return;}"
            "   const button = target.closest('[data-rename-url]');"
            "   if(!(button instanceof HTMLElement)){return;}"
            "   const wrap = button.closest('[data-doc-rename-wrap]');"
            "   if(!(wrap instanceof HTMLElement)){return;}"
            "   const input = wrap.querySelector('input[data-rename-stem]');"
            "   if(!(input instanceof HTMLInputElement)){return;}"
            "   const renameUrl = button.getAttribute('data-rename-url') || '';"
            "   const newStem = (input.value || '').trim();"
            "   if(!renameUrl){return;}"
            "   if(!newStem){ alert('文件名不能为空'); return; }"
            "   const params = new URLSearchParams();"
            "   params.set('new_stem', newStem);"
            "   fetch(renameUrl, {"
            "     method: 'POST',"
            "     credentials: 'same-origin',"
            "     headers: {"
            "       'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',"
            "       'X-CSRFToken': getCookie('csrftoken')"
            "     },"
            "     body: params.toString()"
            "   }).then(function(){ window.location.reload(); });"
            " });"
            "})();"
            "</script>"
        )

        return format_html_join("", "{}", ((p,) for p in [*parts, script]))

    @admin.display(description=_("通知状态"))
    def notification_status(self, obj: CourtSMS) -> SafeString:
        """多平台通知状态"""
        # 优先使用 notification_results
        if obj.notification_results and isinstance(obj.notification_results, dict):
            results = obj.notification_results
            success_platforms = [k for k, v in results.items() if isinstance(v, dict) and v.get("success")]
            fail_platforms = [k for k, v in results.items() if isinstance(v, dict) and not v.get("success")]

            if success_platforms:
                parts = [mark_safe('<span style="color: green;">✓ 通知成功</span>')]
                for p in success_platforms:
                    info = results[p]
                    sent_at = info.get("sent_at", "")
                    if sent_at:
                        # 只显示日期时间部分
                        sent_display = sent_at[:16] if len(sent_at) > 16 else sent_at
                        parts.append(format_html('<br><small>{}: {}</small>', p, sent_display))
                    else:
                        parts.append(format_html('<br><small>{}</small>', p))
                if fail_platforms:
                    parts.append(format_html('<br><small style="color: #d63384;">失败: {}</small>', ", ".join(fail_platforms)))
                return mark_safe("".join(str(p) for p in parts))
            elif fail_platforms:
                first_error = ""
                for p in fail_platforms:
                    err = results[p].get("error", "")
                    if err:
                        first_error = err[:30] + ("..." if len(err) > 30 else "")
                        break
                return format_html(
                    '<span style="color: red;">✗ 通知失败</span><br><small style="color: #d63384;">{}</small>',
                    first_error,
                )

        # 向后兼容：检查旧的 feishu_sent_at / feishu_error 字段
        if obj.feishu_sent_at:
            return format_html(
                '<span style="color: green;">✓ 通知成功</span><br><small>{}</small>',
                obj.feishu_sent_at.strftime("%m-%d %H:%M"),
            )
        elif obj.feishu_error:
            error_preview = obj.feishu_error[:30] + ("..." if len(obj.feishu_error) > 30 else "")
            return format_html(
                '<span style="color: red;">✗ 通知失败</span><br><small style="color: #d63384;">{}</small>',
                error_preview,
            )
        return format_html('<span style="color: gray;">{}</span>', "- 未发送")

    @admin.display(description=_("通知详情"))
    def notification_details(self, obj: CourtSMS) -> str:
        """多平台通知详情"""
        if obj.notification_results and isinstance(obj.notification_results, dict):
            lines = []
            for platform, info in obj.notification_results.items():
                if not isinstance(info, dict):
                    continue
                status = "成功" if info.get("success") else "失败"
                sent_at = info.get("sent_at", "")
                error = info.get("error", "")
                chat_id = info.get("chat_id", "")
                line = f"{platform}: {status}"
                if sent_at:
                    line += f", 时间: {sent_at[:19]}"
                if chat_id:
                    line += f", Chat ID: {chat_id}"
                if error:
                    line += f", 错误: {error[:80]}"
                lines.append(line)
            if lines:
                return "\n".join(lines)

        # 向后兼容
        if obj.feishu_sent_at:
            return f"发送时间: {obj.feishu_sent_at}"
        elif obj.feishu_error:
            return f"发送失败: {obj.feishu_error}"
        return "未发送"

    @admin.display(description=_("操作"))
    def retry_button(self, obj: CourtSMS) -> SafeString | str:
        """重新处理按钮"""
        if obj.id:
            retry_url = reverse("admin:automation_courtsms_retry", args=[obj.id])
            return format_html(
                '<a href="{}" class="button" onclick="return confirm('
                "'确认要重新处理这条短信吗?这将重置状态并重新执行完整流程.');"
                '">'
                "🔄 重新处理</a>",
                retry_url,
            )
        return "-"

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet[CourtSMS], search_term: str
    ) -> tuple[QuerySet[CourtSMS], bool]:
        """自定义搜索,支持 JSON 字段搜索"""
        queryset, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        return queryset, may_have_duplicates

    def get_queryset(self, request: HttpRequest) -> QuerySet[CourtSMS]:
        """优化查询性能"""
        return (
            super()
            .get_queryset(request)
            .select_related("case", "scraper_task", "case_log")
            .prefetch_related("scraper_task__documents", "case_log__attachments")
        )

    def get_fields(self, request: HttpRequest, obj: CourtSMS | None = None) -> Any:
        """根据是否为新增页面返回不同的字段"""
        if obj is None:
            return ["content", "received_at"]
        else:
            return [field.name for field in self.model._meta.fields if field.name != "id"]

    def get_readonly_fields(self, request: HttpRequest, obj: CourtSMS | None = None) -> list[str] | tuple[str, ...]:
        """根据是否为新增页面返回不同的只读字段"""
        if obj is None:
            return ["received_at"]
        else:
            return self.readonly_fields

    def get_fieldsets(self, request: HttpRequest, obj: CourtSMS | None = None) -> Any:
        """根据是否为新增页面返回不同的字段分组"""
        if obj is None:
            return [
                (
                    str(_("短信信息")),
                    {
                        "fields": ("content", "received_at"),
                        "description": (
                            "请输入完整的法院短信内容。收到时间将自动设置为当前时间。"
                            "<br>"
                            "<style>"
                            ".sms-platforms{margin-top:12px;padding:12px 14px;background:#f6f8fc;border-radius:10px;border:1px solid #e4eaf5;}"
                            ".sms-platforms-title{font-size:13px;color:#445069;margin-bottom:8px;font-weight:600;}"
                            ".sms-platforms-tags{display:flex;flex-wrap:wrap;gap:8px;}"
                            ".sms-platforms-tags span{background:#edf2ff;color:#2f57d8;padding:4px 10px;border-radius:999px;font-size:12px;border:0;white-space:nowrap;}"
                            ".sms-platforms-tags span code{color:#5e78d6;font-size:11px;}"
                            ".sfdw-tail6-wrap{display:none;padding:12px 0 14px;border-top:0;}"
                            ".sfdw-tail6-row{display:grid;grid-template-columns:160px minmax(260px,420px);align-items:flex-start;}"
                            ".sfdw-tail6-label{padding:4px 10px 0 0;color:#333;font-size:13px;font-weight:600;box-sizing:border-box;}"
                            ".sfdw-tail6-body{padding-right:12px;max-width:420px;}"
                            ".sfdw-tail6-wrap input{width:100%;max-width:420px;box-sizing:border-box;}"
                            "</style>"
                            "<div class='sms-platforms'>"
                            "<div class='sms-platforms-title'>📥 支持自动下载</div>"
                            "<div class='sms-platforms-tags'>"
                            "<span title='zxfw.court.gov.cn'>人民法院在线服务网</span>"
                            "<span title='sd.gdems.com'>睿法智达</span>"
                            "<span title='jysd.10102368.com'>集约送达</span>"
                            "<span title='dzsd.hbfy.gov.cn'>湖北电子送达</span>"
                            "<span title='sfpt.cdfy12368.gov.cn'>司法送达网</span>"
                            "<span title='171.106.48.55:28083'>广西法院短信平台</span>"
                            "</div>"
                            "</div>"
                            "<div id='sfdw-tail6-wrap' class='form-row sfdw-tail6-wrap'>"
                            "<div class='sfdw-tail6-row'>"
                            "<label for='id_sfdw_phone_tail6' class='sfdw-tail6-label'>手机号后6位：</label>"
                            "<div class='sfdw-tail6-body'>"
                            "<input id='id_sfdw_phone_tail6' name='sfdw_phone_tail6' type='text' maxlength='6' inputmode='numeric' pattern='[0-9]{6}' class='vTextField' placeholder='留空会自动回退律师手机号后6位。' />"
                            "</div>"
                            "</div>"
                            "</div>"
                            "<script>"
                            "(function(){"
                            "  const mount = function(){"
                            "    const wrap = document.getElementById('sfdw-tail6-wrap');"
                            "    const row = wrap ? wrap.querySelector('.sfdw-tail6-row') : null;"
                            "    const input = document.getElementById('id_sfdw_phone_tail6');"
                            "    const contentRow = document.querySelector('.form-row.field-content');"
                            "    const receivedAtRow = document.querySelector('.form-row.field-received_at');"
                            "    const contentLabel = contentRow ? contentRow.querySelector('label') : null;"
                            "    if(!wrap || !row || !input){return;}"
                            "    if(receivedAtRow && wrap.previousElementSibling !== contentRow){"
                            "      receivedAtRow.insertAdjacentElement('beforebegin', wrap);"
                            "    } else if(contentRow && wrap.previousElementSibling !== contentRow) {"
                            "      contentRow.insertAdjacentElement('afterend', wrap);"
                            "    }"
                            "    wrap.style.display = 'block';"
                            "    if(contentLabel){"
                            "      const labelRect = contentLabel.getBoundingClientRect();"
                            "      const rowRect = row.getBoundingClientRect();"
                            "      const w = Math.ceil(labelRect.width);"
                            "      const rawOffset = Math.round(labelRect.left - rowRect.left);"
                            "      const offset = Math.max(0, Math.min(40, rawOffset));"
                            "      if(w > 0){ row.style.gridTemplateColumns = w + 'px minmax(260px, 420px)'; }"
                            "      row.style.paddingLeft = offset + 'px';"
                            "    }"
                            "    input.value = (input.value || '').replace(/\\D/g, '').slice(0, 6);"
                            "    input.addEventListener('input', function(){"
                            "      input.value = (input.value || '').replace(/\\D/g, '').slice(0, 6);"
                            "    });"
                            "  };"
                            "  if(document.readyState === 'loading'){"
                            "    document.addEventListener('DOMContentLoaded', mount);"
                            "  } else {"
                            "    mount();"
                            "  }"
                            "})();"
                            "</script>"
                        ),
                    },
                ),
            ]
        else:
            return list(self.fieldsets)

    def get_form(self, request: HttpRequest, obj: CourtSMS | None = None, change: bool = False, **kwargs: Any) -> Any:
        """自定义表单"""
        form = super().get_form(request, obj, change=change, **kwargs)

        if obj is None:
            from django.utils import timezone

            received_at_field = form.base_fields.get("received_at")
            if received_at_field:
                received_at_field.initial = timezone.now()
                received_at_field.help_text = "自动设置为当前时间,不可修改"

            content_field = form.base_fields.get("content")
            if content_field:
                content_field.required = True
                content_field.help_text = "请粘贴完整的法院短信内容"
                if hasattr(content_field, "widget") and hasattr(content_field.widget, "attrs"):
                    content_field.widget.attrs.update({"rows": 8, "placeholder": "请粘贴完整的法院短信内容..."})

        return form
