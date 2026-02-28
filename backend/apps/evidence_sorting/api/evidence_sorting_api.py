"""案件材料整理 API"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.http import HttpRequest
from ninja import Router

logger = logging.getLogger("apps.evidence_sorting")

router = Router(tags=["案件材料整理"])


def _body(request: HttpRequest) -> dict[str, Any]:
    return json.loads(request.body or b"{}")


@router.post("/classify")
def classify_images(request: HttpRequest) -> dict[str, Any]:
    """OCR + 关键词分类"""
    payload = _body(request)
    images: list[dict[str, Any]] = payload.get("images", [])
    if not images:
        return {"success": False, "message": "没有图片"}

    from apps.evidence_sorting.services.classifier import ClassifierService

    svc = ClassifierService()
    result = svc.classify_images(images)

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
def parse_statement(request: HttpRequest) -> dict[str, Any]:
    """LLM 解析对账单"""
    payload = _body(request)
    ocr_text: str = payload.get("ocr_text", "")
    backend: str | None = payload.get("backend")
    model: str | None = payload.get("model")

    if not ocr_text:
        return {"success": False, "message": "缺少 ocr_text"}

    from apps.evidence_sorting.services.reconciler import ReconcilerService

    svc = ReconcilerService()
    info = svc.parse_statement(ocr_text, backend=backend, model=model)

    return {
        "success": True,
        "month": info.month,
        "total_amount": info.total_amount,
        "signed": info.signed,
        "line_items": [
            {"date": li.date, "amount": li.amount, "description": li.description}
            for li in info.line_items
        ],
    }


@router.post("/reconcile")
def reconcile(request: HttpRequest) -> dict[str, Any]:
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
    result = svc.reconcile(
        statements=statements,
        deliveries=deliveries,
        receipts=receipts,
        others=others,
        backend=backend,
        model=model,
    )

    return {
        "success": True,
        "month_groups": [
            {
                "month": g.month,
                "folder_name": g.folder_name,
                "issues": g.issues,
                "statement": {
                    "filename": g.statement.filename,
                    "month": g.statement.month,
                    "total_amount": g.statement.total_amount,
                    "signed": g.statement.signed,
                    "line_items_count": len(g.statement.line_items),
                } if g.statement else None,
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
            {"filename": d.filename, "date": d.date, "amount": d.amount}
            for d in result.unmatched_deliveries
        ],
    }


@router.post("/export")
def export_zip(request: HttpRequest) -> dict[str, Any]:
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


@router.get("/llm-options")
def llm_options(request: HttpRequest) -> dict[str, Any]:
    """获取可用的 LLM 后端和模型列表"""
    from apps.core.llm import get_llm_service
    from apps.core.llm.model_list_service import ModelListService

    llm = get_llm_service()
    backends: list[dict[str, Any]] = []

    # Ollama
    try:
        ollama_backend = llm.get_backend("ollama")
        backends.append({
            "name": "ollama",
            "label": "Ollama (本地)",
            "available": ollama_backend.is_available(),
            "default_model": ollama_backend.get_default_model(),
        })
    except Exception:
        pass

    # SiliconFlow
    try:
        sf_backend = llm.get_backend("siliconflow")
        model_svc = ModelListService()
        models = model_svc.get_models()
        backends.append({
            "name": "siliconflow",
            "label": "硅基流动",
            "available": sf_backend.is_available(),
            "default_model": sf_backend.get_default_model(),
            "models": models,
        })
    except Exception:
        pass

    return {"success": True, "backends": backends}
