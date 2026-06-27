"""案件材料整理 API"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router

from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security.auth import JWTOrSessionAuth

logger = logging.getLogger("apps.evidence_sorting")

router = Router(tags=["案件材料整理"], auth=JWTOrSessionAuth())


def _body(request: HttpRequest) -> dict[str, Any]:
    return json.loads(request.body or b"{}")  # type: ignore[no-any-return]


@router.post("/classify")
async def classify_images(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
    """OCR + 关键词分类"""
    payload = _body(request)
    images: list[dict[str, Any]] = payload.get("images", [])
    if not images:
        return {"success": False, "message": "没有图片"}

    from apps.evidence_sorting.services.classifier import ClassifierService

    svc = ClassifierService()

    @sync_to_async
    def _classify() -> Any:
        return svc.classify_images(images)

    result = await _classify()

    return {
        "success": True,
        "images": [
            {
                "filename": img.filename,
                "category": img.category,
                "ocr_text": img.ocr_text,
                "date": img.date,
                "amount": img.amount,
                "signed": img.signed,
                "confidence": img.confidence,
                "rotation": img.rotation,
            }
            for img in result.images
        ],
        "errors": result.errors,
    }


@router.post("/parse-statement")
async def parse_statement(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
    """LLM 解析对账单"""
    payload = _body(request)
    ocr_text: str = payload.get("ocr_text", "")
    backend: str | None = payload.get("backend")
    model: str | None = payload.get("model")

    if not ocr_text:
        return {"success": False, "message": "缺少 ocr_text"}

    from apps.evidence_sorting.services.reconciler import ReconcilerService

    svc = ReconcilerService()

    @sync_to_async
    def _parse() -> Any:
        return svc.parse_statement(ocr_text, backend=backend, model=model)

    info = await _parse()

    return {
        "success": True,
        "month": info.month,
        "total_amount": info.total_amount,
        "signed": info.signed,
        "line_items": [{"date": li.date, "amount": li.amount, "description": li.description} for li in info.line_items],
    }


@router.post("/reconcile")
async def reconcile(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
    """交叉比对"""
    payload = _body(request)
    statements: list[dict[str, Any]] = payload.get("statements", [])
    deliveries: list[dict[str, Any]] = payload.get("deliveries", [])
    receipts: list[dict[str, Any]] = payload.get("receipts", [])
    others: list[dict[str, Any]] = payload.get("others", [])
    backend: str | None = payload.get("backend")
    model: str | None = payload.get("model")

    from apps.evidence_sorting.services.reconciler import ReconcilerService

    svc = ReconcilerService()

    @sync_to_async
    def _reconcile() -> Any:
        return svc.reconcile(
            statements=statements,
            deliveries=deliveries,
            receipts=receipts,
            others=others,
            backend=backend,
            model=model,
        )

    result = await _reconcile()

    return {
        "success": True,
        "month_groups": [
            {
                "month": g.month,
                "folder_name": g.folder_name,
                "issues": g.issues,
                "statement": (
                    {
                        "filename": g.statement.filename,
                        "month": g.statement.month,
                        "total_amount": g.statement.total_amount,
                        "signed": g.statement.signed,
                        "line_items_count": len(g.statement.line_items),
                    }
                    if g.statement
                    else None
                ),
                "deliveries": [
                    {
                        "filename": d.filename,
                        "date": d.date,
                        "amount": d.amount,
                        "match_status": d.match_status,
                        "remark": d.remark,
                    }
                    for d in g.deliveries
                ],
            }
            for g in result.month_groups
        ],
        "unsigned_statements": [
            {
                "filename": s.filename,
                "month": s.month,
                "total_amount": s.total_amount,
            }
            for s in result.unsigned_statements
        ],
        "receipts_count": len(result.receipts),
        "others_count": len(result.others),
        "unmatched_deliveries": [
            {"filename": d.filename, "date": d.date, "amount": d.amount} for d in result.unmatched_deliveries
        ],
    }


@router.post("/export")
@rate_limit_from_settings("EXPORT", by_user=True)
async def export_zip(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
    """导出 ZIP"""
    payload = _body(request)
    statements = payload.get("statements", [])
    deliveries = payload.get("deliveries", [])
    receipts = payload.get("receipts", [])
    others = payload.get("others", [])
    backend: str | None = payload.get("backend")
    model: str | None = payload.get("model")

    from apps.evidence_sorting.services.exporter import ExporterService
    from apps.evidence_sorting.services.reconciler import ReconcilerService

    reconciler = ReconcilerService()

    @sync_to_async
    def _reconcile_and_export() -> dict[str, Any]:
        result = reconciler.reconcile(
            statements=statements,
            deliveries=deliveries,
            receipts=receipts,
            others=others,
            backend=backend,
            model=model,
        )
        exporter = ExporterService()
        return exporter.export_zip(result)

    return await _reconcile_and_export()


@router.get("/llm-options")
@rate_limit_from_settings("LLM", by_user=True)
async def llm_options(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
    """获取可用的 LLM 后端和模型列表"""
    from apps.core.llm import get_llm_service
    from apps.core.llm.model_list_service import ModelListService

    llm = get_llm_service()
    backends: list[dict[str, Any]] = []

    async def _check_ollama() -> dict[str, Any] | None:
        try:
            ollama_backend = await sync_to_async(llm.get_backend)("ollama")
            is_available = await sync_to_async(ollama_backend.is_available)()
            default_model = await sync_to_async(ollama_backend.get_default_model)()
            return {
                "name": "ollama",
                "label": "Ollama (本地)",
                "available": is_available,
                "default_model": default_model,
            }
        except Exception:
            return None

    async def _check_openai_compatible() -> dict[str, Any] | None:
        try:
            oc_backend = await sync_to_async(llm.get_backend)("openai_compatible")
            model_svc = ModelListService()
            is_available, default_model, model_result = await asyncio.gather(
                sync_to_async(oc_backend.is_available)(),
                sync_to_async(oc_backend.get_default_model)(),
                sync_to_async(model_svc.get_result)(),
            )
            return {
                "name": "openai_compatible",
                "label": "在线模型",
                "available": is_available,
                "default_model": default_model,
                "models": model_result.models,
                "models_fallback": model_result.is_fallback,
                "models_error": model_result.error_message,
            }
        except Exception:
            return None

    ollama_result, oc_result = await asyncio.gather(_check_ollama(), _check_openai_compatible())
    for b in (ollama_result, oc_result):
        if b is not None:
            backends.append(b)

    return {"success": True, "backends": backends}
