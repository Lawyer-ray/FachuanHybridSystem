"""Tests for core/services/business_config_service.py and core/config/business_config.py.

Covers: BusinessConfigService all methods, BusinessConfig singleton, stage/status queries,
label lookups, validity checks, compatible statuses, cache invalidation.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.services.business_config_service import BusinessConfigService


class TestBusinessConfigServiceLazyConfig:
    def test_init_no_config(self):
        svc = BusinessConfigService(config=None)
        assert svc._config_instance is None

    def test_init_with_config(self):
        mock_config = MagicMock()
        svc = BusinessConfigService(config=mock_config)
        assert svc._config_instance is mock_config


class TestBusinessConfigServiceMethods:
    """Test all BusinessConfigService methods with a mock config."""

    def setup_method(self):
        self.mock_config = MagicMock()
        self.svc = BusinessConfigService(config=self.mock_config)

    def test_get_stages_for_case_type(self):
        self.mock_config.get_stages_for_case_type.return_value = [("civil", "Civil")]
        result = self.svc.get_stages_for_case_type("civil")
        self.mock_config.get_stages_for_case_type.assert_called_once_with("civil")
        assert result == [("civil", "Civil")]

    def test_get_legal_statuses_for_case_type(self):
        self.mock_config.get_legal_statuses_for_case_type.return_value = [("plaintiff", "Plaintiff")]
        result = self.svc.get_legal_statuses_for_case_type("civil")
        assert result == [("plaintiff", "Plaintiff")]

    def test_get_stage_label(self):
        self.mock_config.get_stage_label.return_value = "一审"
        result = self.svc.get_stage_label("first_trial")
        self.mock_config.get_stage_label.assert_called_once_with("first_trial")
        assert result == "一审"

    def test_get_legal_status_label(self):
        self.mock_config.get_legal_status_label.return_value = "原告"
        result = self.svc.get_legal_status_label("plaintiff")
        assert result == "原告"

    def test_is_stage_valid_for_case_type(self):
        self.mock_config.is_stage_valid_for_case_type.return_value = True
        result = self.svc.is_stage_valid_for_case_type("first_trial", "civil")
        self.mock_config.is_stage_valid_for_case_type.assert_called_once_with("first_trial", "civil")
        assert result is True

    def test_is_legal_status_valid_for_case_type(self):
        self.mock_config.is_legal_status_valid_for_case_type.return_value = False
        result = self.svc.is_legal_status_valid_for_case_type("plaintiff", "criminal")
        assert result is False

    def test_get_compatible_legal_statuses(self):
        self.mock_config.get_compatible_legal_statuses.return_value = [("plaintiff", "原告")]
        result = self.svc.get_compatible_legal_statuses(["defendant"], "civil")
        self.mock_config.get_compatible_legal_statuses.assert_called_once_with(["defendant"], "civil")
        assert result == [("plaintiff", "原告")]

    def test_is_legal_status_compatible(self):
        self.mock_config.is_legal_status_compatible.return_value = True
        result = self.svc.is_legal_status_compatible("plaintiff", ["defendant"])
        assert result is True

    def test_internal_methods_delegate(self):
        self.mock_config.get_stages_for_case_type.return_value = []
        self.svc.get_stages_for_case_type_internal("civil")
        self.mock_config.get_stages_for_case_type.assert_called_once_with("civil")

    def test_internal_legal_statuses(self):
        self.mock_config.get_legal_statuses_for_case_type.return_value = []
        self.svc.get_legal_statuses_for_case_type_internal(None)
        self.mock_config.get_legal_statuses_for_case_type.assert_called_once_with(None)


class TestBusinessConfigReal:
    """Test the real BusinessConfig class.

    Note: BusinessConfig methods are decorated with @cached which may
    interfere with testing. We patch the cache decorator to be a no-op
    for deterministic results.
    """

    @pytest.fixture(autouse=True)
    def _patch_cache(self):
        """Disable caching decorator to test real logic."""
        from unittest.mock import patch as _patch

        def _noop_decorator(*args, **kwargs):
            def wrapper(fn):
                return fn
            return wrapper if args and callable(args[0]) else wrapper

        with _patch("apps.core.config.business_config.cached", _noop_decorator):
            # Reset singleton to pick up patched decorator
            from apps.core.config.business_config import BusinessConfig
            BusinessConfig._instance = None
            yield
            BusinessConfig._instance = None

    def test_singleton(self):
        from apps.core.config.business_config import BusinessConfig

        a = BusinessConfig()
        b = BusinessConfig()
        assert a is b

    def test_get_stages_for_case_type_none(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        stages = bc.get_stages_for_case_type(None)
        # When case_type is None, only stages with empty applicable_case_types are returned
        assert isinstance(stages, list)

    def test_get_stages_for_civil(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        stages = bc.get_stages_for_case_type("civil")
        values = [s[0] for s in stages]
        assert "first_trial" in values
        assert "labor_arbitration" not in values

    def test_get_stages_for_labor(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        stages = bc.get_stages_for_case_type("labor")
        values = [s[0] for s in stages]
        assert "labor_arbitration" in values
        assert "first_trial" not in values

    def test_get_legal_statuses_for_civil(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        statuses = bc.get_legal_statuses_for_case_type("civil")
        values = [s[0] for s in statuses]
        assert "plaintiff" in values
        assert "criminal_defendant" not in values

    def test_get_legal_statuses_none(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        statuses = bc.get_legal_statuses_for_case_type(None)
        assert isinstance(statuses, list)

    def test_get_stage_label_known(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        assert bc.get_stage_label("first_trial") == "一审"

    def test_get_stage_label_unknown(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        assert bc.get_stage_label("unknown_stage") == "unknown_stage"

    def test_get_legal_status_label_known(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        assert bc.get_legal_status_label("plaintiff") == "原告"

    def test_get_legal_status_label_unknown(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        assert bc.get_legal_status_label("unknown") == "unknown"

    def test_is_stage_valid_for_case_type_true(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        assert bc.is_stage_valid_for_case_type("first_trial", "civil") is True

    def test_is_stage_valid_for_case_type_false(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        assert bc.is_stage_valid_for_case_type("labor_arbitration", "civil") is False

    def test_is_stage_valid_unknown_stage(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        assert bc.is_stage_valid_for_case_type("nonexistent", "civil") is False

    def test_is_stage_valid_none_case_type(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        # None case_type should return True for stages that have applicable types
        assert bc.is_stage_valid_for_case_type("first_trial", None) is True

    def test_is_stage_valid_no_applicable_types(self):
        from apps.core.config.business_config import BusinessConfig
        from apps.core.config.business_config import StageConfig, CASE_STAGES

        bc = BusinessConfig()
        # Find a stage with no applicable_case_types (should return True for any case_type)
        for s in CASE_STAGES:
            if not s.applicable_case_types:
                assert bc.is_stage_valid_for_case_type(s.value, "civil") is True
                return
        pytest.skip("No stage with empty applicable_case_types")

    def test_is_legal_status_valid_for_case_type(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        assert bc.is_legal_status_valid_for_case_type("plaintiff", "civil") is True
        assert bc.is_legal_status_valid_for_case_type("plaintiff", "criminal") is False

    def test_is_legal_status_valid_unknown(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        assert bc.is_legal_status_valid_for_case_type("nonexistent", "civil") is False

    def test_is_legal_status_valid_none_case_type(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        assert bc.is_legal_status_valid_for_case_type("plaintiff", None) is True

    def test_is_legal_status_valid_no_applicable_types(self):
        from apps.core.config.business_config import BusinessConfig, LEGAL_STATUSES

        bc = BusinessConfig()
        for s in LEGAL_STATUSES:
            if not s.applicable_case_types:
                assert bc.is_legal_status_valid_for_case_type(s.value, "civil") is True
                return
        pytest.skip("No legal status with empty applicable_case_types")

    def test_invalidate_config_cache(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        with patch("apps.core.config.business_config.invalidate_cache") as mock_inv:
            bc.invalidate_config_cache("civil")
            assert mock_inv.call_count == 2

    def test_invalidate_config_cache_all(self):
        from apps.core.config.business_config import BusinessConfig

        bc = BusinessConfig()
        with patch("apps.core.config.business_config.invalidate_cache") as mock_inv:
            bc.invalidate_config_cache(None)
            assert mock_inv.call_count == 2
