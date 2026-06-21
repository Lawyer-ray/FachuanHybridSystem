"""CourtSMSDedupService 单元测试。"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.automation.models import CourtSMSStatus
from apps.automation.services.sms.court_sms_dedup_service import CourtSMSDedupService


@pytest.mark.django_db
class TestCourtSMSDedupService:
    """验证文书送达去重的核心行为。"""
