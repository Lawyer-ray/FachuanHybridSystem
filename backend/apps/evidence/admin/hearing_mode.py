"""开庭模式 Admin views"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from django.template.response import TemplateResponse
from django.urls import path

from apps.evidence.models import EvidenceItem, EvidenceList, EvidenceType

logger = logging.getLogger("apps.evidence")


class HearingModeAdminMixin:  # pragma: no cover
    """开庭模式 Admin Mixin，添加到 EvidenceListAdmin"""

    def get_urls(self) -> list[Any]:  # pragma: no cover
        urls = super().get_urls()  # type: ignore[misc]
        custom = [
            path(
                "hearing-mode/<int:case_id>/",
                self.admin_site.admin_view(self.hearing_mode_view),  # type: ignore[attr-defined]
                name="evidence_hearing_mode",
            ),
        ]
        return custom + urls  # type: ignore[no-any-return]

    def hearing_mode_view(self, request: HttpRequest, case_id: int) -> TemplateResponse:  # pragma: no cover
        from apps.cases.models import Case

        case = Case.objects.get(pk=case_id)
        evidence_lists = EvidenceList.objects.filter(case_id=case_id).order_by("order")

        items: list[dict[str, Any]] = []
        for el in evidence_lists:
            start_order = el.start_order
            for item in el.items.order_by("order"):
                global_order = start_order + item.order - 1
                items.append(
                    {
                        "global_order": global_order,
                        "name": item.name,
                        "purpose": item.purpose,
                        "direction": item.direction,
                        "evidence_type": item.evidence_type,
                        "evidence_type_display": item.get_evidence_type_display() if item.evidence_type else "",
                        "original_status": item.original_status,
                        "original_location": item.original_location,
                        "page_range": item.page_range_display,
                        "page_count": item.page_count,
                        "ocr_text": item.ocr_text or "",
                        "three_properties": item.three_properties,
                        "three_properties_display": _format_properties(item.three_properties),
                        "cross_examination": item.cross_examination,
                        "cross_examination_display": _format_properties(item.cross_examination),
                    }
                )

        context = {
            "case_id": case_id,
            "case_name": case.name,
            "items": items,
            "evidence_types": EvidenceType.choices,
            "opts": EvidenceList._meta,
            "has_view_permission": True,
            "site_header": admin.site.site_header,
            "site_title": admin.site.site_title,
        }
        return TemplateResponse(request, "admin/evidence/hearing_mode.html", context)


def _format_properties(data: dict[str, Any] | None) -> str:
    """格式化三性/质证意见 JSON 为可读文本"""
    if not data:
        return ""
    parts: list[str] = []
    labels = {"authenticity": "真实性", "legality": "合法性", "relevance": "关联性"}
    for key, label in labels.items():
        info = data.get(key, {})
        if not info:
            continue
        opinion = info.get("opinion", "")
        reason = info.get("reason", "")
        if opinion or reason:
            parts.append(f"{label}: {opinion} {reason}".strip())
    return " | ".join(parts)
