from __future__ import annotations

import re
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.legal_research.models import LegalResearchResult, LegalResearchTask
from apps.legal_research.services.sources import CaseDetail


class ExecutorResultPersistenceMixin:
    CONTENT_EXCERPT_MAX_CHARS = 12000

    @staticmethod
    @transaction.atomic
    def _save_result(
        *,
        task: LegalResearchTask,
        detail: CaseDetail,
        similarity: Any,
        rank: int,
        pdf: tuple[bytes, str],
        coarse_score: float | None = None,
        coarse_reason: str = "",
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        pdf_bytes, filename = pdf
        metadata: dict[str, Any] = {
            "search_id": detail.search_id,
            "module": detail.module,
            "source_doc_id_raw": detail.doc_id_raw,
        }
        if coarse_score is not None:
            metadata["coarse_score"] = round(float(coarse_score), 4)
        if coarse_reason:
            metadata["coarse_reason"] = str(coarse_reason)[:240]
        if extra_metadata:
            metadata.update(extra_metadata)
        content_excerpt = ExecutorResultPersistenceMixin._build_content_excerpt(detail.content_text)
        if content_excerpt:
            metadata["content_excerpt"] = content_excerpt

        result, _ = LegalResearchResult.objects.get_or_create(
            task=task,
            source_doc_id=detail.doc_id_unquoted,
            defaults={
                "rank": rank,
                "source_url": detail.detail_url,
                "title": detail.title,
                "court_text": detail.court_text,
                "document_number": detail.document_number,
                "judgment_date": detail.judgment_date,
                "case_digest": detail.case_digest,
                "similarity_score": similarity.score,
                "match_reason": similarity.reason,
                "metadata": metadata,
            },
        )

        if not result.pdf_file:
            safe_filename = ExecutorResultPersistenceMixin._sanitize_pdf_filename(
                filename, fallback=detail.doc_id_unquoted
            )
            result.pdf_file.save(safe_filename, ContentFile(pdf_bytes), save=False)

        result.rank = rank
        result.source_url = detail.detail_url
        result.title = detail.title
        result.court_text = detail.court_text
        result.document_number = detail.document_number
        result.judgment_date = detail.judgment_date
        result.case_digest = detail.case_digest
        result.similarity_score = similarity.score
        result.match_reason = similarity.reason
        existing_metadata = dict(result.metadata or {})
        existing_metadata.update(metadata)
        result.metadata = existing_metadata
        result.updated_at = timezone.now()
        result.save()

    @staticmethod
    def _extract_similarity_metadata(*, similarity: Any) -> dict[str, Any]:
        metadata = getattr(similarity, "metadata", None)
        if not isinstance(metadata, dict) or not metadata:
            return {}
        normalized: dict[str, Any] = {}
        for key, value in metadata.items():
            field = str(key or "").strip()
            if not field:
                continue
            normalized[field] = value
        if not normalized:
            return {}
        return {"similarity_structured": normalized}

    @staticmethod
    def _build_content_excerpt(content_text: str) -> str:
        text = str(content_text or "").strip()
        if not text:
            return ""
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
        return normalized[: ExecutorResultPersistenceMixin.CONTENT_EXCERPT_MAX_CHARS]

    @staticmethod
    def _sanitize_pdf_filename(filename: str, *, fallback: str) -> str:
        name = (filename or "").replace("\\", "/").split("/")[-1].strip()
        if not name.lower().endswith(".pdf"):
            name = f"{name}.pdf"

        stem = name[:-4]
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
        if not stem:
            stem = re.sub(r"[^A-Za-z0-9._-]+", "_", fallback or "case").strip("._") or "case"

        # 上传路径里已包含 task_id/result_id，文件名需要显著收敛以避免超长。
        return f"{stem[:120]}.pdf"
