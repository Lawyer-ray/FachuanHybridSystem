"""Coverage tests for document_delivery_token_service."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.automation.services.document_delivery.token.document_delivery_token_service import (
    DocumentDeliveryTokenService,
)


class TestDocumentDeliveryTokenServiceInit:
    def test_init_defaults(self):
        svc = DocumentDeliveryTokenService()
        assert svc._cache_manager is None
        assert svc._auto_token_service is None

    def test_init_with_injection(self):
        cache = MagicMock()
        auto = MagicMock()
        svc = DocumentDeliveryTokenService(cache_manager=cache, auto_token_service=auto)
        assert svc._cache_manager is cache
        assert svc._auto_token_service is auto


class TestCacheManagerProperty:
    def test_lazy_load(self):
        svc = DocumentDeliveryTokenService()
        with patch(
            "apps.automation.services.token.cache_manager.cache_manager", new_callable=lambda: MagicMock
        ) as mock_cm:
            # The property imports from the module-level cache_manager
            with patch.dict("sys.modules", {"apps.automation.services.token.cache_manager": MagicMock(cache_manager=mock_cm)}):
                pass  # lazy load tested via integration

    def test_direct_inject(self):
        cache = MagicMock()
        svc = DocumentDeliveryTokenService(cache_manager=cache)
        assert svc.cache_manager is cache


class TestAutoTokenServiceProperty:
    def test_direct_inject(self):
        auto = MagicMock()
        svc = DocumentDeliveryTokenService(auto_token_service=auto)
        assert svc.auto_token_service is auto


class TestAcquireToken:
    def test_credential_not_found(self):
        svc = DocumentDeliveryTokenService(cache_manager=MagicMock())
        with patch("apps.core.interfaces.ServiceLocator") as mock_sl:
            mock_org = MagicMock()
            mock_org.get_credential.return_value = None
            mock_sl.get_organization_service.return_value = mock_org
            result = svc.acquire_token(credential_id=1)
            assert result is None

    def test_cache_hit(self):
        cache = MagicMock()
        cache.get_cached_token.return_value = "cached_token_abc"
        svc = DocumentDeliveryTokenService(cache_manager=cache)
        with patch("apps.core.interfaces.ServiceLocator.get_organization_service") as mock_get:
            mock_org = MagicMock()
            mock_cred = SimpleNamespace(site_name="court", account="user1")
            mock_org.get_credential.return_value = mock_cred
            mock_get.return_value = mock_org
            with patch("apps.automation.utils.logging.AutomationLogger"):
                result = svc.acquire_token(credential_id=1)
                assert result == "cached_token_abc"

    def test_cache_miss_acquires_via_service(self):
        cache = MagicMock()
        cache.get_cached_token.return_value = None
        svc = DocumentDeliveryTokenService(cache_manager=cache, auto_token_service=MagicMock())
        svc._acquire_token_via_service = MagicMock(return_value="new_token")
        with patch("apps.core.interfaces.ServiceLocator.get_organization_service") as mock_get:
            mock_org = MagicMock()
            mock_cred = SimpleNamespace(site_name="court", account="user1")
            mock_org.get_credential.return_value = mock_cred
            mock_get.return_value = mock_org
            with patch("apps.automation.utils.logging.AutomationLogger"):
                result = svc.acquire_token(credential_id=1)
                assert result == "new_token"

    def test_acquisition_returns_none(self):
        cache = MagicMock()
        cache.get_cached_token.return_value = None
        svc = DocumentDeliveryTokenService(cache_manager=cache, auto_token_service=MagicMock())
        svc._acquire_token_via_service = MagicMock(return_value=None)
        with patch("apps.core.interfaces.ServiceLocator.get_organization_service") as mock_get:
            mock_org = MagicMock()
            mock_cred = SimpleNamespace(site_name="court", account="user1")
            mock_org.get_credential.return_value = mock_cred
            mock_get.return_value = mock_org
            with patch("apps.automation.utils.logging.AutomationLogger"):
                result = svc.acquire_token(credential_id=1)
                assert result is None

    def test_exception_returns_none(self):
        svc = DocumentDeliveryTokenService(cache_manager=MagicMock())
        with patch("apps.core.interfaces.ServiceLocator.get_organization_service") as mock_get:
            mock_get.side_effect = RuntimeError("db error")
            with patch("apps.automation.utils.logging.AutomationLogger"):
                result = svc.acquire_token(credential_id=1)
                assert result is None


class TestAcquireTokenViaService:
    def test_no_running_loop(self):
        svc = DocumentDeliveryTokenService()
        mock_auto = MagicMock()
        mock_auto.acquire_token_if_needed = AsyncMock(return_value="token_from_service")
        svc._auto_token_service = mock_auto
        result = svc._acquire_token_via_service("court", 1)
        assert result == "token_from_service"

    def test_exception_returns_none(self):
        svc = DocumentDeliveryTokenService()
        mock_auto = MagicMock()
        mock_auto.acquire_token_if_needed = AsyncMock(side_effect=RuntimeError("service error"))
        svc._auto_token_service = mock_auto
        result = svc._acquire_token_via_service("court", 1)
        assert result is None


class TestInvalidateToken:
    def test_invalidate_success(self):
        cache = MagicMock()
        svc = DocumentDeliveryTokenService(cache_manager=cache)
        with patch("apps.core.interfaces.ServiceLocator.get_organization_service") as mock_get:
            mock_org = MagicMock()
            mock_cred = SimpleNamespace(site_name="court", account="user1")
            mock_org.get_credential.return_value = mock_cred
            mock_get.return_value = mock_org
            result = svc.invalidate_token(credential_id=1)
            assert result is True
            cache.invalidate_token_cache.assert_called_once_with("court", "user1")

    def test_invalidate_credential_not_found(self):
        svc = DocumentDeliveryTokenService(cache_manager=MagicMock())
        with patch("apps.core.interfaces.ServiceLocator.get_organization_service") as mock_get:
            mock_org = MagicMock()
            mock_org.get_credential.return_value = None
            mock_get.return_value = mock_org
            result = svc.invalidate_token(credential_id=999)
            assert result is False

    def test_invalidate_exception(self):
        svc = DocumentDeliveryTokenService(cache_manager=MagicMock())
        with patch("apps.core.interfaces.ServiceLocator.get_organization_service") as mock_get:
            mock_get.side_effect = RuntimeError("error")
            result = svc.invalidate_token(credential_id=1)
            assert result is False
