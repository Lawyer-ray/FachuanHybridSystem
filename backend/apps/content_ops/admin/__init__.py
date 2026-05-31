from typing import Any

from django.contrib import admin
from django.db.models import Q
from django.db.models.query import QuerySet

from apps.content_ops.models import ContentTask, GeneratedArticle, PodcastEpisode

_WEIKE_SITE_FILTER = (
    Q(site_name__icontains="wkxx")
    | Q(site_name__iexact="wk")
    | Q(site_name__icontains="weike")
    | Q(site_name__icontains="wkinfo")
    | Q(url__icontains="wkinfo.com.cn")
)

@admin.register(ContentTask)
class ContentTaskAdmin(admin.ModelAdmin):
    list_display = ["id", "mode", "keyword", "voice", "status", "progress", "created_at"]
    list_filter = ["mode", "status", "voice"]
    search_fields = ["keyword", "source_title", "case_summary"]
    readonly_fields = ["q_task_id", "started_at", "finished_at", "created_at", "updated_at"]

    def get_form(self, request, obj: ContentTask | None = None, **kwargs: Any):  # type: ignore[override]
        form = super().get_form(request, obj, **kwargs)
        self._configure_credential_field(request=request, form=form)
        return form

    def _configure_credential_field(self, *, request: Any, form: type) -> None:
        credential_field = form.base_fields.get("credential")
        if credential_field is None:
            return

        queryset = self._get_weike_credential_queryset(request)
        credential_field.queryset = queryset

        count = queryset.count()
        if count <= 0:
            credential_field.help_text = "没有可用的法律检索网站账号，请先在「账号密码」中创建。"
            return

        if count == 1:
            only = queryset.first()
            if only is not None:
                credential_field.initial = only.id
            from django import forms

            credential_field.widget = forms.HiddenInput()
            return

        credential_field.help_text = "仅显示法律检索网站账号。"

    @staticmethod
    def _get_weike_credential_queryset(request) -> QuerySet[Any, Any]:
        from apps.organization.models import AccountCredential

        qs = AccountCredential.objects.select_related("lawyer", "lawyer__law_firm").filter(_WEIKE_SITE_FILTER)
        user = getattr(request, "user", None)
        if not getattr(user, "is_superuser", False):
            is_lawyer_user = getattr(getattr(user, "_meta", None), "label_lower", "") == "organization.lawyer"
            if is_lawyer_user:
                qs = qs.filter(lawyer__law_firm_id=getattr(user, "law_firm_id", None))
            else:
                return qs.none()
        return qs.order_by("-last_login_success_at", "-login_success_count", "login_failure_count", "-id")

@admin.register(GeneratedArticle)
class GeneratedArticleAdmin(admin.ModelAdmin):
    list_display = ["id", "task", "title", "review_status", "llm_model", "created_at"]
    list_filter = ["review_status"]
    search_fields = ["title", "content"]
    readonly_fields = ["llm_model", "token_usage", "created_at", "updated_at"]

@admin.register(PodcastEpisode)
class PodcastEpisodeAdmin(admin.ModelAdmin):
    list_display = ["id", "task", "voice", "review_status", "duration_seconds", "file_size_bytes", "created_at"]
    list_filter = ["review_status", "voice"]
    readonly_fields = ["audio_file", "duration_seconds", "file_size_bytes", "created_at", "updated_at"]
