"""Tests for admin service modules."""

from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")

try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)

from django.utils import timezone

from apps.core.exceptions import BusinessException, ValidationException


# ============================================================
# token_acquisition_history_admin_service.py
# ============================================================

class TestTokenAcquisitionHistoryAdminService:
    """Tests for TokenAcquisitionHistoryAdminService."""

    def _make_service(self):
        from apps.automation.services.admin.token_acquisition_history_admin_service import (
            TokenAcquisitionHistoryAdminService,
        )
        return TokenAcquisitionHistoryAdminService()

    @pytest.mark.django_db
    def test_cleanup_old_records_zero_days_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="保留天数必须大于0"):
            svc.cleanup_old_records(days=0)

    @pytest.mark.django_db
    def test_cleanup_old_records_negative_days_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc.cleanup_old_records(days=-1)

    def test_export_to_csv_empty_queryset_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="没有选中任何记录"):
            svc.export_to_csv(None)

    def test_reanalyze_performance_empty_queryset_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc.reanalyze_performance(None)


# ============================================================
# court_document_admin_service.py
# ============================================================

class TestCourtDocumentAdminService:
    """Tests for CourtDocumentAdminService."""

    def _make_service(self):
        from apps.automation.services.admin.court_document_admin_service import CourtDocumentAdminService
        return CourtDocumentAdminService()

    @pytest.mark.django_db
    def test_batch_download_empty_ids_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="没有选中任何文书"):
            svc.batch_download_documents([])

    @pytest.mark.django_db
    def test_batch_delete_empty_ids_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc.batch_delete_documents([])

    @pytest.mark.django_db
    def test_batch_delete_empty_ids_delete_files(self):
        svc = self._make_service()
        with pytest.raises(ValidationException):
            svc.batch_delete_documents([], delete_files=True)


# ============================================================
# preservation_quote_admin_service.py
# ============================================================

class TestPreservationQuoteAdminService:
    """Tests for PreservationQuoteAdminService."""

    def _make_service(self):
        from plugins.court_automation.preservation_quote.admin_service import PreservationQuoteAdminService
        return PreservationQuoteAdminService()

    @pytest.mark.django_db
    def test_execute_quotes_empty_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="没有选中任何询价任务"):
            asyncio.run(svc.execute_quotes([]))

    @pytest.mark.django_db
    def test_batch_create_quotes_empty_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="没有提供询价配置"):
            svc.batch_create_quotes([])

    @pytest.mark.django_db
    def test_batch_create_quotes_missing_amount_raises(self):
        svc = self._make_service()
        # The inner try catches ValidationException, so this returns error dict
        result = svc.batch_create_quotes([{"corp_id": "2550"}])
        assert result["error_count"] == 1

    @pytest.mark.django_db
    def test_batch_create_quotes_negative_amount_raises(self):
        svc = self._make_service()
        result = svc.batch_create_quotes([{"preserve_amount": "-100"}])
        assert result["error_count"] == 1

    @pytest.mark.django_db
    def test_batch_create_quotes_zero_amount_raises(self):
        svc = self._make_service()
        result = svc.batch_create_quotes([{"preserve_amount": "0"}])
        assert result["error_count"] == 1


import asyncio


# ============================================================
# scraping_tasks.py - _run_coroutine_sync
# ============================================================

class TestRunCoroutineSync:
    """Tests for _run_coroutine_sync helper."""

    def test_run_simple_coroutine(self):
        from apps.automation.tasks.scraping_tasks import _run_coroutine_sync

        async def coro():
            return 42

        result = _run_coroutine_sync(coro())
        assert result == 42

    def test_run_coroutine_with_exception(self):
        from apps.automation.tasks.scraping_tasks import _run_coroutine_sync

        async def coro():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            _run_coroutine_sync(coro())
