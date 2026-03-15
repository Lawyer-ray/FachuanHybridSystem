from __future__ import annotations

from typing import ClassVar

from django.contrib import admin

from apps.legal_research.models import LegalResearchResult
from apps.legal_research.services.feedback_loop import LegalResearchFeedbackLoopService


@admin.register(LegalResearchResult)
class LegalResearchResultAdmin(admin.ModelAdmin[LegalResearchResult]):
    list_display: ClassVar[list[str]] = [
        "id",
        "task",
        "rank",
        "title",
        "similarity_score",
        "feedback_status",
        "has_pdf",
        "created_at",
    ]
    list_filter: ClassVar[list[str]] = ["created_at"]
    actions: ClassVar[list[str]] = ["mark_as_relevant", "mark_as_false_positive"]
    search_fields: ClassVar[tuple[str, ...]] = (
        "id",
        "task__id",
        "title",
        "source_doc_id",
        "document_number",
    )
    readonly_fields: ClassVar[list[str]] = [
        "id",
        "task",
        "rank",
        "source_doc_id",
        "source_url",
        "title",
        "court_text",
        "document_number",
        "judgment_date",
        "case_digest",
        "similarity_score",
        "match_reason",
        "pdf_file",
        "metadata",
        "created_at",
        "updated_at",
    ]
    ordering: ClassVar[list[str]] = ["-id"]

    @admin.display(description="PDF")
    def has_pdf(self, obj: LegalResearchResult) -> bool:
        return bool(obj.pdf_file)

    has_pdf.boolean = True

    @admin.display(description="人工反馈")
    def feedback_status(self, obj: LegalResearchResult) -> str:
        value = str((obj.metadata or {}).get("human_feedback", "")).strip()
        if value == "relevant":
            return "真实命中"
        if value == "false_positive":
            return "误命中"
        return "—"

    @admin.action(description="标记为真实命中（在线正反馈）")
    def mark_as_relevant(self, request, queryset) -> None:
        service = LegalResearchFeedbackLoopService()
        operator = str(getattr(request.user, "id", "") or "")
        count = 0
        for result in queryset:
            service.record_result_feedback(result=result, is_relevant=True, operator=operator)
            count += 1
        self.message_user(request, f"已标记 {count} 条为真实命中，并完成在线微调。")

    @admin.action(description="标记为误命中（在线负反馈）")
    def mark_as_false_positive(self, request, queryset) -> None:
        service = LegalResearchFeedbackLoopService()
        operator = str(getattr(request.user, "id", "") or "")
        count = 0
        for result in queryset:
            service.record_result_feedback(result=result, is_relevant=False, operator=operator)
            count += 1
        self.message_user(request, f"已标记 {count} 条为误命中，并完成在线微调。")
