from __future__ import annotations

from typing import ClassVar

from django.contrib import admin

from apps.legal_research.models import LegalResearchResult


@admin.register(LegalResearchResult)
class LegalResearchResultAdmin(admin.ModelAdmin[LegalResearchResult]):
    list_display: ClassVar[list[str]] = [
        "id",
        "task",
        "rank",
        "title",
        "similarity_score",
        "has_pdf",
        "created_at",
    ]
    list_filter: ClassVar[list[str]] = ["created_at"]
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
