"""开庭模式 Admin views"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.contrib import admin
from django.http import HttpRequest, JsonResponse
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.translation import gettext_lazy as _

from apps.evidence.models import EvidenceDirection, EvidenceItem, EvidenceList, EvidenceType, HearingNote

logger = logging.getLogger("apps.evidence")


class HearingModeAdminMixin:
    """开庭模式 Admin Mixin，添加到 EvidenceListAdmin"""

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()  # type: ignore[misc]
        custom = [
            path(
                "hearing-mode/<int:case_id>/",
                self.admin_site.admin_view(self.hearing_mode_view),  # type: ignore[attr-defined]
                name="evidence_hearing_mode",
            ),
            path(
                "hearing-note/<int:case_id>/save/",
                self.admin_site.admin_view(self.hearing_note_save_view),  # type: ignore[attr-defined]
                name="evidence_hearing_note_save",
            ),
        ]
        return custom + urls

    def hearing_mode_view(self, request: HttpRequest, case_id: int) -> TemplateResponse:
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

    def hearing_note_save_view(self, request: HttpRequest, case_id: int) -> JsonResponse:
        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

        data = json.loads(request.body)
        content = data.get("content", "").strip()
        if not content:
            return JsonResponse({"success": False, "error": "内容不能为空"})

        note = HearingNote.objects.create(case_id=case_id, content=content)

        evidence_order = data.get("evidence_order")
        if evidence_order:
            # 通过全局序号找到对应的 EvidenceItem
            for el in EvidenceList.objects.filter(case_id=case_id).order_by("order"):
                start = el.start_order
                for item in el.items.order_by("order"):
                    if start + item.order - 1 == int(evidence_order):
                        note.evidence_items.add(item)
                        break

        return JsonResponse({"success": True, "note_id": note.pk})


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
