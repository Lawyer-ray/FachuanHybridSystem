from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite

from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin
from apps.legal_research.models import LegalResearchTask, LegalResearchTaskEvent
from apps.organization.models import AccountCredential


@pytest.mark.django_db
def test_private_api_stage_metrics_includes_capability_metrics(lawyer) -> None:
    credential = AccountCredential.objects.create(
        lawyer=lawyer,
        site_name="wkxx",
        url="https://www.wkinfo.com.cn/login/index",
        account="admin-metrics-account",
        password="admin-metrics-password",  # pragma: allowlist secret
    )
    task = LegalResearchTask.objects.create(
        created_by=lawyer,
        credential=credential,
        source="weike",
        keyword="买卖合同 违约",
        case_summary="被告逾期交货并引发赔偿争议。",
        target_count=3,
        max_candidates=100,
        min_similarity_score=0.9,
    )
    LegalResearchTaskEvent.objects.create(
        task=task,
        stage="search",
        source="system",
        interface_name="capability_direct_call",
        method="POST",
        status_code=200,
        duration_ms=1200,
        success=True,
    )
    LegalResearchTaskEvent.objects.create(
        task=task,
        stage="search",
        source="system",
        interface_name="capability_direct_call",
        method="POST",
        status_code=504,
        duration_ms=20000,
        success=False,
        error_code="LEGAL_RESEARCH_CAPABILITY_TIMEOUT",
    )

    admin = LegalResearchTaskAdmin(LegalResearchTask, AdminSite())
    html = str(admin.private_api_stage_metrics(task))

    assert "能力直连成功率" in html
    assert "timeout=" in html
