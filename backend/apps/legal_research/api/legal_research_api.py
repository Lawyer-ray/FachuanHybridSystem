from __future__ import annotations

import asyncio
import re
import zipfile
from asyncio import get_running_loop
from io import BytesIO
from typing import Any

from asgiref.sync import sync_to_async
from django.http import FileResponse, Http404, HttpResponse
from ninja import Router

from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security.auth import JWTOrSessionAuth
from apps.legal_research.schemas import (
    AgentSearchRequestV1,
    AgentSearchResponseV1,
    LegalResearchCreateOut,
    LegalResearchResultOut,
    LegalResearchTaskCreateIn,
    LegalResearchTaskOut,
)
from apps.legal_research.services.capability.mcp_wrapper import LegalResearchCapabilityMcpWrapper
from apps.legal_research.services.capability.service import LegalResearchCapabilityService
from apps.legal_research.services.task.service import LegalResearchTaskService

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
        llm_scoring_concurrency=getattr(task, "llm_scoring_concurrency", 5) or 5,
        q_task_id=task.q_task_id or "",
        search_url=task.search_url or "",
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
async def create_task(request: Any, payload: LegalResearchTaskCreateIn) -> LegalResearchCreateOut:  # pragma: no cover
    service = _get_service()

    def _do() -> Any:
        task = service.create_task(
            payload=payload, user=getattr(request, "user", None)
        )
        return LegalResearchCreateOut(task_id=task.id, status=task.status)

    return await sync_to_async(_do)()


@router.post("/capability/search", response=AgentSearchResponseV1)
async def capability_search(request: Any, payload: AgentSearchRequestV1) -> AgentSearchResponseV1:  # pragma: no cover
    headers = getattr(request, "headers", {}) or {}
    idempotency_key = str(headers.get("Idempotency-Key", "") or "").strip()
    svc = _get_capability_service()
    return await sync_to_async(svc.search)(
        payload=payload,
        user=getattr(request, "user", None),
        idempotency_key=idempotency_key,
    )


@router.post("/capability/search/mcp", response=dict[str, Any])
async def capability_search_mcp(request: Any, payload: AgentSearchRequestV1) -> dict[str, Any]:  # pragma: no cover
    headers = getattr(request, "headers", {}) or {}
    idempotency_key = str(headers.get("Idempotency-Key", "") or "").strip()
    svc = _get_capability_mcp_wrapper()
    return await sync_to_async(svc.search)(
        payload=payload,
        user=getattr(request, "user", None),
        idempotency_key=idempotency_key,
    )


@router.get("/tasks/{task_id}", response=LegalResearchTaskOut)
async def get_task(request: Any, task_id: int) -> LegalResearchTaskOut:  # pragma: no cover
    service = _get_service()

    def _do() -> Any:
        task = service.get_task(
            task_id=task_id, user=getattr(request, "user", None)
        )
        return _serialize_task(task)

    return await sync_to_async(_do)()


@router.get("/tasks/{task_id}/results", response=list[LegalResearchResultOut])
async def list_results(request: Any, task_id: int) -> list[LegalResearchResultOut]:  # pragma: no cover
    service = _get_service()

    def _do() -> Any:
        results = service.list_results(
            task_id=task_id, user=getattr(request, "user", None)
        )
        return [_serialize_result(x) for x in results]

    return await sync_to_async(_do)()


@router.get("/tasks/{task_id}/results/{result_id}/download")
@rate_limit_from_settings("EXPORT", by_user=True)
async def download_single_result(request: Any, task_id: int, result_id: int) -> FileResponse:  # pragma: no cover
    service = _get_service()

    def _do() -> Any:
        result = service.get_result(
            task_id=task_id, result_id=result_id, user=getattr(request, "user", None)
        )
        if not result.pdf_file:
            raise Http404("结果PDF不存在")

        filename = (result.pdf_file.name or "").split("/")[-1]
        return result.pdf_file.open("rb"), filename

    file_obj, filename = await sync_to_async(_do)()
    return FileResponse(file_obj, as_attachment=True, filename=filename)


@router.get("/tasks/{task_id}/results/download")
@rate_limit_from_settings("EXPORT", by_user=True)
async def download_all_results(request: Any, task_id: int) -> HttpResponse:  # pragma: no cover
    service = _get_service()

    def _do_download_prep() -> Any:
        service.ensure_task_ready_for_download(
            task_id=task_id, user=getattr(request, "user", None)
        )
        results = service.list_results(
            task_id=task_id, user=getattr(request, "user", None)
        )
        if not results:
            raise Http404("任务暂无可下载结果")
        return results

    results = await sync_to_async(_do_download_prep)()

    def _build_zip() -> tuple[bytes, bool]:
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            has_file = False
            for result in results:
                if not result.pdf_file:
                    continue
                has_file = True
                raw_title = result.title or f"case_{result.rank}"
                safe_title = re.sub(r"[^\w一-鿿-]+", "_", raw_title).strip("_") or f"case_{result.rank}"
                entry_name = f"{result.rank:02d}_{safe_title}.pdf"
                with result.pdf_file.open("rb") as fp:
                    zip_file.writestr(entry_name, fp.read())
        return buffer.getvalue(), has_file

    zip_bytes, has_file = await asyncio.to_thread(_build_zip)

    if not has_file:
        raise Http404("任务暂无可下载PDF")

    filename = f"legal_research_{task_id}.zip"
    response = HttpResponse(zip_bytes, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ──────────────────────────────────────────────────────────────
# 法规引用核查
# ──────────────────────────────────────────────────────────────


@router.post("/law-verification/check", response=dict[str, Any])
async def check_law_references(request: Any, payload: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
    """核查文档中的法规引用.

    请求: {"text": "文档全文", "credential_id": 6}
    响应: {"references": [...], "total": N}
    """

    def _do_check() -> dict[str, Any]:
        text = str(payload.get("text") or "").strip()
        credential_id = int(payload.get("credential_id") or 0)

        if not text:
            return {"error": "text 不能为空", "references": [], "total": 0}

        # 检测插件是否可用
        from plugins import has_law_verification_plugin  # type: ignore[attr-defined]

        if not has_law_verification_plugin():
            return {"error": "法规核查插件未安装", "references": [], "total": 0}

        # 获取威科先行凭证
        from apps.organization.models import AccountCredential
        from apps.core.security.secret_codec import SecretCodec

        try:
            cred = AccountCredential.objects.get(id=credential_id)
        except AccountCredential.DoesNotExist:
            return {"error": f"凭证 ID {credential_id} 不存在", "references": [], "total": 0}

        codec = SecretCodec()
        password = codec.try_decrypt(cred.password)

        # 建立威科先行会话
        from plugins.weike_api_private.adapter import PrivateWeikeApiAdapter
        from apps.legal_research.services.sources.weike.client import WeikeCaseClient

        adapter = PrivateWeikeApiAdapter()
        client = WeikeCaseClient()

        try:
            session = adapter.open_http_session(
                client=client,
                username=cred.account,
                password=password,
                login_url=cred.url or None,
            )
        except Exception as e:
            return {"error": f"威科先行登录失败: {e}", "references": [], "total": 0}

        # 定义回调函数
        def search_laws(law_name: str) -> list[dict[str, Any]]:
            return adapter.search_laws_via_api(session=session, keyword=law_name)  # type: ignore[no-any-return]

        def fetch_article(doc_id: str, article_num: int) -> str | None:
            return adapter.fetch_law_article_via_api(session=session, doc_id=doc_id, article_num=article_num)  # type: ignore[no-any-return]

        # 执行核查
        from plugins.weike_api_private.law_verification import verify_references

        try:
            results = verify_references(text, search_laws_fn=search_laws, fetch_article_fn=fetch_article)
        except Exception as e:
            return {"error": f"核查失败: {e}", "references": [], "total": 0}

        return {
            "references": [
                {
                    "law_name": r.law_name,
                    "article_num": r.article_num,
                    "status": r.status,
                    "validity": r.validity,
                    "article_text": r.article_text,
                    "reference_text": r.reference_text,
                    "similarity": r.similarity,
                    "weike_url": r.weike_url,
                }
                for r in results
            ],
            "total": len(results),
        }

    loop = get_running_loop()
    return await loop.run_in_executor(None, _do_check)
