"""
外部模板 API

提供外部模板分析、填充、匹配等接口.
"""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.utils.translation import gettext_lazy as _
from ninja import Router, Schema

from apps.core.security.auth import JWTOrSessionAuth

logger = logging.getLogger("apps.documents.api")
router = Router(auth=JWTOrSessionAuth())


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def _get_analysis_service() -> Any:
    from apps.documents.services.infrastructure.wiring import get_analysis_service

    return get_analysis_service()


def _get_filling_service() -> Any:
    from apps.documents.services.infrastructure.wiring import get_filling_service

    return get_filling_service()


def _get_matching_service() -> Any:
    from apps.documents.services.infrastructure.wiring import get_matching_service

    return get_matching_service()


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class FillRequestSchema(Schema):
    """填充请求体"""

    template_ids: list[int]
    case_id: int
    party_ids: list[int] | None = None
    custom_values: dict[str, dict[str, str]] | None = None


class MappingUpdateSchema(Schema):
    """映射更新请求体"""

    semantic_label: str | None = None
    fill_type: str | None = None
    position_description: str | None = None


class MappingCreateSchema(Schema):
    """映射创建请求体"""

    position_locator: dict[str, Any]
    position_description: str = ""
    semantic_label: str
    fill_type: str = "text"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{template_id}/analyze")
def analyze_template(request: HttpRequest, template_id: int) -> dict[str, Any]:
    """触发/重新触发 LLM 分析"""
    service = _get_analysis_service()
    mappings = service.analyze_template(template_id)
    logger.info(
        "模板分析完成",
        extra={"template_id": template_id, "mapping_count": len(mappings)},
    )
    return {
        "success": True,
        "template_id": template_id,
        "mapping_count": len(mappings),
    }


@router.post("/{template_id}/confirm")
def confirm_mappings(request: HttpRequest, template_id: int) -> dict[str, Any]:
    """确认字段映射"""
    service = _get_analysis_service()
    service.confirm_mappings(template_id)
    logger.info("映射已确认", extra={"template_id": template_id})
    return {"success": True, "template_id": template_id}


@router.post("/fill")
def fill_templates(request: HttpRequest, payload: FillRequestSchema) -> dict[str, Any] | HttpResponse:
    """执行填充（单个或批量），返回文件信息"""
    service = _get_filling_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)

    batch_task = service.batch_fill(
        case_id=payload.case_id,
        template_ids=payload.template_ids,
        party_ids=payload.party_ids,
        custom_values=payload.custom_values,
        filled_by=user,
    )

    records = list(batch_task.records.values_list("id", "original_output_name", "file_path", flat=False))
    logger.info(
        "填充完成",
        extra={"batch_task_id": batch_task.id, "record_count": len(records)},
    )
    return {
        "success": True,
        "batch_task_id": batch_task.id,
        "zip_file_path": batch_task.zip_file_path,
        "summary": batch_task.summary_json,
        "records": [{"id": r[0], "filename": r[1], "file_path": r[2]} for r in records],
    }


@router.get("/{template_id}/preview")
def preview_fill(
    request: HttpRequest,
    template_id: int,
    case_id: int,
    party_id: int | None = None,
) -> dict[str, Any]:
    """填充预览"""
    service = _get_filling_service()
    items = service.generate_preview(
        template_id=template_id,
        case_id=case_id,
        party_id=party_id,
    )
    return {
        "template_id": template_id,
        "case_id": case_id,
        "party_id": party_id,
        "fields": [
            {
                "position_description": item.position_description,
                "semantic_label": item.semantic_label,
                "fill_value": item.fill_value,
                "value_source": item.value_source,
                "fill_type": item.fill_type,
                "mapping_id": item.mapping_id,
            }
            for item in items
        ],
    }


@router.get("/match")
def match_templates(
    request: HttpRequest,
    case_id: int | None = None,
    source_name: str | None = None,
) -> dict[str, Any]:
    """模板匹配推荐"""
    service = _get_matching_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    law_firm_id: int | None = getattr(user, "law_firm_id", None)

    if law_firm_id is None:
        return {"success": False, "message": str(_("无法确定所属律所"))}

    if case_id is not None:
        results = service.match_by_case(case_id=case_id, law_firm_id=law_firm_id)
    elif source_name is not None:
        results = service.match_by_source_name(
            source_name=source_name,
            law_firm_id=law_firm_id,
        )
    else:
        return {"success": False, "message": str(_("请提供 case_id 或 source_name 参数"))}

    return {
        "success": True,
        "results": [{"id": t.id, "name": t.name, "status": t.status, "version": t.version} for t in results],
    }


@router.get("/{template_id}/custom-fields")
def get_custom_fields(request: HttpRequest, template_id: int) -> dict[str, Any]:
    """获取需手动输入的自定义字段"""
    service = _get_filling_service()
    fields = service.get_custom_fields(template_id)
    return {"template_id": template_id, "fields": fields}


@router.get("/history")
def get_fill_history(
    request: HttpRequest,
    case_id: int | None = None,
    template_id: int | None = None,
) -> dict[str, Any]:
    """填充历史查询"""
    service = _get_filling_service()

    if case_id is not None:
        qs = service.get_fill_history_by_case(case_id)
    elif template_id is not None:
        qs = service.get_fill_history_by_template(template_id)
    else:
        return {"success": False, "message": str(_("请提供 case_id 或 template_id 参数"))}

    records = list(
        qs.values(
            "id",
            "case_id",
            "template_id",
            "party_id",
            "filled_at",
            "original_output_name",
            "file_available",
        )
    )
    return {"success": True, "records": records}


@router.get("/statistics")
def get_statistics(request: HttpRequest) -> dict[str, Any]:
    """模板统计"""
    service = _get_matching_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    law_firm_id: int | None = getattr(user, "law_firm_id", None)

    if law_firm_id is None:
        return {"success": False, "message": str(_("无法确定所属律所"))}

    stats = service.get_template_statistics(law_firm_id)
    return {"success": True, "statistics": stats}


# ---------------------------------------------------------------------------
# 预览与映射编辑 API
# ---------------------------------------------------------------------------


@router.get("/{template_id}/preview-html")
def get_preview_html(request: HttpRequest, template_id: int) -> dict[str, Any]:
    """将 docx 转为 HTML 用于预览"""
    from pathlib import Path

    import mammoth
    from django.conf import settings

    from apps.documents.models.external_template import ExternalTemplate

    template = ExternalTemplate.objects.get(pk=template_id)
    abs_path = Path(settings.MEDIA_ROOT) / template.file_path

    with abs_path.open("rb") as f:
        result = mammoth.convert_to_html(f)

    return {
        "html": result.value,
        "messages": [str(m) for m in result.messages],
    }


@router.get("/{template_id}/mappings")
def list_mappings(request: HttpRequest, template_id: int) -> list[dict[str, Any]]:
    """获取模板的所有字段映射"""
    from apps.documents.models.external_template import ExternalTemplateFieldMapping

    mappings = ExternalTemplateFieldMapping.objects.filter(template_id=template_id).order_by("sort_order", "id")

    return [
        {
            "id": m.id,
            "position_locator": m.position_locator,
            "position_description": m.position_description,
            "semantic_label": m.semantic_label,
            "fill_type": m.fill_type,
            "sort_order": m.sort_order,
        }
        for m in mappings
    ]


@router.post("/{template_id}/mappings")
def create_mapping(request: HttpRequest, template_id: int, payload: MappingCreateSchema) -> dict[str, Any]:
    """手动添加字段映射"""
    service = _get_analysis_service()
    m = service.create_manual_mapping(
        template_id=template_id,
        position_locator=payload.position_locator,
        position_description=payload.position_description,
        semantic_label=payload.semantic_label,
        fill_type=payload.fill_type,
    )
    logger.info("手动添加映射: template_id=%d, mapping_id=%d", template_id, m.id)
    return {
        "id": m.id,
        "position_locator": m.position_locator,
        "position_description": m.position_description,
        "semantic_label": m.semantic_label,
        "fill_type": m.fill_type,
        "sort_order": m.sort_order,
    }


@router.put("/mappings/{mapping_id}")
def update_mapping(request: HttpRequest, mapping_id: int, payload: MappingUpdateSchema) -> dict[str, Any]:
    """更新字段映射"""
    from apps.documents.models.external_template import ExternalTemplateFieldMapping

    m = ExternalTemplateFieldMapping.objects.get(pk=mapping_id)
    update_fields: list[str] = ["updated_at"]

    if payload.semantic_label is not None:
        m.semantic_label = payload.semantic_label
        update_fields.append("semantic_label")
    if payload.fill_type is not None:
        m.fill_type = payload.fill_type
        update_fields.append("fill_type")
    if payload.position_description is not None:
        m.position_description = payload.position_description
        update_fields.append("position_description")

    m.save(update_fields=update_fields)
    logger.info("更新映射: mapping_id=%d", mapping_id)
    return {
        "id": m.id,
        "position_locator": m.position_locator,
        "position_description": m.position_description,
        "semantic_label": m.semantic_label,
        "fill_type": m.fill_type,
        "sort_order": m.sort_order,
    }


@router.delete("/mappings/{mapping_id}")
def delete_mapping(request: HttpRequest, mapping_id: int) -> dict[str, bool]:
    """删除字段映射"""
    service = _get_analysis_service()
    service.delete_mapping(mapping_id)
    logger.info("删除映射: mapping_id=%d", mapping_id)
    return {"success": True}
