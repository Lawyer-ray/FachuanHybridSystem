"""Coverage tests for document_delivery_coordinator."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.document_delivery.coordinator.document_delivery_coordinator import (
    DocumentDeliveryCoordinator,
)


class TestCoordinatorInit:
    def test_init_defaults(self):
        coord = DocumentDeliveryCoordinator()
        assert coord._token_service is None
        assert coord._api_service is None
        assert coord._playwright_service is None
        assert coord._processor is None

    def test_init_with_injection(self):
        ts = MagicMock()
        api = MagicMock()
        pw = MagicMock()
        proc = MagicMock()
        coord = DocumentDeliveryCoordinator(
            token_service=ts, api_service=api, playwright_service=pw, processor=proc,
        )
        assert coord._token_service is ts
        assert coord._api_service is api
        assert coord._playwright_service is pw
        assert coord._processor is proc


class TestPropertyLazyLoad:
    def test_token_service_property_inject(self):
        ts = MagicMock()
        coord = DocumentDeliveryCoordinator(token_service=ts)
        assert coord.token_service is ts

    def test_api_service_property_inject(self):
        api = MagicMock()
        coord = DocumentDeliveryCoordinator(api_service=api)
        assert coord.api_service is api

    def test_playwright_service_property_inject(self):
        pw = MagicMock()
        coord = DocumentDeliveryCoordinator(playwright_service=pw)
        assert coord.playwright_service is pw

    def test_processor_property_inject(self):
        proc = MagicMock()
        coord = DocumentDeliveryCoordinator(processor=proc)
        assert coord.processor is proc


class TestQueryAndDownload:
    def test_api_approach_succeeds(self):
        ts = MagicMock()
        api = MagicMock()
        pw = MagicMock()
        result = MagicMock()
        ts.acquire_token.return_value = "token123"
        api.query_documents.return_value = result
        coord = DocumentDeliveryCoordinator(token_service=ts, api_service=api, playwright_service=pw)
        cutoff = datetime(2025, 1, 1)
        ret = coord.query_and_download(credential_id=1, cutoff_time=cutoff)
        assert ret is result
        pw.query_documents.assert_not_called()

    def test_api_approach_fails_falls_back_to_playwright(self):
        ts = MagicMock()
        api = MagicMock()
        pw = MagicMock()
        ts.acquire_token.return_value = None
        pw_result = MagicMock()
        pw.query_documents.return_value = pw_result
        coord = DocumentDeliveryCoordinator(token_service=ts, api_service=api, playwright_service=pw)
        cutoff = datetime(2025, 1, 1)
        ret = coord.query_and_download(credential_id=1, cutoff_time=cutoff, tab="reviewed", debug_mode=False)
        assert ret is pw_result
        pw.query_documents.assert_called_once_with(
            credential_id=1, cutoff_time=cutoff, tab="reviewed", debug_mode=False,
        )

    def test_api_exception_falls_back_to_playwright(self):
        ts = MagicMock()
        api = MagicMock()
        pw = MagicMock()
        ts.acquire_token.side_effect = RuntimeError("token error")
        pw_result = MagicMock()
        pw.query_documents.return_value = pw_result
        coord = DocumentDeliveryCoordinator(token_service=ts, api_service=api, playwright_service=pw)
        cutoff = datetime(2025, 1, 1)
        with patch("apps.automation.services.document_delivery.coordinator.document_delivery_coordinator.AutomationLogger"):
            ret = coord.query_and_download(credential_id=1, cutoff_time=cutoff)
        assert ret is pw_result


class TestTryApiApproach:
    def test_token_success_api_success(self):
        ts = MagicMock()
        api = MagicMock()
        result = MagicMock()
        result.total_found = 5
        result.processed_count = 3
        result.skipped_count = 1
        result.failed_count = 1
        ts.acquire_token.return_value = "token123"
        api.query_documents.return_value = result
        coord = DocumentDeliveryCoordinator(token_service=ts, api_service=api)
        with patch("apps.automation.services.document_delivery.coordinator.document_delivery_coordinator.AutomationLogger"):
            ret = coord._try_api_approach(1, datetime(2025, 1, 1))
        assert ret is result

    def test_token_none_returns_none(self):
        ts = MagicMock()
        ts.acquire_token.return_value = None
        coord = DocumentDeliveryCoordinator(token_service=ts)
        with patch("apps.automation.services.document_delivery.coordinator.document_delivery_coordinator.AutomationLogger"):
            ret = coord._try_api_approach(1, datetime(2025, 1, 1))
        assert ret is None

    def test_api_exception_returns_none(self):
        ts = MagicMock()
        api = MagicMock()
        ts.acquire_token.return_value = "token123"
        api.query_documents.side_effect = RuntimeError("api error")
        coord = DocumentDeliveryCoordinator(token_service=ts, api_service=api)
        with patch("apps.automation.services.document_delivery.coordinator.document_delivery_coordinator.AutomationLogger"):
            ret = coord._try_api_approach(1, datetime(2025, 1, 1))
        assert ret is None


class TestTryApiAfterLogin:
    def test_success(self):
        api = MagicMock()
        result = MagicMock()
        result.total_found = 2
        result.processed_count = 1
        result.skipped_count = 0
        result.failed_count = 1
        api.query_documents.return_value = result
        coord = DocumentDeliveryCoordinator(api_service=api)
        with patch("apps.automation.services.document_delivery.coordinator.document_delivery_coordinator.AutomationLogger"):
            ret = coord._try_api_after_login("token123", datetime(2025, 1, 1), credential_id=1)
        assert ret is result

    def test_exception_returns_none(self):
        api = MagicMock()
        api.query_documents.side_effect = RuntimeError("api error")
        coord = DocumentDeliveryCoordinator(api_service=api)
        with patch("apps.automation.services.document_delivery.coordinator.document_delivery_coordinator.AutomationLogger"):
            ret = coord._try_api_after_login("token123", datetime(2025, 1, 1), credential_id=1)
        assert ret is None
