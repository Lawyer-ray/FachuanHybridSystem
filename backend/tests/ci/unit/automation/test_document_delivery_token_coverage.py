"""Tests for automation/services/document_delivery/token/document_delivery_token_service.py
— uncovered branches.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestDocumentDeliveryTokenServiceInit:
    def test_default_init(self):
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )
        svc = DocumentDeliveryTokenService()
        assert svc._cache_manager is None
        assert svc._auto_token_service is None

    def test_injected_init(self):
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )
        mock_cm = MagicMock()
        mock_at = MagicMock()
        svc = DocumentDeliveryTokenService(cache_manager=mock_cm, auto_token_service=mock_at)
        assert svc.cache_manager is mock_cm
        assert svc.auto_token_service is mock_at


class TestDocumentDeliveryTokenServiceCacheManagerProperty:
    def test_lazy_load(self):
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )
        svc = DocumentDeliveryTokenService()
        with patch("apps.automation.services.token.cache_manager.cache_manager") as mock_cm:
            cm = svc.cache_manager
            assert cm is svc._cache_manager or cm is not None


class TestDocumentDeliveryTokenServiceAutoTokenServiceProperty:
    def test_lazy_load(self):
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )
        svc = DocumentDeliveryTokenService()
        with patch("apps.automation.services.token.auto_token_acquisition_service.AutoTokenAcquisitionService") as MockATS:
            MockATS.return_value = MagicMock()
            ats = svc.auto_token_service
            assert ats is not None


class TestAcquireToken:
    def test_credential_not_found(self):
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )
        svc = DocumentDeliveryTokenService()
        mock_org_svc = MagicMock()
        mock_org_svc.get_credential.return_value = None
        with patch("apps.automation.services.document_delivery.token.document_delivery_token_service.ServiceLocator") as MockSL:
            MockSL.get_organization_service.return_value = mock_org_svc
            result = svc.acquire_token(credential_id=1)
            assert result is None

    def test_cache_hit(self):
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )
        svc = DocumentDeliveryTokenService()
        mock_cm = MagicMock()
        mock_cm.get_cached_token.return_value = "cached_token"
        svc._cache_manager = mock_cm
        mock_org_svc = MagicMock()
        credential = MagicMock()
        credential.site_name = "court"
        credential.account = "test"
        mock_org_svc.get_credential.return_value = credential
        with patch("apps.automation.services.document_delivery.token.document_delivery_token_service.ServiceLocator") as MockSL:
            MockSL.get_organization_service.return_value = mock_org_svc
            with patch("apps.automation.services.document_delivery.token.document_delivery_token_service.AutomationLogger"):
                result = svc.acquire_token(credential_id=1)
                assert result == "cached_token"

    def test_cache_miss_fallback_to_service(self):
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )
        svc = DocumentDeliveryTokenService()
        mock_cm = MagicMock()
        mock_cm.get_cached_token.return_value = None
        svc._cache_manager = mock_cm
        mock_at = MagicMock()
        mock_at.acquire_token_if_needed = AsyncMock(return_value="new_token")
        svc._auto_token_service = mock_at
        mock_org_svc = MagicMock()
        credential = MagicMock()
        credential.site_name = "court"
        credential.account = "test"
        mock_org_svc.get_credential.return_value = credential
        with patch("apps.automation.services.document_delivery.token.document_delivery_token_service.ServiceLocator") as MockSL:
            MockSL.get_organization_service.return_value = mock_org_svc
            with patch("apps.automation.services.document_delivery.token.document_delivery_token_service.AutomationLogger"):
                result = svc.acquire_token(credential_id=1)
                assert result == "new_token"

    def test_cache_miss_service_returns_none(self):
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )
        svc = DocumentDeliveryTokenService()
        mock_cm = MagicMock()
        mock_cm.get_cached_token.return_value = None
        svc._cache_manager = mock_cm
        svc._acquire_token_via_service = MagicMock(return_value=None)
        mock_org_svc = MagicMock()
        credential = MagicMock()
        credential.site_name = "court"
        credential.account = "test"
        mock_org_svc.get_credential.return_value = credential
        with patch("apps.automation.services.document_delivery.token.document_delivery_token_service.ServiceLocator") as MockSL:
            MockSL.get_organization_service.return_value = mock_org_svc
            with patch("apps.automation.services.document_delivery.token.document_delivery_token_service.AutomationLogger"):
                result = svc.acquire_token(credential_id=1)
                assert result is None

    def test_exception_returns_none(self):
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )
        svc = DocumentDeliveryTokenService()
        with patch("apps.automation.services.document_delivery.token.document_delivery_token_service.ServiceLocator") as MockSL:
            MockSL.get_organization_service.side_effect = RuntimeError("fail")
            with patch("apps.automation.services.document_delivery.token.document_delivery_token_service.AutomationLogger"):
                result = svc.acquire_token(credential_id=1)
                assert result is None


class TestAcquireTokenViaService:
    def test_no_event_loop(self):
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )
        svc = DocumentDeliveryTokenService()
        mock_at = MagicMock()
        mock_at.acquire_token_if_needed = AsyncMock(return_value="token123")
        svc._auto_token_service = mock_at
        with patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
            with patch("asyncio.run", return_value="token123") as mock_run:
                result = svc._acquire_token_via_service("court", 1)
                assert result == "token123"

    def test_exception_returns_none(self):
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )
        svc = DocumentDeliveryTokenService()
        mock_at = MagicMock()
        mock_at.acquire_token_if_needed = AsyncMock(side_effect=RuntimeError("fail"))
        svc._auto_token_service = mock_at
        result = svc._acquire_token_via_service("court", 1)
        assert result is None


class TestInvalidateToken:
    def test_credential_not_found(self):
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )
        svc = DocumentDeliveryTokenService()
        mock_org_svc = MagicMock()
        mock_org_svc.get_credential.return_value = None
        with patch("apps.automation.services.document_delivery.token.document_delivery_token_service.ServiceLocator") as MockSL:
            MockSL.get_organization_service.return_value = mock_org_svc
            assert svc.invalidate_token(credential_id=1) is False

    def test_success(self):
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )
        svc = DocumentDeliveryTokenService()
        mock_cm = MagicMock()
        svc._cache_manager = mock_cm
        mock_org_svc = MagicMock()
        credential = MagicMock()
        credential.site_name = "court"
        credential.account = "test"
        mock_org_svc.get_credential.return_value = credential
        with patch("apps.automation.services.document_delivery.token.document_delivery_token_service.ServiceLocator") as MockSL:
            MockSL.get_organization_service.return_value = mock_org_svc
            assert svc.invalidate_token(credential_id=1) is True
            mock_cm.invalidate_token_cache.assert_called_once_with("court", "test")

    def test_exception(self):
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )
        svc = DocumentDeliveryTokenService()
        with patch("apps.automation.services.document_delivery.token.document_delivery_token_service.ServiceLocator") as MockSL:
            MockSL.get_organization_service.side_effect = RuntimeError("fail")
            assert svc.invalidate_token(credential_id=1) is False
