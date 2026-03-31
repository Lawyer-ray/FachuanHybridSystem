from __future__ import annotations

import re
import zipfile
from io import BytesIO
from typing import Any

from django.http import FileResponse, Http404, HttpResponse
from django.utils.translation import gettext_lazy as _
from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth
from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.legal_research.schemas import (
    AgentSearchRequestV1,
    AgentSearchResponseV1,
    LegalResearchCreateOut,
    LegalResearchResultOut,
    LegalResearchTaskCreateIn,
    LegalResearchTaskOut,
)
from apps.legal_research.services.capability_mcp_wrapper import LegalResearchCapabilityMcpWrapper
from apps.legal_research.services.capability_service import LegalResearchCapabilityService
from apps.legal_research.services.task_service import LegalResearchTaskService

router = Router(tags=["案例检索"], auth=JWTOrSessionAuth())


def _get_service() -> LegalResearchTaskService:
    return LegalResearchTaskService()


def _get_capability_service() -> LegalResearchCapabilityService:
    return LegalResearchCapabilityService()


def _get_capability_mcp_wrapper() -> LegalResearchCapabilityMcpWrapper:
    return LegalResearchCapabilityMcpWrapper()


def _serialize_task(task: Any) -> LegalResearchTaskOut:
    return LegalResearchTaskOut(
        id=task.id,
        credential_id=task.credential_id,
        keyword=task.keyword,
        case_summary=task.case_summary,
        search_mode=task.search_mode,
        target_count=task.target_count,
        max_candidates=task.max_candidates,
        min_similarity_score=task.min_similarity_score,
        status=task.status,
        progress=task.progress,
        scanned_count=task.scanned_count,
        matched_count=task.matched_count,
        candidate_count=task.candidate_count,
        message=task.message or "",
        error=task.error or "",
        llm_backend=task.llm_backend,
        llm_model=task.llm_model or "",
        q_task_id=task.q_task_id or "",
        started_at=task.started_at,
        finished_at=task.finished_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _serialize_result(result: Any) -> LegalResearchResultOut:
    return LegalResearchResultOut(
        id=result.id,
        task_id=result.task_id,
        rank=result.rank,
        source_doc_id=result.source_doc_id,
        source_url=result.source_url or "",
        title=result.title or "",
        court_text=result.court_text or "",
        document_number=result.document_number or "",
        judgment_date=result.judgment_date or "",
        case_digest=result.case_digest or "",
        similarity_score=result.similarity_score,
        match_reason=result.match_reason or "",
        has_pdf=bool(result.pdf_file),
        created_at=result.created_at,
    )


@router.post("/tasks", response=LegalResearchCreateOut)
def create_task(request: Any, payload: LegalResearchTaskCreateIn) -> LegalResearchCreateOut:
    task = _get_service().create_task(payload=payload, user=getattr(request, "user", None))
    return LegalResearchCreateOut(task_id=task.id, status=task.status)


@router.post("/capability/search", response=AgentSearchResponseV1)
def capability_search(request: Any, payload: AgentSearchRequestV1) -> AgentSearchResponseV1:
    headers = getattr(request, "headers", {}) or {}
    idempotency_key = str(headers.get("Idempotency-Key", "") or "").strip()
    return _get_capability_service().search(
        payload=payload,
        user=getattr(request, "user", None),
        idempotency_key=idempotency_key,
    )


@router.post("/capability/search/mcp", response=dict[str, Any])
def capability_search_mcp(request: Any, payload: AgentSearchRequestV1) -> dict[str, Any]:
    headers = getattr(request, "headers", {}) or {}
    idempotency_key = str(headers.get("Idempotency-Key", "") or "").strip()
    return _get_capability_mcp_wrapper().search(
        payload=payload,
        user=getattr(request, "user", None),
        idempotency_key=idempotency_key,
    )


@router.get("/tasks/{task_id}", response=LegalResearchTaskOut)
def get_task(request: Any, task_id: int) -> LegalResearchTaskOut:
    task = _get_service().get_task(task_id=task_id, user=getattr(request, "user", None))
    return _serialize_task(task)


@router.get("/tasks/{task_id}/results", response=list[LegalResearchResultOut])
def list_results(request: Any, task_id: int) -> list[LegalResearchResultOut]:
    results = _get_service().list_results(task_id=task_id, user=getattr(request, "user", None))
    return [_serialize_result(x) for x in results]


@router.get("/tasks/{task_id}/results/{result_id}/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_single_result(request: Any, task_id: int, result_id: int) -> FileResponse:
    result = _get_service().get_result(task_id=task_id, result_id=result_id, user=getattr(request, "user", None))
    if not result.pdf_file:
        raise Http404(_("结果PDF不存在"))

    filename = result.pdf_file.name.split("/")[-1]
    return FileResponse(result.pdf_file.open("rb"), as_attachment=True, filename=filename)


@router.get("/tasks/{task_id}/results/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_all_results(request: Any, task_id: int) -> HttpResponse:
    service = _get_service()
    service.ensure_task_ready_for_download(task_id=task_id, user=getattr(request, "user", None))
    results = service.list_results(task_id=task_id, user=getattr(request, "user", None))

    if not results:
        raise Http404(_("任务暂无可下载结果"))

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        has_file = False
        for result in results:
            if not result.pdf_file:
                continue
            has_file = True
            raw_title = result.title or f"case_{result.rank}"
            safe_title = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", raw_title).strip("_") or f"case_{result.rank}"
            entry_name = f"{result.rank:02d}_{safe_title}.pdf"
            with result.pdf_file.open("rb") as fp:
                zip_file.writestr(entry_name, fp.read())

    if buffer.tell() == 0 or not has_file:
        raise Http404(_("任务暂无可下载PDF"))

    filename = f"legal_research_{task_id}.zip"
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
