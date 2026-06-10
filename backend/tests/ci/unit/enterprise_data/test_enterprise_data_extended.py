"""Extended tests for enterprise_data services - metrics_service, provider_registry, types."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.enterprise_data.services.metrics_service import EnterpriseDataMetricsService
from apps.enterprise_data.services.types import (
    DEFAULT_ALERT_AVG_LATENCY_MS_THRESHOLD,
    DEFAULT_ALERT_FALLBACK_RATE_THRESHOLD,
    DEFAULT_ALERT_MIN_SAMPLES,
    DEFAULT_ALERT_SUCCESS_RATE_THRESHOLD,
    DEFAULT_METRICS_WINDOW_SECONDS,
    DEFAULT_RISK_TYPE,
)


class TestEnterpriseDataMetricsService:
    def test_init_defaults(self):
        svc = EnterpriseDataMetricsService()
        assert svc._window_seconds >= 60

    def test_init_custom(self):
        svc = EnterpriseDataMetricsService(window_seconds=300, alert_min_samples=5)
        assert svc._window_seconds == 300
        assert svc._alert_min_samples == 5

    @patch("apps.enterprise_data.services.metrics_service.cache")
    def test_record_new_bucket(self, mock_cache):
        mock_cache.get.return_value = None
        mock_cache.add.return_value = True
        svc = EnterpriseDataMetricsService()
        snapshot = svc.record(
            provider="qichacha",
            capability="search",
            success=True,
            duration_ms=100,
            fallback_used=False,
        )
        assert snapshot["total"] == 1
        assert snapshot["success"] == 1
        assert snapshot["failure"] == 0

    @patch("apps.enterprise_data.services.metrics_service.cache")
    def test_record_failure(self, mock_cache):
        mock_cache.get.return_value = None
        mock_cache.add.return_value = True
        svc = EnterpriseDataMetricsService()
        snapshot = svc.record(
            provider="qichacha",
            capability="search",
            success=False,
            duration_ms=200,
            fallback_used=False,
        )
        assert snapshot["failure"] == 1

    @patch("apps.enterprise_data.services.metrics_service.cache")
    def test_record_with_fallback(self, mock_cache):
        mock_cache.get.return_value = None
        mock_cache.add.return_value = True
        svc = EnterpriseDataMetricsService()
        snapshot = svc.record(
            provider="qichacha",
            capability="search",
            success=True,
            duration_ms=100,
            fallback_used=True,
        )
        assert snapshot["fallback"] == 1

    @patch("apps.enterprise_data.services.metrics_service.cache")
    def test_snapshot_empty(self, mock_cache):
        mock_cache.get.return_value = None
        svc = EnterpriseDataMetricsService()
        assert svc.snapshot(provider="qichacha", capability="search") is None

    @patch("apps.enterprise_data.services.metrics_service.cache")
    def test_snapshot_with_data(self, mock_cache):
        mock_cache.get.return_value = {
            "window_start": 1000,
            "window_end": 1300,
            "total": 10,
            "success": 8,
            "failure": 2,
            "fallback": 1,
            "duration_sum_ms": 1000,
            "updated_at": 1100,
        }
        svc = EnterpriseDataMetricsService()
        snapshot = svc.snapshot(provider="qichacha", capability="search")
        assert snapshot is not None
        assert snapshot["total"] == 10
        assert snapshot["success"] == 8

    def test_snapshot_from_bucket(self):
        svc = EnterpriseDataMetricsService()
        bucket = {
            "window_start": 1000,
            "window_end": 1300,
            "total": 5,
            "success": 4,
            "failure": 1,
            "fallback": 0,
            "duration_sum_ms": 500,
        }
        snapshot = svc._snapshot_from_bucket(bucket)
        assert snapshot["total"] == 5
        assert snapshot["success_rate"] == 0.8
        assert snapshot["avg_duration_ms"] == 100

    def test_snapshot_from_empty_bucket(self):
        svc = EnterpriseDataMetricsService()
        bucket = {
            "window_start": 1000,
            "window_end": 1300,
            "total": 0,
            "success": 0,
            "failure": 0,
            "fallback": 0,
            "duration_sum_ms": 0,
        }
        snapshot = svc._snapshot_from_bucket(bucket)
        assert snapshot["success_rate"] == 1.0
        assert snapshot["avg_duration_ms"] == 0

    def test_new_bucket(self):
        svc = EnterpriseDataMetricsService()
        bucket = svc._new_bucket(1000)
        assert bucket["window_start"] == 1000
        assert bucket["total"] == 0

    def test_bucket_key(self):
        key = EnterpriseDataMetricsService._bucket_key(provider="qichacha", capability="search")
        assert "qichacha" in key
        assert "search" in key


class TestEnterpriseDataTypes:
    def test_default_risk_type(self):
        assert isinstance(DEFAULT_RISK_TYPE, str)
        assert len(DEFAULT_RISK_TYPE) > 0

    def test_default_constants(self):
        assert DEFAULT_METRICS_WINDOW_SECONDS > 0
        assert DEFAULT_ALERT_MIN_SAMPLES > 0
        assert 0 < DEFAULT_ALERT_SUCCESS_RATE_THRESHOLD <= 1.0


class TestProviderResponse:
    def test_import(self):
        from apps.enterprise_data.services.types import ProviderResponse

        assert ProviderResponse is not None


class TestEnterpriseDataService:
    def test_build_cache_key(self):
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        key = EnterpriseDataService._build_cache_key(
            provider="test",
            capability="search",
            query={"keyword": "test"},
        )
        assert isinstance(key, str)
        assert key.startswith("enterprise_data:")

    def test_build_cache_key_deterministic(self):
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        key1 = EnterpriseDataService._build_cache_key(
            provider="test", capability="search", query={"keyword": "abc"}
        )
        key2 = EnterpriseDataService._build_cache_key(
            provider="test", capability="search", query={"keyword": "abc"}
        )
        assert key1 == key2

    def test_build_query_payload(self):
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService
        from apps.enterprise_data.services.types import ProviderResponse

        response = ProviderResponse(data={"name": "test"}, tool="search_company", raw=None, meta={"duration_ms": 100})
        payload = EnterpriseDataService._build_query_payload(
            provider="qichacha",
            transport="http",
            capability="search",
            query={"keyword": "test"},
            response=response,
            include_raw=False,
        )
        assert payload["data"] == {"name": "test"}
        assert payload["meta"]["provider"] == "qichacha"
        assert payload["raw"] is None

    def test_build_query_payload_with_raw(self):
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService
        from apps.enterprise_data.services.types import ProviderResponse

        response = ProviderResponse(data={"name": "test"}, tool="search_company", raw={"raw_data": True}, meta={})
        payload = EnterpriseDataService._build_query_payload(
            provider="qichacha",
            transport="http",
            capability="search",
            query={"keyword": "test"},
            response=response,
            include_raw=True,
        )
        assert payload["raw"] == {"raw_data": True}

    @patch("apps.enterprise_data.services.enterprise_data_service.cache")
    def test_search_companies_empty_keyword_raises(self, mock_cache):
        from apps.core.exceptions import ValidationException
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        svc = EnterpriseDataService()
        with pytest.raises(ValidationException):
            svc.search_companies(keyword="")

    @patch("apps.enterprise_data.services.enterprise_data_service.cache")
    def test_get_company_profile_empty_id_raises(self, mock_cache):
        from apps.core.exceptions import ValidationException
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        svc = EnterpriseDataService()
        with pytest.raises(ValidationException):
            svc.get_company_profile(company_id="")

    @patch("apps.enterprise_data.services.enterprise_data_service.cache")
    def test_get_company_risks_empty_id_raises(self, mock_cache):
        from apps.core.exceptions import ValidationException
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        svc = EnterpriseDataService()
        with pytest.raises(ValidationException):
            svc.get_company_risks(company_id="")

    @patch("apps.enterprise_data.services.enterprise_data_service.cache")
    def test_get_company_shareholders_empty_id_raises(self, mock_cache):
        from apps.core.exceptions import ValidationException
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        svc = EnterpriseDataService()
        with pytest.raises(ValidationException):
            svc.get_company_shareholders(company_id="")

    @patch("apps.enterprise_data.services.enterprise_data_service.cache")
    def test_get_company_personnel_empty_id_raises(self, mock_cache):
        from apps.core.exceptions import ValidationException
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        svc = EnterpriseDataService()
        with pytest.raises(ValidationException):
            svc.get_company_personnel(company_id="")

    @patch("apps.enterprise_data.services.enterprise_data_service.cache")
    def test_get_person_profile_empty_hcgid_raises(self, mock_cache):
        from apps.core.exceptions import ValidationException
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        svc = EnterpriseDataService()
        with pytest.raises(ValidationException):
            svc.get_person_profile(hcgid="")

    @patch("apps.enterprise_data.services.enterprise_data_service.cache")
    def test_search_bidding_info_empty_keyword_raises(self, mock_cache):
        from apps.core.exceptions import ValidationException
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        svc = EnterpriseDataService()
        with pytest.raises(ValidationException):
            svc.search_bidding_info(keyword="")

    @patch("apps.enterprise_data.services.enterprise_data_service.cache")
    def test_search_bidding_info_invalid_search_type_raises(self, mock_cache):
        from apps.core.exceptions import ValidationException
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        svc = EnterpriseDataService()
        with pytest.raises(ValidationException):
            svc.search_bidding_info(keyword="test", search_type=99)

    @patch("apps.enterprise_data.services.enterprise_data_service.cache")
    def test_search_bidding_info_invalid_bid_type_raises(self, mock_cache):
        from apps.core.exceptions import ValidationException
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        svc = EnterpriseDataService()
        with pytest.raises(ValidationException):
            svc.search_bidding_info(keyword="test", bid_type=99)

    @patch("apps.enterprise_data.services.enterprise_data_service.cache")
    def test_search_bidding_info_invalid_date_range_raises(self, mock_cache):
        from datetime import date

        from apps.core.exceptions import ValidationException
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        svc = EnterpriseDataService()
        with pytest.raises(ValidationException):
            svc.search_bidding_info(
                keyword="test",
                start_date=date(2025, 12, 31),
                end_date=date(2025, 1, 1),
            )

    def test_read_registry_int(self):
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        svc = EnterpriseDataService()
        # Default case when registry doesn't have the method
        result = svc._read_registry_int("nonexistent_method", 42)
        assert result == 42

    def test_read_registry_float(self):
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        svc = EnterpriseDataService()
        result = svc._read_registry_float("nonexistent_method", 0.5)
        assert result == 0.5
