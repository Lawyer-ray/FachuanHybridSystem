from __future__ import annotations

import json
import logging
from typing import Any, ClassVar

from django import forms
from django.contrib import admin, messages
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from apps.core.interfaces import ServiceLocator
from apps.core.llm.config import LLMConfig
from apps.core.llm.model_list_service import ModelListService
from apps.legal_research.models import LegalResearchResult, LegalResearchTask, LegalResearchTaskEvent
from apps.legal_research.models.task import LegalResearchSearchMode, LegalResearchTaskStatus
from apps.legal_research.services.feedback_loop import LegalResearchFeedbackLoopService
from apps.legal_research.services.keywords import KEYWORD_INPUT_HELP_TEXT, normalize_keyword_query
from apps.legal_research.services.llm_preflight import verify_siliconflow_connectivity
from apps.legal_research.services.task_service import LegalResearchTaskService
from apps.legal_research.services.task_state_sync import sync_failed_queue_state

logger = logging.getLogger(__name__)


@admin.register(LegalResearchTask)
class LegalResearchTaskAdmin(admin.ModelAdmin[LegalResearchTask]):
    change_form_template = "admin/legal_research/legalresearchtask/change_form.html"
    WEIKE_SITE_FILTER = (
        Q(site_name__icontains="wkxx")
        | Q(site_name__iexact="wk")
        | Q(site_name__icontains="weike")
        | Q(site_name__icontains="wkinfo")
        | Q(url__icontains="wkinfo.com.cn")
    )
    PRIVATE_API_VISUAL_FIELD_PREFIX = "private_api_"

    list_display: ClassVar[list[str]] = [
        "id",
        "keyword",
        "search_mode",
        "credential",
        "status",
        "progress",
        "scanned_count",
        "matched_count",
        "created_at",
    ]
    list_filter: ClassVar[list[str]] = ["status", "llm_backend", "created_at"]
    search_fields: ClassVar[tuple[str, ...]] = (
        "id",
        "keyword",
        "credential__account",
        "credential__site_name",
    )
    readonly_fields: ClassVar[list[str]] = [
        "id",
        "created_by",
        "credential",
        "source",
        "keyword",
        "case_summary",
        "search_mode",
        "target_count",
        "max_candidates",
        "min_similarity_score",
        "status",
        "progress",
        "scanned_count",
        "matched_count",
        "candidate_count",
        "private_api_stage_metrics",
        "private_api_event_timeline",
        "private_api_event_panel",
        "candidate_pool_hint",
        "cancel_task_button",
        "result_attachments",
        "message",
        "error",
        "llm_backend",
        "llm_model",
        "q_task_id",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    ]
    ordering: ClassVar[list[str]] = ["-created_at"]
    add_fields: ClassVar[list[str]] = [
        "credential",
        "keyword",
        "advanced_query",
        "court_filter",
        "cause_of_action_filter",
        "date_from",
        "date_to",
        "case_summary",
        "search_mode",
        "target_count",
        "max_candidates",
        "min_similarity_score",
        "llm_model",
    ]
    actions: ClassVar[list[str]] = ["mark_as_missed_case_feedback"]

    def get_object(self, request, object_id, from_field=None):  # type: ignore[override]
        obj = super().get_object(request, object_id, from_field=from_field)
        if obj is None:
            return None
        self._sync_failed_queue_state(obj=obj)
        return obj

    def get_readonly_fields(self, request, obj: LegalResearchTask | None = None) -> list[str]:  # type: ignore[override]
        if obj is None:
            return []
        readonly_fields = list(self.readonly_fields)
        if obj.status == LegalResearchTaskStatus.FAILED:
            readonly_fields = [name for name in readonly_fields if name != "llm_model"]
        return self._filter_private_api_visual_fields(readonly_fields, obj=obj)

    def get_fields(self, request, obj: LegalResearchTask | None = None) -> list[str]:  # type: ignore[override]
        if obj is None:
            fields = list(self.add_fields)
            if self._get_weike_credential_queryset(request).count() == 1:
                fields.remove("credential")
            return fields
        return self._filter_private_api_visual_fields(list(self.readonly_fields), obj=obj)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        extra = dict(context or {})
        extra["private_weike_api_enabled"] = self._should_show_private_api_visuals(obj=obj)
        return super().render_change_form(
            request=request,
            context=extra,
            add=add,
            change=change,
            form_url=form_url,
            obj=obj,
        )

    def get_form(self, request, obj: LegalResearchTask | None = None, **kwargs):  # type: ignore[override]
        form = super().get_form(request, obj, **kwargs)
        if obj is not None:
            if obj.status == LegalResearchTaskStatus.FAILED:
                model_field = form.base_fields.get("llm_model")
                if model_field is not None:
                    choices = self._build_llm_model_choices()
                    model_field.widget = forms.Select(choices=choices)
                    model_field.help_text = "失败任务可修改模型，保存后将自动重启任务。"
            return form

        self._configure_credential_field(request=request, form=form)
        self._configure_keyword_field(form=form)
        self._configure_advanced_query_field(form=form)
        self._configure_filter_fields(form=form)
        self._configure_search_mode_field(form=form)
        self._configure_scan_threshold_fields(form=form)
        self._attach_search_mode_cleaner(form)

        model_field = form.base_fields.get("llm_model")
        if model_field is None:
            self._attach_keyword_cleaner(form)
            return form

        choices = self._build_llm_model_choices()
        model_field.widget = forms.Select(choices=choices)
        model_field.initial = choices[0][0] if choices else LLMConfig.get_default_model()
        model_field.help_text = "选择用于案例相似度评估的硅基流动模型。"
        self._attach_keyword_cleaner(form)
        return form

    def get_urls(self):  # type: ignore[override]
        urls = super().get_urls()
        opts = self.model._meta
        custom_urls = [
            path(
                "<path:object_id>/cancel/",
                self.admin_site.admin_view(self.cancel_task_view),
                name=f"{opts.app_label}_{opts.model_name}_cancel",
            )
        ]
        return custom_urls + urls

    def cancel_task_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        obj = self.get_object(request, object_id)
        if obj is None:
            messages.error(request, "任务不存在")
            return HttpResponseRedirect(reverse("admin:legal_research_legalresearchtask_changelist"))

        if not self.has_change_permission(request, obj):
            messages.error(request, "无权限取消该任务")
            return HttpResponseRedirect(reverse("admin:legal_research_legalresearchtask_change", args=[obj.pk]))

        if not self._is_cancellable_status(obj.status):
            messages.warning(request, f"当前状态为“{obj.get_status_display()}”，无需取消。")
            return HttpResponseRedirect(reverse("admin:legal_research_legalresearchtask_change", args=[obj.pk]))

        cancel_info = self._cancel_task(obj=obj)
        queue_deleted = int(cancel_info.get("queue_deleted", 0))
        running = bool(cancel_info.get("running", False))

        msg = f"任务已取消，队列撤销 {queue_deleted} 条。"
        if running:
            msg += " 任务正在运行，将在下一轮取消检查时停止。"
        messages.success(request, msg)
        return HttpResponseRedirect(reverse("admin:legal_research_legalresearchtask_change", args=[obj.pk]))

    @staticmethod
    def _is_cancellable_status(status: str) -> bool:
        return status in {
            LegalResearchTaskStatus.PENDING,
            LegalResearchTaskStatus.QUEUED,
            LegalResearchTaskStatus.RUNNING,
        }

    @staticmethod
    def _attach_keyword_cleaner(form: type[forms.ModelForm]) -> None:
        def clean_keyword(self) -> str:
            raw = str(self.cleaned_data.get("keyword", "") or "")
            normalized = normalize_keyword_query(raw)
            if not normalized:
                raise forms.ValidationError("请至少输入一个有效检索关键词")
            return normalized

        form.clean_keyword = clean_keyword

    @staticmethod
    def _configure_advanced_query_field(*, form: type[forms.ModelForm]) -> None:
        field = form.base_fields.get("advanced_query")
        if field is None:
            return
        field.required = False
        field.help_text = (
            "可选。高级检索条件，JSON 数组格式，留空则使用上方关键词做全文检索。<br>"
            "每项格式：<code>{\"field\": \"字段名\", \"keyword\": \"关键词\", \"op\": \"AND\"}</code><br>"
            "字段名可选：<code>fullText</code>（全文）、<code>title</code>（标题）、"
            "<code>courtOpinion</code>（本院认为）、<code>judgmentResult</code>（裁判结果）、"
            "<code>disputeFocus</code>（争议焦点）、<code>causeOfAction</code>（案由）、"
            "<code>caseNumber</code>（案号）<br>"
            "示例：<code>[{\"field\":\"courtOpinion\",\"keyword\":\"逾期利息\",\"op\":\"AND\"},"
            "{\"field\":\"title\",\"keyword\":\"借款合同\",\"op\":\"AND\"}]</code>"
        )
        field.widget = forms.Textarea(attrs={"rows": 4, "style": "font-family:monospace;font-size:12px;"})

    @staticmethod
    def _configure_filter_fields(*, form: type[forms.ModelForm]) -> None:
        court_field = form.base_fields.get("court_filter")
        if court_field is not None:
            court_field.required = False
            court_field.help_text = "可选。按法院名称精确筛选，例如：北京市第一中级人民法院"
            if hasattr(court_field.widget, "attrs"):
                court_field.widget.attrs["placeholder"] = "例如：北京市第一中级人民法院（留空不限）"

        cause_field = form.base_fields.get("cause_of_action_filter")
        if cause_field is not None:
            cause_field.required = False
            cause_field.help_text = "可选。按案由精确筛选，例如：民间借贷纠纷"
            if hasattr(cause_field.widget, "attrs"):
                cause_field.widget.attrs["placeholder"] = "例如：民间借贷纠纷（留空不限）"

        date_from_field = form.base_fields.get("date_from")
        if date_from_field is not None:
            date_from_field.required = False
            date_from_field.help_text = "可选。裁判日期起，格式：YYYY-MM-DD"
            if hasattr(date_from_field.widget, "attrs"):
                date_from_field.widget.attrs["placeholder"] = "例如：2020-01-01"

        date_to_field = form.base_fields.get("date_to")
        if date_to_field is not None:
            date_to_field.required = False
            date_to_field.help_text = "可选。裁判日期止，格式：YYYY-MM-DD"
            if hasattr(date_to_field.widget, "attrs"):
                date_to_field.widget.attrs["placeholder"] = "例如：2024-12-31"

    @staticmethod
    def _configure_search_field_field(*, form: type[forms.ModelForm]) -> None:
        pass  # 已废弃，保留避免调用报错

    @staticmethod
    def _configure_keyword_field(*, form: type[forms.ModelForm]) -> None:
        keyword_field = form.base_fields.get("keyword")
        if keyword_field is None:
            return
        keyword_field.help_text = KEYWORD_INPUT_HELP_TEXT
        if hasattr(keyword_field.widget, "attrs"):
            keyword_field.widget.attrs["placeholder"] = "例如：借款合同 逾期利息 担保责任"

    @staticmethod
    def _configure_scan_threshold_fields(*, form: type[forms.ModelForm]) -> None:
        max_candidates_field = form.base_fields.get("max_candidates")
        if max_candidates_field is not None:
            max_candidates_field.help_text = "最多扫描多少篇候选案例。默认 100。"
            if hasattr(max_candidates_field.widget, "attrs"):
                max_candidates_field.widget.attrs["placeholder"] = "默认 100"

        min_similarity_field = form.base_fields.get("min_similarity_score")
        if min_similarity_field is not None:
            min_similarity_field.help_text = "最低相似度阈值（0~1）。默认 0.9。"
            if hasattr(min_similarity_field.widget, "attrs"):
                min_similarity_field.widget.attrs["placeholder"] = "默认 0.9"

    @staticmethod
    def _configure_search_mode_field(*, form: type[forms.ModelForm]) -> None:
        search_mode_field = form.base_fields.get("search_mode")
        if search_mode_field is None:
            return
        search_mode_field.required = False
        search_mode_field.initial = LegalResearchSearchMode.EXPANDED
        search_mode_field.help_text = (
            "默认“扩展检索”：会自动扩展检索式（同义词、意图、反馈）。切换为“单检索”后仅使用原始关键词检索。"
        )

    @staticmethod
    def _attach_search_mode_cleaner(form: type[forms.ModelForm]) -> None:
        def clean_search_mode(self) -> str:
            raw = str(self.cleaned_data.get("search_mode", "") or "").strip().lower()
            return raw or LegalResearchSearchMode.EXPANDED

        form.clean_search_mode = clean_search_mode

    def _configure_credential_field(self, *, request, form: type[forms.ModelForm]) -> None:
        credential_field = form.base_fields.get("credential")
        if credential_field is None:
            return

        queryset = self._get_weike_credential_queryset(request)
        credential_field.queryset = queryset

        count = queryset.count()
        if count <= 0:
            credential_field.help_text = "没有可用的wkxx账号，请先在“账号密码”中创建。"
            return

        if count == 1:
            only = queryset.first()
            if only is not None:
                credential_field.initial = only.id
            credential_field.widget = forms.HiddenInput()
            return

        credential_field.help_text = "仅显示wkxx账号。"

    @staticmethod
    def _get_credential_model() -> Any:
        credential_field = LegalResearchTask._meta.get_field("credential")
        return credential_field.remote_field.model

    def _get_weike_credential_queryset(self, request) -> QuerySet[Any, Any]:
        credential_model = self._get_credential_model()
        qs = credential_model.objects.select_related("lawyer", "lawyer__law_firm").filter(self.WEIKE_SITE_FILTER)
        user = getattr(request, "user", None)
        if not getattr(user, "is_superuser", False):
            is_lawyer_user = getattr(getattr(user, "_meta", None), "label_lower", "") == "organization.lawyer"
            if is_lawyer_user:
                qs = qs.filter(lawyer__law_firm_id=getattr(user, "law_firm_id", None))
            else:
                return qs.none()
        return qs.order_by("-last_login_success_at", "-login_success_count", "login_failure_count", "-id")

    @classmethod
    def _filter_private_api_visual_fields(cls, fields: list[str], *, obj: LegalResearchTask | None = None) -> list[str]:
        if cls._should_show_private_api_visuals(obj=obj):
            return fields
        return [name for name in fields if not str(name).startswith(cls.PRIVATE_API_VISUAL_FIELD_PREFIX)]

    @classmethod
    def _should_show_private_api_visuals(cls, *, obj: LegalResearchTask | None = None) -> bool:
        if obj is not None and str(getattr(obj, "source", "") or "").strip().lower() != "weike":
            return False
        return cls._private_weike_api_enabled()

    @staticmethod
    def _private_weike_api_enabled() -> bool:
        try:
            from apps.legal_research.services.sources.weike import api_optional

            return api_optional.get_private_weike_api() is not None
        except Exception:
            return False

    @staticmethod
    def _build_llm_model_choices() -> list[tuple[str, str]]:
        choices: list[tuple[str, str]] = []
        seen: set[str] = set()

        def append_choice(model_id: str, *, label: str | None = None) -> None:
            value = model_id.strip()
            if not value or value in seen:
                return
            seen.add(value)
            choices.append((value, label or value))

        default_model = LLMConfig.get_default_model().strip()
        if default_model:
            append_choice(default_model, label=f"{default_model}（默认）")

        try:
            models = ModelListService().get_models()
        except Exception:
            logger.exception("加载硅基流动模型列表失败")
            models = []

        for item in models:
            model_id = str(item.get("id", "")).strip()
            model_name = str(item.get("name", "")).strip()
            if model_name and model_name != model_id:
                append_choice(model_id, label=f"{model_name} ({model_id})")
            else:
                append_choice(model_id)

        if not choices:
            append_choice(default_model or "Qwen/Qwen2.5-7B-Instruct")
        return choices

    @admin.display(description="案例附件")
    def result_attachments(self, obj: LegalResearchTask) -> str:
        results = list(
            LegalResearchResult.objects.filter(task=obj, pdf_file__isnull=False)
            .exclude(pdf_file="")
            .order_by("rank", "created_at")
        )
        if not results:
            return "—"

        rows: list[tuple[str, str]] = []
        for result in results:
            title = (result.title or f"案例{result.rank}")[:80]
            label = f"#{result.rank} | 相似度 {result.similarity_score:.2f} | {title}"
            url = f"/api/v1/legal-research/tasks/{obj.id}/results/{result.id}/download"
            rows.append((url, label))

        items = format_html_join(
            "",
            '<li style="margin-bottom:4px;"><a href="{}" target="_blank">📎 {}</a></li>',
            rows,
        )
        all_url = f"/api/v1/legal-research/tasks/{obj.id}/results/download"
        return format_html(
            '<div><ul style="margin:0 0 8px 18px;padding:0;">{}</ul>'
            '<a href="{}" target="_blank" style="font-weight:600;">⬇ 下载全部附件(zip)</a></div>',
            items,
            all_url,
        )

    @admin.display(description="API阶段指标")
    def private_api_stage_metrics(self, obj: LegalResearchTask) -> str:
        events = self._get_private_api_events(obj=obj)
        if not events:
            return "—"

        total = len(events)
        search_api_events = [event for event in events if event.stage == "search" and event.source == "api"]
        search_api_success = [event for event in search_api_events if event.success]
        capability_events = [event for event in events if event.interface_name == "capability_direct_call"]
        capability_success = [event for event in capability_events if event.success]
        capability_timeout = [
            event
            for event in capability_events
            if str(event.error_code or "").strip().upper() == "LEGAL_RESEARCH_CAPABILITY_TIMEOUT"
        ]
        capability_busy = [
            event
            for event in capability_events
            if str(event.error_code or "").strip().upper() == "LEGAL_RESEARCH_CAPABILITY_BUSY"
        ]
        capability_degraded = [
            event
            for event in capability_events
            if str(event.error_code or "").strip().upper() == "LEGAL_RESEARCH_CAPABILITY_SOURCE_DEGRADED"
        ]
        dom_fallback_events = [
            event
            for event in events
            if (event.stage == "search" and event.source == "dom") or event.interface_name == "search_fallback_dom"
        ]
        c001009_events = [event for event in events if str(event.error_code or "").strip().upper() == "C_001_009"]
        api_hit_rate = (len(search_api_success) / len(search_api_events) * 100.0) if search_api_events else 0.0
        dom_fallback_rate = (
            (len(dom_fallback_events) / max(1, len(search_api_events) + len(dom_fallback_events)) * 100.0)
            if events
            else 0.0
        )
        error_distribution = self._build_error_distribution(events=events)
        error_html = "、".join(f"{code}:{count}" for code, count in error_distribution) if error_distribution else "无"
        api_hit_rate_text = f"{api_hit_rate:.1f}%"
        dom_fallback_rate_text = f"{dom_fallback_rate:.1f}%"
        capability_success_rate = (
            (len(capability_success) / len(capability_events) * 100.0) if capability_events else 0.0
        )
        capability_success_rate_text = f"{capability_success_rate:.1f}%"

        return format_html(
            "<div>"
            "<div>总事件: <strong>{}</strong></div>"
            "<div>检索API命中率: <strong>{}</strong>（{}/{}）</div>"
            "<div>能力直连成功率: <strong>{}</strong>（{}/{}）</div>"
            "<div>DOM回退率: <strong>{}</strong>（{}）</div>"
            "<div>能力异常: timeout=<strong>{}</strong> / busy=<strong>{}</strong> / degraded=<strong>{}</strong></div>"
            "<div>C_001_009: <strong>{}</strong></div>"
            "<div>错误码分布: {}</div>"
            "</div>",
            total,
            api_hit_rate_text,
            len(search_api_success),
            len(search_api_events),
            capability_success_rate_text,
            len(capability_success),
            len(capability_events),
            dom_fallback_rate_text,
            len(dom_fallback_events),
            len(capability_timeout),
            len(capability_busy),
            len(capability_degraded),
            len(c001009_events),
            error_html,
        )

    @admin.display(description="流程时间线")
    def private_api_event_timeline(self, obj: LegalResearchTask) -> str:
        events = self._get_private_api_events(obj=obj)
        if not events:
            return "—"

        rows: list[tuple[str, str, str, str, str, str]] = []
        for event in events[-60:]:
            created = timezone.localtime(event.created_at).strftime("%H:%M:%S")
            status = str(event.status_code) if event.status_code is not None else "—"
            duration = f"{max(0, int(event.duration_ms or 0))}ms"
            result = "成功" if event.success else "失败"
            rows.append((created, event.stage, event.source, event.interface_name, status, f"{result} / {duration}"))

        items = format_html_join(
            "",
            "<li>{} | {} / {} | {} | HTTP {} | {}</li>",
            rows,
        )
        return format_html('<ul style="margin:0 0 8px 18px;padding:0;">{}</ul>', items)

    @admin.display(description="接口返回可视化")
    def private_api_event_panel(self, obj: LegalResearchTask) -> str:
        events = self._get_private_api_events(obj=obj)
        if not events:
            return "—"

        blocks: list[tuple[str, str, str, str]] = []
        for event in events[-24:]:
            title = (
                f"{timezone.localtime(event.created_at).strftime('%H:%M:%S')} | "
                f"{event.stage}/{event.source} | {event.interface_name}"
            )
            request_preview = self._render_json_preview(event.request_summary)
            response_preview = self._render_json_preview(event.response_summary)
            meta_preview = self._render_json_preview(event.event_metadata)
            blocks.append((title, request_preview, response_preview, meta_preview))

        sections = format_html_join(
            "",
            (
                '<details style="margin-bottom:8px;">'
                "<summary>{}</summary>"
                "<div><strong>Request</strong><pre>{}</pre></div>"
                "<div><strong>Response</strong><pre>{}</pre></div>"
                "<div><strong>Meta</strong><pre>{}</pre></div>"
                "</details>"
            ),
            blocks,
        )
        return format_html("{}", sections)

    @admin.display(description="任务控制")
    def cancel_task_button(self, obj: LegalResearchTask) -> str:
        if not self._is_cancellable_status(obj.status):
            return "—"

        cancel_url = reverse("admin:legal_research_legalresearchtask_cancel", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" '
            "onclick=\"return confirm('确定取消这个任务吗？已执行部分将保留，后续扫描会停止。')\">"
            "取消任务</a>",
            cancel_url,
        )

    @admin.display(description="候选池提示")
    def candidate_pool_hint(self, obj: LegalResearchTask) -> str:
        if obj.status != LegalResearchTaskStatus.COMPLETED:
            return "—"

        if obj.matched_count >= obj.target_count:
            return format_html(
                '<span style="color:#389e0d;font-weight:600;">已达到目标案例数（{}/{}），任务已提前结束。</span>',
                obj.matched_count,
                obj.target_count,
            )

        if obj.candidate_count <= 0:
            return format_html(
                '<span style="color:#d4380d;font-weight:600;">{}</span>',
                "当前关键词未检索到候选案例，请放宽关键词后重试。",
            )

        if obj.scanned_count >= obj.candidate_count and obj.candidate_count < obj.max_candidates:
            return format_html(
                '<span style="color:#d4380d;font-weight:600;">'
                "当前关键词仅检索到 {} 篇候选案例（设置上限为 {}），已全部扫描。"
                "</span>",
                obj.candidate_count,
                obj.max_candidates,
            )

        if obj.scanned_count >= obj.max_candidates:
            return format_html(
                '<span style="color:#1677ff;font-weight:600;">已扫描到最大上限 {}，可按需提高“最大扫描案例数”。</span>',
                obj.max_candidates,
            )

        return "—"

    def _cancel_task(self, *, obj: LegalResearchTask) -> dict[str, Any]:
        cancel_info: dict[str, Any] = {"queue_deleted": 0, "running": False, "finished": False, "exists": False}
        if obj.q_task_id:
            try:
                cancel_info = ServiceLocator.get_task_submission_service().cancel(obj.q_task_id)
            except Exception:
                logger.exception("撤销DjangoQ任务失败", extra={"task_id": str(obj.id), "q_task_id": obj.q_task_id})

        obj.status = LegalResearchTaskStatus.CANCELLED
        obj.message = "任务已取消（用户手动）"
        obj.error = ""
        obj.finished_at = timezone.now()
        obj.save(update_fields=["status", "message", "error", "finished_at", "updated_at"])
        return cancel_info

    @staticmethod
    def _sync_failed_queue_state(*, obj: LegalResearchTask) -> None:
        sync_failed_queue_state(task=obj, failed_message="任务执行失败（队列状态自动回填）")

    @staticmethod
    def _get_private_api_events(*, obj: LegalResearchTask) -> list[LegalResearchTaskEvent]:
        return list(
            LegalResearchTaskEvent.objects.filter(task=obj, stage__in=("search", "detail")).order_by("created_at", "id")
        )

    @staticmethod
    def _build_error_distribution(*, events: list[LegalResearchTaskEvent]) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for event in events:
            code = str(event.error_code or "").strip().upper()
            if not code:
                continue
            counts[code] = counts.get(code, 0) + 1
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:8]

    @staticmethod
    def _render_json_preview(payload: object, *, max_chars: int = 2200) -> str:
        try:
            text = json.dumps(payload or {}, ensure_ascii=False, indent=2)
        except Exception:
            text = str(payload or "")
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3]}..."

    @admin.action(description="标记为漏命中（在线负反馈）")
    def mark_as_missed_case_feedback(self, request: HttpRequest, queryset) -> None:
        service = LegalResearchFeedbackLoopService()
        operator = str(getattr(request.user, "id", "") or "")
        count = 0
        for task in queryset:
            service.record_task_missed_feedback(task=task, operator=operator)
            count += 1
        self.message_user(request, f"已记录 {count} 个任务的漏命中反馈，并完成在线微调。")

    def save_model(self, request, obj: LegalResearchTask, form, change) -> None:  # type: ignore[override]
        task_service = LegalResearchTaskService()

        if change and obj.status != LegalResearchTaskStatus.FAILED:
            super().save_model(request, obj, form, change)
            return

        if change and obj.status == LegalResearchTaskStatus.FAILED:
            super().save_model(request, obj, form, change)
            task_service.reset_task_for_dispatch(
                task=obj,
                pending_message=task_service.RETRY_PENDING_MESSAGE,
                clear_results=True,
            )

            queued = task_service.dispatch_task(
                task=obj,
                queue_failure_message="任务重新提交失败",
                precheck=verify_siliconflow_connectivity,
            )
            if queued:
                messages.success(request, "任务已重新提交到队列。")
            else:
                if obj.message == task_service.PRECHECK_FAILED_MESSAGE:
                    messages.error(request, f"LLM连通性检查失败，任务未启动: {obj.error}")
                else:
                    messages.error(request, f"{obj.message}: {obj.error}")
            return

        obj.keyword = normalize_keyword_query(obj.keyword)
        if obj.credential_id is None:
            default_credential = self._get_weike_credential_queryset(request).first()
            if default_credential is not None:
                obj.credential = default_credential

        is_lawyer_user = getattr(getattr(request.user, "_meta", None), "label_lower", "") == "organization.lawyer"
        if obj.created_by_id is None and is_lawyer_user and getattr(request.user, "id", None) is not None:
            obj.created_by_id = int(request.user.id)

        super().save_model(request, obj, form, change)
        task_service.reset_task_for_dispatch(
            task=obj,
            pending_message=task_service.CREATE_PENDING_MESSAGE,
            clear_results=False,
        )

        queued = task_service.dispatch_task(
            task=obj,
            queue_failure_message="任务提交失败",
            precheck=verify_siliconflow_connectivity,
        )
        if not queued:
            if obj.message == task_service.PRECHECK_FAILED_MESSAGE:
                messages.error(request, f"LLM连通性检查失败，任务未启动: {obj.error}")
            else:
                messages.error(request, f"任务已创建但提交队列失败: {obj.error}")
