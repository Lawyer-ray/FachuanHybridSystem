"""Django admin configuration."""

from __future__ import annotations

import calendar
import json
from datetime import date, datetime
from urllib.parse import urlencode

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.template.response import TemplateResponse
from django.urls import URLPattern, path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from ..models import Reminder, ReminderType
from simple_history.admin import SimpleHistoryAdmin


class ReminderAdminForm(forms.ModelForm[Reminder]):
    class Meta:
        model = Reminder
        fields: str = "__all__"
        help_texts: dict[str, object] = {
            "metadata": _(
                '用于存放"结构化扩展信息"的 JSON(不参与业务必填).可留空或填 {}.'
                "常见键:source(来源,如 court_sms / manual)、file_name(来源文件名)、"
                'external_id(外部ID)、note(备注).示例:{"source":"court_sms","file_name":"传票.pdf"}'
            ),
        }
        widgets: dict[str, forms.Widget] = {
            "metadata": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_metadata(self) -> object:
        value = self.cleaned_data.get("metadata")
        if value in (None, ""):
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                raise forms.ValidationError(_("请输入合法的 JSON 格式")) from None
            if not isinstance(parsed, dict):
                raise forms.ValidationError(_("请输入合法的 JSON 对象（非数组或标量）"))
            return parsed
        raise forms.ValidationError(_("请输入合法的 JSON 格式"))


@admin.register(Reminder)
class ReminderAdmin(SimpleHistoryAdmin, admin.ModelAdmin[Reminder]):
    form = ReminderAdminForm
    list_display = (
        "id",
        "due_at",
        "reminder_type",
        "content",
        "contract",
        "case",
        "case_log",
        "created_at",
        "updated_at",
    )
    list_display_links = ("id", "content")
    list_filter = ("reminder_type", "created_at")
    search_fields = ("content",)
    list_select_related = ("contract", "case", "case_log")
    autocomplete_fields = ["contract", "case", "case_log"]
    readonly_fields = ("created_at", "updated_at", "metadata_display")
    ordering = ("-due_at", "-id")
    date_hierarchy = "due_at"
    list_per_page = 30
    change_list_template = "admin/reminders/reminder/change_list.html"

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "content",
                    "reminder_type",
                    "due_at",
                    "contract",
                    "case",
                    "case_log",
                    "metadata_display",
                ),
            },
        ),
        (
            _("扩展数据（原始 JSON）"),
            {
                "fields": ("metadata",),
                "classes": ("collapse",),
            },
        ),
        (
            _("时间信息"),
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    @admin.display(description=_("扩展数据"))
    def metadata_display(self, obj: Reminder) -> str:
        from django.utils.html import escape

        data = obj.metadata if isinstance(obj.metadata, dict) else {}
        if not data:
            return "—"
        rows = "".join(
            f'<tr><td style="padding:4px 12px 4px 0;font-weight:600;white-space:nowrap;vertical-align:top;'
            f'color:#475569;border-bottom:1px solid #f1f5f9">{escape(str(key))}</td>'
            f'<td style="padding:4px 0;border-bottom:1px solid #f1f5f9">{escape(str(value))}</td></tr>'
            for key, value in data.items()
        )
        return str(mark_safe(f'<table style="border-spacing:0;font-size:13px">{rows}</table>'))

    def get_urls(self) -> list[URLPattern]:
        urls = super().get_urls()
        custom_urls = [
            path("calendar/", self.admin_site.admin_view(self.calendar_view), name="reminders_reminder_calendar"),
            path(
                "calendar/create/",
                self.admin_site.admin_view(self.calendar_create_view),
                name="reminders_reminder_calendar_create",
            ),
            path(
                "calendar/target-options/",
                self.admin_site.admin_view(self.calendar_target_options_view),
                name="reminders_reminder_calendar_target_options",
            ),
            path(
                "calendar/sync/providers/",
                self.admin_site.admin_view(self.calendar_sync_providers_view),
                name="reminders_reminder_calendar_sync_providers",
            ),
            path(
                "calendar/sync/preview/",
                self.admin_site.admin_view(self.calendar_sync_preview_view),
                name="reminders_reminder_calendar_sync_preview",
            ),
            path(
                "calendar/sync/import/",
                self.admin_site.admin_view(self.calendar_sync_import_view),
                name="reminders_reminder_calendar_sync_import",
            ),
            path(
                "calendar/sync/open-privacy/",
                self.admin_site.admin_view(self.calendar_sync_open_privacy_view),
                name="reminders_reminder_calendar_sync_open_privacy",
            ),
            path(
                "calendar/sync/clear/",
                self.admin_site.admin_view(self.calendar_sync_clear_view),
                name="reminders_reminder_calendar_sync_clear",
            ),
            path(
                "calendar/sync/calendars/",
                self.admin_site.admin_view(self.calendar_sync_calendars_view),
                name="reminders_reminder_calendar_sync_calendars",
            ),
            path(
                "calendar/export/",
                self.admin_site.admin_view(self.calendar_export_view),
                name="reminders_reminder_calendar_export",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, object] | None = None) -> HttpResponse:
        context = extra_context or {}
        context["calendar_url"] = reverse("admin:reminders_reminder_calendar")
        return super().changelist_view(request, extra_context=context)

    def calendar_view(self, request: HttpRequest) -> TemplateResponse:
        year, month = self._parse_year_month(request)
        month_start = date(year, month, 1)
        next_year, next_month = self._shift_month(year, month, 1)
        next_month_start = date(next_year, next_month, 1)
        previous_year, previous_month = self._shift_month(year, month, -1)

        selected_type = request.GET.get("reminder_type", "").strip()
        selected_scope = request.GET.get("scope", "all").strip()
        selected_status = request.GET.get("status", "all").strip()

        reminders = self._query_month_reminders(
            month_start=month_start,
            next_month_start=next_month_start,
            selected_type=selected_type,
            selected_scope=selected_scope,
            selected_status=selected_status,
        )
        events_by_day = self._group_events_by_day(reminders=reminders)
        calendar_weeks = self._build_calendar_weeks(year=year, month=month, events_by_day=events_by_day)

        preserve_filters: dict[str, str] = {}
        if selected_type:
            preserve_filters["reminder_type"] = selected_type
        if selected_scope != "all":
            preserve_filters["scope"] = selected_scope
        if selected_status != "all":
            preserve_filters["status"] = selected_status

        context: dict[str, object] = {
            **self.admin_site.each_context(request),
            "title": _("提醒日历"),
            "opts": self.model._meta,
            "calendar_weeks": calendar_weeks,
            "month_title": _("%(year)s年%(month)s月") % {"year": year, "month": month},
            "weekday_labels": [
                _("周一"),
                _("周二"),
                _("周三"),
                _("周四"),
                _("周五"),
                _("周六"),
                _("周日"),
            ],
            "selected_type": selected_type,
            "selected_scope": selected_scope,
            "selected_status": selected_status,
            "reminder_type_options": [{"value": value, "label": str(label)} for value, label in ReminderType.choices],
            "current_year": year,
            "current_month": month,
            "prev_url": self._build_calendar_url(previous_year, previous_month, preserve_filters),
            "next_url": self._build_calendar_url(next_year, next_month, preserve_filters),
            "today_url": self._build_calendar_url(
                timezone.localdate().year,
                timezone.localdate().month,
                preserve_filters,
            ),
            "changelist_url": reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"),
            "calendar_create_url": reverse("admin:reminders_reminder_calendar_create"),
            "target_options_url": reverse("admin:reminders_reminder_calendar_target_options"),
            "sync_providers_url": reverse("admin:reminders_reminder_calendar_sync_providers"),
            "sync_preview_url": reverse("admin:reminders_reminder_calendar_sync_preview"),
            "sync_import_url": reverse("admin:reminders_reminder_calendar_sync_import"),
            "export_url": reverse("admin:reminders_reminder_calendar_export"),
            "current_calendar_url": request.get_full_path(),
        }
        return TemplateResponse(request, "admin/reminders/reminder/calendar.html", context)

    def calendar_create_view(self, request: HttpRequest) -> HttpResponseRedirect:
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:reminders_reminder_calendar"))

        if not self.has_add_permission(request):
            self.message_user(request, _("你没有新增提醒的权限。"), level="error")
            return HttpResponseRedirect(reverse("admin:reminders_reminder_calendar"))

        return_url = self._safe_return_url(request=request)
        content = request.POST.get("content", "").strip()
        reminder_type = request.POST.get("reminder_type", "").strip()
        due_date_text = request.POST.get("due_date", "").strip()
        due_time_text = request.POST.get("due_time", "").strip()
        target_type = request.POST.get("target_type", "").strip()
        target_id = self._parse_positive_int(request.POST.get("target_id", ""))

        if not content:
            self.message_user(request, _("提醒事项不能为空。"), level="error")
            return HttpResponseRedirect(return_url)

        valid_types = {value for value, _ in ReminderType.choices}
        if reminder_type not in valid_types:
            self.message_user(request, _("提醒类型不合法。"), level="error")
            return HttpResponseRedirect(return_url)

        if not due_date_text or not due_time_text:
            self.message_user(request, _("请选择提醒日期和时间。"), level="error")
            return HttpResponseRedirect(return_url)

        if target_type and target_type not in {"contract", "case", "case_log"}:
            self.message_user(request, _("请选择合法的关联对象类型。"), level="error")
            return HttpResponseRedirect(return_url)

        if target_type and target_id is None:
            self.message_user(request, _("关联对象ID必须是正整数。"), level="error")
            return HttpResponseRedirect(return_url)

        if not target_type and target_id is not None:
            self.message_user(request, _("请选择关联对象类型后再选择具体对象。"), level="error")
            return HttpResponseRedirect(return_url)

        try:
            due_naive = datetime.fromisoformat(f"{due_date_text}T{due_time_text}")
        except ValueError:
            self.message_user(request, _("提醒时间格式不正确。"), level="error")
            return HttpResponseRedirect(return_url)

        due_at = timezone.make_aware(due_naive, timezone.get_current_timezone())
        create_kwargs: dict[str, object] = {
            "content": content,
            "reminder_type": reminder_type,
            "due_at": due_at,
            "metadata": {},
        }
        if target_type == "contract":
            create_kwargs["contract_id"] = target_id
        elif target_type == "case":
            create_kwargs["case_id"] = target_id
        elif target_type == "case_log":
            create_kwargs["case_log_id"] = target_id

        reminder = Reminder(**create_kwargs)
        try:
            reminder.full_clean()
            reminder.save()
        except ValidationError as exc:
            messages = exc.messages if exc.messages else [_("新增提醒失败，请检查输入内容。")]
            self.message_user(request, "；".join(str(message) for message in messages), level="error")
            return HttpResponseRedirect(return_url)

        self.message_user(request, _("提醒已创建。"))
        return HttpResponseRedirect(return_url)

    def calendar_target_options_view(self, request: HttpRequest) -> JsonResponse:
        if request.method != "GET":
            return JsonResponse({"items": [], "groups": []}, status=405)

        if not self.has_add_permission(request):
            return JsonResponse({"items": [], "groups": []}, status=403)

        from apps.cases.models import Case
        from apps.cases.models.log import CaseLog
        from apps.contracts.models.contract import Contract

        keyword = request.GET.get("q", "").strip()
        limit_per_group = 12

        contract_queryset = Contract.objects.all()
        case_queryset = Case.objects.all()
        case_log_queryset = CaseLog.objects.select_related("case").all()

        if keyword:
            contract_queryset = contract_queryset.filter(name__icontains=keyword)
            case_queryset = case_queryset.filter(name__icontains=keyword)
            case_log_queryset = case_log_queryset.filter(
                Q(case__name__icontains=keyword) | Q(content__icontains=keyword)
            )

        groups: list[dict[str, object]] = []

        contract_items = [
            {
                "id": row["id"],
                "name": row["name"],
                "target_type": "contract",
                "target_type_label": str(_("合同")),
            }
            for row in contract_queryset.order_by("-id").values("id", "name")[:limit_per_group]
        ]
        if contract_items:
            groups.append(
                {
                    "key": "contract",
                    "label": str(_("合同")),
                    "items": contract_items,
                }
            )

        case_items = [
            {
                "id": row["id"],
                "name": row["name"],
                "target_type": "case",
                "target_type_label": str(_("案件")),
            }
            for row in case_queryset.order_by("-id").values("id", "name")[:limit_per_group]
        ]
        if case_items:
            groups.append(
                {
                    "key": "case",
                    "label": str(_("案件")),
                    "items": case_items,
                }
            )

        case_log_items: list[dict[str, object]] = []
        for item in case_log_queryset.order_by("-id")[:limit_per_group]:
            preview = item.content.strip().replace("\n", " ")
            if len(preview) > 24:
                preview = f"{preview[:24]}..."
            label = _("#%(id)s %(case)s｜%(preview)s") % {
                "id": item.id,
                "case": item.case.name,
                "preview": preview or _("无内容"),
            }
            case_log_items.append(
                {
                    "id": item.id,
                    "name": label,
                    "target_type": "case_log",
                    "target_type_label": str(_("案件日志")),
                }
            )
        if case_log_items:
            groups.append(
                {
                    "key": "case_log",
                    "label": str(_("案件日志")),
                    "items": case_log_items,
                }
            )

        merged_items: list[dict[str, object]] = []
        for group in groups:
            group_items = group.get("items", [])
            if isinstance(group_items, list):
                merged_items.extend(group_items)

        return JsonResponse({"items": merged_items, "groups": groups})

    def calendar_sync_providers_view(self, request: HttpRequest) -> JsonResponse:
        """GET: Return available calendar sync providers as JSON."""
        if not self.has_add_permission(request):
            return JsonResponse({"providers": []}, status=403)

        from apps.reminders.services.wiring import get_calendar_sync_service

        sync_service = get_calendar_sync_service()
        providers = sync_service.get_available_providers()

        # Include macOS Calendar authorization status
        calendar_auth_status = ""
        calendar_auth_code = -1
        local_providers = [p for p in providers if p["name"] in ("mac", "windows")]
        if any(p["name"] == "mac" for p in local_providers):
            try:
                from apps.reminders.services.calendar_providers.mac_provider import MacCalendarProvider

                auth_code = MacCalendarProvider.get_auth_status()
                calendar_auth_code = auth_code
                if auth_code == 0:
                    calendar_auth_status = "not_determined"
                elif auth_code == 1:
                    calendar_auth_status = "restricted"
                elif auth_code == 2:
                    calendar_auth_status = "denied"
                elif auth_code == 3:
                    calendar_auth_status = "authorized"
            except Exception:
                calendar_auth_status = "unknown"

        return JsonResponse({
            "providers": providers,
            "calendar_auth_status": calendar_auth_status,
            "calendar_auth_code": calendar_auth_code,
        })

    def calendar_sync_preview_view(self, request: HttpRequest) -> JsonResponse:
        """POST: Preview calendar events from .ics file, URL, or local provider."""
        if not self.has_add_permission(request):
            return JsonResponse({"events": [], "error": "无权限"}, status=403)

        from apps.reminders.services.wiring import get_calendar_sync_service

        sync_service = get_calendar_sync_service()

        source = request.POST.get("source", "").strip()

        if source == "ics_file":
            uploaded_file = request.FILES.get("ics_file")
            if not uploaded_file:
                return JsonResponse({"events": [], "error": "未选择文件"}, status=400)
            if not (uploaded_file.name or "").lower().endswith(".ics"):
                return JsonResponse({"events": [], "error": "仅支持 .ics 文件"}, status=400)
            if (uploaded_file.size or 0) > 5 * 1024 * 1024:
                return JsonResponse({"events": [], "error": "文件大小超过 5MB 限制"}, status=400)
            ics_content = uploaded_file.read()
            events = sync_service.preview_from_ics(ics_content)
        elif source == "ics_url":
            url = request.POST.get("url", "").strip()
            if not url:
                return JsonResponse({"events": [], "error": "URL 不能为空"}, status=400)
            events = sync_service.preview_from_url(url)
        elif source in ("mac", "windows"):
            from datetime import datetime as dt, timedelta as td

            kwargs: dict[str, object] = {}
            start_date_str = request.POST.get("start_date", "").strip()
            end_date_str = request.POST.get("end_date", "").strip()
            if start_date_str:
                try:
                    kwargs["start_date"] = timezone.make_aware(
                        dt.fromisoformat(start_date_str), timezone.get_current_timezone()
                    )
                except ValueError:
                    pass
            if end_date_str:
                try:
                    kwargs["end_date"] = timezone.make_aware(
                        dt.fromisoformat(end_date_str) + td(days=1),
                        timezone.get_current_timezone(),
                    )
                except ValueError:
                    pass
            # Parse included calendars (preferred) or excluded calendars (legacy)
            import json as json_mod

            included_calendars_raw = request.POST.get("included_calendars", "").strip()
            excluded_calendars_raw = request.POST.get("excluded_calendars", "").strip()
            if included_calendars_raw:
                try:
                    included_calendars = json_mod.loads(included_calendars_raw)
                    if isinstance(included_calendars, list):
                        kwargs["included_calendars"] = included_calendars
                except (json_mod.JSONDecodeError, TypeError):
                    pass
            if "included_calendars" not in kwargs and excluded_calendars_raw:
                try:
                    excluded_calendars = json_mod.loads(excluded_calendars_raw)
                    if isinstance(excluded_calendars, list):
                        kwargs["excluded_calendars"] = excluded_calendars
                except (json_mod.JSONDecodeError, TypeError):
                    pass
            events = sync_service.preview_from_local(source, **kwargs)
        else:
            return JsonResponse({"events": [], "error": f"不支持的来源: {source}"}, status=400)

        return JsonResponse({"events": events, "error": ""})

    def calendar_sync_import_view(self, request: HttpRequest) -> JsonResponse:
        """POST: Import selected calendar events as Reminders."""
        if not self.has_add_permission(request):
            return JsonResponse({"created": 0, "skipped": 0, "error": "无权限"}, status=403)

        from apps.reminders.services.wiring import get_calendar_sync_service

        sync_service = get_calendar_sync_service()

        import json as json_mod

        events_json = request.POST.get("events", "[]")
        try:
            events = json_mod.loads(events_json)
        except (json_mod.JSONDecodeError, TypeError):
            return JsonResponse({"created": 0, "skipped": 0, "error": "事件数据格式错误"}, status=400)

        if not isinstance(events, list):
            return JsonResponse({"created": 0, "skipped": 0, "error": "事件数据格式错误"}, status=400)

        created, skipped = sync_service.import_events(events)
        return JsonResponse({"created": created, "skipped": skipped, "error": ""})

    def calendar_sync_open_privacy_view(self, request: HttpRequest) -> JsonResponse:
        """POST: Open macOS System Settings → Privacy → Calendars."""
        import platform
        import subprocess

        if platform.system() == "Darwin":
            try:
                # Open System Settings → Privacy & Security → Calendars
                import shutil

                open_cmd = shutil.which("open") or "/usr/bin/open"
                subprocess.Popen(
                    [open_cmd, "x-apple.systempreferences:com.apple.preference.security?Privacy_Calendars"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return JsonResponse({"ok": True})
            except Exception:
                return JsonResponse({"ok": False, "error": "无法打开系统设置"})
        return JsonResponse({"ok": False, "error": "仅支持 macOS"})

    def calendar_sync_calendars_view(self, request: HttpRequest) -> JsonResponse:
        """GET: Return available local calendars for selection."""
        if not self.has_add_permission(request):
            return JsonResponse({"calendars": []}, status=403)

        provider_name = request.GET.get("provider", "").strip()
        if provider_name not in ("mac", "windows"):
            return JsonResponse({"calendars": []}, status=400)

        try:
            if provider_name == "mac":
                from apps.reminders.services.calendar_providers.mac_provider import MacCalendarProvider

                provider = MacCalendarProvider()
                calendars = provider.list_calendars()
                # Mark default-excluded calendars
                excluded_set = set(MacCalendarProvider.DEFAULT_EXCLUDED_CALENDARS)
                for cal in calendars:
                    cal["default_excluded"] = cal["name"] in excluded_set
                return JsonResponse({"calendars": calendars})
        except Exception as exc:
            return JsonResponse({"calendars": [], "error": str(exc)})

        return JsonResponse({"calendars": []})

    def calendar_sync_clear_view(self, request: HttpRequest) -> JsonResponse:
        """POST: Delete all Reminders that were imported from calendar sync."""
        if not self.has_delete_permission(request, obj=None):
            return JsonResponse({"deleted": 0, "error": "无权限"}, status=403)

        from apps.reminders.models import Reminder

        deleted_count, _ = Reminder.objects.filter(
            metadata__source="local_calendar_sync"
        ).delete()
        import logging

        logging.getLogger(__name__).info("Cleared %d synced calendar reminders", deleted_count)
        return JsonResponse({"deleted": deleted_count, "error": ""})

    def calendar_export_view(self, request: HttpRequest) -> HttpResponse:
        """GET: Export filtered Reminders as .ics file download."""
        if not self.has_view_permission(request):
            return HttpResponse("无权限", status=403)

        year, month = self._parse_year_month(request)
        reminder_type = request.GET.get("reminder_type", "").strip()
        scope = request.GET.get("scope", "all").strip()
        status = request.GET.get("status", "all").strip()

        from apps.reminders.services.wiring import get_calendar_export_service

        export_service = get_calendar_export_service()
        ics_bytes = export_service.export_reminders(
            year=year,
            month=month,
            reminder_type=reminder_type,
            scope=scope,
            status=status,
        )

        filter_parts: list[str] = []
        if reminder_type:
            type_label = dict(ReminderType.choices).get(reminder_type, reminder_type)
            filter_parts.append(str(type_label))
        if scope != "all":
            scope_labels = {"contract": "合同", "case": "案件", "case_log": "案件日志"}
            filter_parts.append(scope_labels.get(scope, scope))
        if status != "all":
            status_labels = {"overdue": "已逾期", "upcoming": "未到期"}
            filter_parts.append(status_labels.get(status, status))

        filter_str = "-".join(filter_parts) if filter_parts else "全部"
        filename = f"法穿提醒-{year}年{month}月-{filter_str}.ics"

        response = HttpResponse(ics_bytes, content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def _safe_return_url(self, *, request: HttpRequest) -> str:
        fallback = reverse("admin:reminders_reminder_calendar")
        return_url = request.POST.get("return_url", "").strip()
        if return_url and url_has_allowed_host_and_scheme(
            url=return_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return return_url
        return fallback

    def _parse_positive_int(self, raw_value: str) -> int | None:
        value = raw_value.strip()
        if not value:
            return None
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed > 0 else None

    def _parse_year_month(self, request: HttpRequest) -> tuple[int, int]:
        today = timezone.localdate()
        year_raw = request.GET.get("year")
        month_raw = request.GET.get("month")
        try:
            year = int(year_raw) if year_raw else today.year
            month = int(month_raw) if month_raw else today.month
        except ValueError:
            return today.year, today.month
        if month < 1 or month > 12:
            month = today.month
        if year < 1970 or year > 2100:
            year = today.year
        return year, month

    def _shift_month(self, year: int, month: int, delta: int) -> tuple[int, int]:
        month_index = year * 12 + (month - 1) + delta
        return month_index // 12, month_index % 12 + 1

    def _query_month_reminders(
        self,
        *,
        month_start: date,
        next_month_start: date,
        selected_type: str,
        selected_scope: str,
        selected_status: str,
    ) -> list[Reminder]:
        queryset = Reminder.objects.select_related("contract", "case", "case_log", "case_log__case").filter(
            due_at__date__gte=month_start,
            due_at__date__lt=next_month_start,
        )

        valid_types = {value for value, _ in ReminderType.choices}
        if selected_type in valid_types:
            queryset = queryset.filter(reminder_type=selected_type)

        if selected_scope == "contract":
            queryset = queryset.filter(contract_id__isnull=False)
        elif selected_scope == "case":
            queryset = queryset.filter(case_id__isnull=False)
        elif selected_scope == "case_log":
            queryset = queryset.filter(case_log_id__isnull=False)

        now = timezone.now()
        if selected_status == "overdue":
            queryset = queryset.filter(due_at__lt=now)
        elif selected_status == "upcoming":
            queryset = queryset.filter(due_at__gte=now)

        return list(queryset.order_by("due_at", "id"))

    def _group_events_by_day(self, *, reminders: list[Reminder]) -> dict[int, list[dict[str, object]]]:
        events_by_day: dict[int, list[dict[str, object]]] = {}
        hearing_merged_index: dict[int, dict[tuple[object, ...], dict[str, object]]] = {}
        now = timezone.now()
        change_url_name = f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_change"

        for reminder in reminders:
            due_local = timezone.localtime(reminder.due_at)
            if reminder.contract_id is not None and reminder.contract is not None:
                target_type = _("合同")
                target_name = reminder.contract.name
            elif reminder.case_id is not None and reminder.case is not None:
                target_type = _("案件")
                target_name = reminder.case.name
            elif reminder.case_log_id is not None and reminder.case_log is not None:
                target_type = _("案件日志")
                target_name = _("#%(id)s %(case)s") % {
                    "id": reminder.case_log_id,
                    "case": reminder.case_log.case.name,
                }
            else:
                target_type = _("未绑定")
                target_name = _("独立提醒")

            type_label = str(dict(ReminderType.choices).get(reminder.reminder_type, reminder.reminder_type))
            metadata = reminder.metadata if isinstance(reminder.metadata, dict) else {}
            courtroom = str(metadata.get("courtroom", "")).strip()
            lawyer_name = str(metadata.get("lawyer_name", "")).strip()
            # For synced calendar events, use "location" instead of "courtroom"
            location = str(metadata.get("location", "")).strip()

            # 一张网庭审日程同事件合并展示：同 source_id 显示一条，律师姓名聚合
            merge_key: tuple[object, ...] | None = None
            if reminder.reminder_type == ReminderType.HEARING:
                source_id = str(metadata.get("source_id", "")).strip()
                if source_id:
                    merge_key = ("hearing", source_id)
                else:
                    merge_key = (
                        "hearing_fallback",
                        due_local.strftime("%Y-%m-%d %H:%M"),
                        reminder.content.strip(),
                        courtroom,
                        reminder.case_id or 0,
                        reminder.contract_id or 0,
                        reminder.case_log_id or 0,
                    )

            if merge_key is not None:
                day_index = hearing_merged_index.setdefault(due_local.day, {})
                existing = day_index.get(merge_key)
                if existing is not None:
                    existing_lawyers = existing.get("lawyer_names", [])
                    if isinstance(existing_lawyers, list) and lawyer_name and lawyer_name not in existing_lawyers:
                        existing_lawyers.append(lawyer_name)
                        existing["lawyer_name"] = "、".join(existing_lawyers)
                    continue

            event = {
                "id": reminder.id,
                "time": due_local.strftime("%H:%M"),
                "due_display": due_local.strftime("%Y-%m-%d %H:%M"),
                "title": reminder.content,
                "type_label": type_label,
                "target_type": target_type,
                "target_name": target_name,
                "courtroom": courtroom,
                "location": location,
                "lawyer_name": lawyer_name,
                "lawyer_names": [lawyer_name] if lawyer_name else [],
                "url": reverse(change_url_name, args=[reminder.id]),
                "is_overdue": reminder.due_at < now,
            }
            events_by_day.setdefault(due_local.day, []).append(event)

            if merge_key is not None:
                hearing_merged_index.setdefault(due_local.day, {})[merge_key] = event

        return events_by_day

    def _build_calendar_weeks(
        self, *, year: int, month: int, events_by_day: dict[int, list[dict[str, object]]]
    ) -> list[list[dict[str, object]]]:
        month_calendar = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
        today = timezone.localdate()
        weeks: list[list[dict[str, object]]] = []

        for week_dates in month_calendar:
            week_cells: list[dict[str, object]] = []
            for day_date in week_dates:
                in_month = day_date.month == month
                week_cells.append(
                    {
                        "date": day_date,
                        "day": day_date.day,
                        "in_month": in_month,
                        "is_today": day_date == today,
                        "items": events_by_day.get(day_date.day, []) if in_month else [],
                    }
                )
            weeks.append(week_cells)
        return weeks

    def _build_calendar_url(self, year: int, month: int, preserve_filters: dict[str, str]) -> str:
        query_dict = {"year": year, "month": month, **preserve_filters}
        return f"{reverse('admin:reminders_reminder_calendar')}?{urlencode(query_dict)}"
