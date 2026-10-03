"""unique_together → UniqueConstraint 迁移的回归测试。

等价性锚点：约束换形态后，重复键仍必须在数据库层拒绝（IntegrityError），
既有 get_or_create 依赖的唯一语义不变。取创建成本低的代表模型各验一条。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.automation.models import CourtDocument, CourtToken, DocumentDownloadStatus, ScraperTask, ScraperTaskType
from apps.core.models import ToolFavorite
from apps.organization.models import Lawyer


def _make_court_token() -> CourtToken:
    return CourtToken.objects.create(
        site_name="court_zxfw",
        account="uniq-tester",
        token="dummy-token",
        expires_at=timezone.now() + timedelta(hours=1),
    )


def _make_court_document(scraper_task: ScraperTask) -> CourtDocument:
    now = timezone.now()
    return CourtDocument.objects.create(
        scraper_task=scraper_task,
        c_sdbh="SD-UNIQ",
        c_stbh="ST-UNIQ",
        wjlj="https://example.com/a.pdf",
        c_wsbh="WS-UNIQ",
        c_wsmc="测试文书",
        c_fybh="F001",
        c_fymc="测试法院",
        c_wjgs="pdf",
        dt_cjsj=now,
        download_status=DocumentDownloadStatus.PENDING,
    )


@pytest.mark.django_db
class TestUniqueConstraintsEnforced:
    def test_court_token_site_account_unique(self):
        _make_court_token()
        with pytest.raises(IntegrityError), transaction.atomic():
            _make_court_token()

    def test_court_token_get_or_create_still_idempotent(self):
        _, created = CourtToken.objects.get_or_create(
            site_name="court_baoquan",
            account="shared",
            defaults={"token": "t", "expires_at": timezone.now() + timedelta(hours=1)},
        )
        assert created is True
        obj, created = CourtToken.objects.get_or_create(
            site_name="court_baoquan",
            account="shared",
            defaults={"token": "t2", "expires_at": timezone.now() + timedelta(hours=2)},
        )
        assert created is False
        assert obj.token == "t"

    def test_court_document_wsbh_sdbh_unique(self):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT, url="https://example.com/t"
        )
        _make_court_document(task)
        with pytest.raises(IntegrityError), transaction.atomic():
            _make_court_document(task)

    def test_tool_favorite_user_url_unique(self):
        lawyer = Lawyer.objects.create(username="uniq-favorite-user")
        ToolFavorite.objects.create(user=lawyer, tool_url="/tools/demo")
        with pytest.raises(IntegrityError), transaction.atomic():
            ToolFavorite.objects.create(user=lawyer, tool_url="/tools/demo")

    def test_tool_favorite_different_users_coexist(self):
        u1 = Lawyer.objects.create(username="uniq-favorite-u1")
        u2 = Lawyer.objects.create(username="uniq-favorite-u2")
        ToolFavorite.objects.create(user=u1, tool_url="/tools/demo")
        ToolFavorite.objects.create(user=u2, tool_url="/tools/demo")  # 不应撞约束
        assert ToolFavorite.objects.count() == 2
