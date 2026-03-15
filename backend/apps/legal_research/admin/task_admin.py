from __future__ import annotations

import logging
from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.contrib import messages
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from django.utils import timezone

from apps.core.interfaces import ServiceLocator
from apps.core.llm.config import LLMConfig
from apps.core.llm.model_list_service import ModelListService
from apps.legal_research.models import LegalResearchResult, LegalResearchTask
from apps.legal_research.models.task import LegalResearchTaskStatus
from apps.legal_research.services.feedback_loop import LegalResearchFeedbackLoopService
from apps.legal_research.services.keywords import KEYWORD_INPUT_HELP_TEXT, normalize_keyword_query
from apps.legal_research.services.llm_preflight import verify_siliconflow_connectivity
from apps.legal_research.services.task_service import LegalResearchTaskService
from apps.legal_research.services.task_state_sync import sync_failed_queue_state
from apps.organization.models import AccountCredential, Lawyer

logger = logging.getLogger(__name__)


@admin.register(LegalResearchTask)
class LegalResearchTaskAdmin(admin.ModelAdmin[LegalResearchTask]):
    WEIKE_SITE_FILTER = (
        Q(site_name__icontains="wkxx")
        | Q(site_name__iexact="wk")
        | Q(site_name__icontains="weike")
        | Q(site_name__icontains="wkinfo")
        | Q(url__icontains="wkinfo.com.cn")
    )

    list_display: ClassVar[list[str]] = [
        "id",
        "keyword",
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
        "target_count",
        "max_candidates",
        "min_similarity_score",
        "status",
        "progress",
        "scanned_count",
        "matched_count",
        "candidate_count",
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
        "case_summary",
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
        if obj.status == LegalResearchTaskStatus.FAILED:
            return [name for name in self.readonly_fields if name != "llm_model"]
        return self.readonly_fields

    def get_fields(self, request, obj: LegalResearchTask | None = None) -> list[str]:  # type: ignore[override]
        if obj is None:
            fields = list(self.add_fields)
            if self._get_weike_credential_queryset(request).count() == 1:
                fields.remove("credential")
            return fields
        return self.readonly_fields

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
        self._configure_scan_threshold_fields(form=form)

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

        setattr(form, "clean_keyword", clean_keyword)

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

    def _get_weike_credential_queryset(self, request) -> QuerySet[AccountCredential, AccountCredential]:
        qs = AccountCredential.objects.select_related("lawyer", "lawyer__law_firm").filter(self.WEIKE_SITE_FILTER)
        user = getattr(request, "user", None)
        if not getattr(user, "is_superuser", False):
            if isinstance(user, Lawyer):
                qs = qs.filter(lawyer__law_firm_id=user.law_firm_id)
            else:
                return qs.none()
        return qs.order_by("-last_login_success_at", "-login_success_count", "login_failure_count", "-id")

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
            LegalResearchResult.objects.filter(task=obj, pdf_file__isnull=False).exclude(pdf_file="").order_by("rank", "created_at")
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

    @admin.display(description="任务控制")
    def cancel_task_button(self, obj: LegalResearchTask) -> str:
        if not self._is_cancellable_status(obj.status):
            return "—"

        cancel_url = reverse("admin:legal_research_legalresearchtask_cancel", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" '
            'onclick="return confirm(\'确定取消这个任务吗？已执行部分将保留，后续扫描会停止。\')">'
            "取消任务</a>",
            cancel_url,
        )

    @admin.display(description="候选池提示")
    def candidate_pool_hint(self, obj: LegalResearchTask) -> str:
        if obj.status != LegalResearchTaskStatus.COMPLETED:
            return "—"

        if obj.matched_count >= obj.target_count:
            return format_html(
                '<span style="color:#389e0d;font-weight:600;">'
                "已达到目标案例数（{}/{}），任务已提前结束。"
                "</span>",
                obj.matched_count,
                obj.target_count,
            )

        if obj.candidate_count <= 0:
            return format_html(
                '<span style="color:#d4380d;font-weight:600;">'
                "当前关键词未检索到候选案例，请放宽关键词后重试。"
                "</span>"
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
                '<span style="color:#1677ff;font-weight:600;">'
                "已扫描到最大上限 {}，可按需提高“最大扫描案例数”。"
                "</span>",
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

        if obj.created_by_id is None and isinstance(request.user, Lawyer):
            obj.created_by = request.user

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
