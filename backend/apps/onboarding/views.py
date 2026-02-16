"""Module for views."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.client.models import Client
from apps.contracts.models import FeeMode, PartyRole
from apps.core.enums import CaseStage, CaseType, LegalStatus


def _get_onboarding_data() -> dict[str, Any]:
    """获取立案引导所需的基础配置数据."""
    legal_statuses = [{"value": choice[0], "label": choice[1]} for choice in LegalStatus.choices]
    if any(ls["value"] == "plaintiff" for ls in legal_statuses) and not any(
        ls["value"] == "plaintif" for ls in legal_statuses
    ):
        label = next(ls["label"] for ls in legal_statuses if ls["value"] == "plaintiff")
        legal_statuses.insert(0, {"value": "plaintif", "label": label})

    return {
        "apiBase": "/api/v1",
        "debug": bool(getattr(settings, "DEBUG", False)),
        "caseTypes": [{"value": choice[0], "label": choice[1]} for choice in CaseType.choices],
        "feeModes": [
            {"value": choice[0], "label": choice[1]} for choice in FeeMode.choices if choice[0] != FeeMode.CUSTOM
        ],
        "clientTypes": [{"value": choice[0], "label": choice[1]} for choice in Client.CLIENT_TYPE_CHOICES],
        "partyRoles": [{"value": choice[0], "label": choice[1]} for choice in PartyRole.choices],
        "legalStatuses": legal_statuses,
        "caseStages": [{"value": choice[0], "label": choice[1]} for choice in CaseStage.choices],
    }


@login_required
@require_GET
def wizard_view(request: HttpRequest) -> HttpResponse:
    """
    立案引导向导页面视图.

    提供立案所需的基础配置数据,包括案件类型、收费模式、
    当事人类型、诉讼地位等选项.使用现代明亮主题设计,
    柔和渐变配色,Plus Jakarta Sans 字体.

    Args:
        request: HTTP请求对象

    Returns:
        HttpResponse: 渲染后的向导页面
    """
    onboarding_data = _get_onboarding_data()
    return render(
        request,
        "onboarding/wizard.html",
        {
            "onboarding_data": onboarding_data,
            "case_types": onboarding_data.get("caseTypes", []),
            "fee_modes": onboarding_data.get("feeModes", []),
            "client_types": onboarding_data.get("clientTypes", []),
            "legal_statuses": onboarding_data.get("legalStatuses", []),
            "case_stages": onboarding_data.get("caseStages", []),
            "party_roles": onboarding_data.get("partyRoles", []),
        },
    )
