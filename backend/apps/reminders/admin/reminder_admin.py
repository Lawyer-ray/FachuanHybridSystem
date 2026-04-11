"""Django admin configuration."""

from __future__ import annotations

import calendar
import json
from datetime import date, datetime
from urllib.parse import urlencode

from django.core.exceptions import ValidationError

from django import forms
from django.contrib import admin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.template.response import TemplateResponse
from django.urls import URLPattern, path, reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _

from django.db.models import Q

from ..models import Reminder, ReminderType


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
class ReminderAdmin(admin.ModelAdmin[Reminder]):
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
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-due_at", "-id")
    date_hierarchy = "due_at"
    list_per_page = 30
    change_list_template = "admin/reminders/reminder/change_list.html"

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
        ]
        return custom_urls + urls

    def changelist_view(
        self, request: HttpRequest, extra_context: dict[str, object] | None = None
    ) -> HttpResponse:
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
            case_log_queryset = case_log_queryset.filter(Q(case__name__icontains=keyword) | Q(content__icontains=keyword))

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
            event = {
                "id": reminder.id,
                "time": due_local.strftime("%H:%M"),
                "due_display": due_local.strftime("%Y-%m-%d %H:%M"),
                "title": reminder.content,
                "type_label": type_label,
                "target_type": target_type,
                "target_name": target_name,
                "courtroom": metadata.get("courtroom", ""),
                "url": reverse(change_url_name, args=[reminder.id]),
                "is_overdue": reminder.due_at < now,
            }
            events_by_day.setdefault(due_local.day, []).append(event)
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
