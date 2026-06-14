"""补充覆盖测试: documents/services/placeholders/context_builder.py (36 missing)

覆盖: build_context (空数据/supplementary_agreement/服务异常),
_normalize_context_data, _get_relevant_services, get_available_placeholders,
validate_placeholders, build_contract_context 异常分支。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.documents.services.placeholders.context_builder import EnhancedContextBuilder
from apps.documents.services.placeholders.fallback import PLACEHOLDER_FALLBACK_VALUE


@dataclass
class _CaseStub:
    id: int


class _ServiceA:
    name = "service_a"
    category = "cat_a"
    placeholder_keys = ["key_a1", "key_a2"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        return {"key_a1": "val1", "key_a2": "val2"}

    def get_placeholder_keys(self) -> list[str]:
        return self.placeholder_keys


class _ServiceB:
    name = "service_b"
    category = "cat_b"
    placeholder_keys = ["key_b1"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        return {"key_b1": "val_b1"}

    def get_placeholder_keys(self) -> list[str]:
        return self.placeholder_keys


class _ErrorService:
    name = "error_service"
    category = "cat_err"
    placeholder_keys = ["key_err"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("service failure")

    def get_placeholder_keys(self) -> list[str]:
        return self.placeholder_keys


class _RegistryStub:
    def __init__(self, services: list[Any]) -> None:
        self._services = services

    def get_all_services(self) -> list[Any]:
        return self._services

    def get_service_for_placeholder(self, key: str) -> Any | None:
        for s in self._services:
            if key in getattr(s, "placeholder_keys", []):
                return s
        return None


# ── build_context: empty data ─────────────────────────────────────


class TestBuildContextEmptyData:
    def test_empty_dict_returns_empty(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([]))
        assert builder.build_context({}) == {}

    def test_none_returns_empty(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([]))
        assert builder.build_context(None) == {}


# ── build_context: normal flow ────────────────────────────────────


class TestBuildContextNormal:
    def test_multiple_services(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([_ServiceA(), _ServiceB()]))
        result = builder.build_context({"case": _CaseStub(id=1)})
        assert result["key_a1"] == "val1"
        assert result["key_b1"] == "val_b1"

    def test_service_exception_continues(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([_ErrorService(), _ServiceA()]))
        result = builder.build_context({"case": _CaseStub(id=1)})
        assert result["key_err"] == PLACEHOLDER_FALLBACK_VALUE
        assert result["key_a1"] == "val1"

    def test_with_required_placeholders(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([_ServiceA()]))
        result = builder.build_context(
            {"case": _CaseStub(id=1)},
            required_placeholders=["key_a1", "missing_key"],
        )
        assert result["key_a1"] == "val1"
        assert result["missing_key"] == PLACEHOLDER_FALLBACK_VALUE


# ── build_context: supplementary_agreement mapping ────────────────


class TestBuildContextSupplementaryAgreement:
    def test_supplementary_keys_mapped(self) -> None:
        class _SuppService:
            name = "supp"
            category = "supp_cat"
            placeholder_keys = ["补充协议委托人信息", "补充协议委托人签名盖章信息"]

            def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
                return {
                    "补充协议委托人信息": "person info",
                    "补充协议委托人签名盖章信息": "sig info",
                }

            def get_placeholder_keys(self) -> list[str]:
                return self.placeholder_keys

        builder = EnhancedContextBuilder(registry=_RegistryStub([_SuppService()]))
        result = builder.build_context({"supplementary_agreement": True, "case": _CaseStub(id=1)})
        assert result["补充协议委托人信息"] == "person info"
        assert result["委托人信息"] == "person info"
        assert result["委托人签名盖章信息"] == "sig info"

    def test_non_supplementary_no_mapping(self) -> None:
        class _SuppService:
            name = "supp"
            category = "supp_cat"
            placeholder_keys = ["补充协议委托人信息"]

            def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
                return {"补充协议委托人信息": "person info"}

            def get_placeholder_keys(self) -> list[str]:
                return self.placeholder_keys

        builder = EnhancedContextBuilder(registry=_RegistryStub([_SuppService()]))
        result = builder.build_context({"case": _CaseStub(id=1)})
        assert "补充协议委托人信息" in result
        # Without supplementary_agreement flag, no mapping occurs
        assert "委托人信息" not in result


# ── _normalize_context_data ───────────────────────────────────────


class TestNormalizeContextData:
    def test_infer_case_id_from_case_object(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([]))
        result = builder._normalize_context_data({"case": _CaseStub(id=42)})
        assert result["case_id"] == 42

    def test_keep_explicit_case_id(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([]))
        result = builder._normalize_context_data({"case": _CaseStub(id=42), "case_id": 99})
        assert result["case_id"] == 99

    def test_no_case_object(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([]))
        result = builder._normalize_context_data({"key": "value"})
        assert result.get("case_id") is None

    def test_case_object_without_id(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([]))
        result = builder._normalize_context_data({"case": object()})
        assert result.get("case_id") is None


# ── _get_relevant_services ────────────────────────────────────────


class TestGetRelevantServices:
    def test_no_required_returns_all(self) -> None:
        svc_a, svc_b = _ServiceA(), _ServiceB()
        builder = EnhancedContextBuilder(registry=_RegistryStub([svc_a, svc_b]))
        result = builder._get_relevant_services()
        assert len(result) == 2

    def test_filters_by_required(self) -> None:
        svc_a, svc_b = _ServiceA(), _ServiceB()
        builder = EnhancedContextBuilder(registry=_RegistryStub([svc_a, svc_b]))
        result = builder._get_relevant_services(required_placeholders=["key_a1"])
        assert len(result) == 1
        assert result[0] is svc_a

    def test_no_match_returns_empty(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([_ServiceA()]))
        result = builder._get_relevant_services(required_placeholders=["nonexistent"])
        assert result == []

    def test_deduplicates_services(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([_ServiceA()]))
        result = builder._get_relevant_services(required_placeholders=["key_a1", "key_a2"])
        assert len(result) == 1


# ── get_available_placeholders ─────────────────────────────────────


class TestGetAvailablePlaceholders:
    def test_groups_by_category(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([_ServiceA(), _ServiceB()]))
        result = builder.get_available_placeholders()
        assert "cat_a" in result
        assert "cat_b" in result
        assert set(result["cat_a"]) == {"key_a1", "key_a2"}
        assert set(result["cat_b"]) == {"key_b1"}


# ── validate_placeholders ─────────────────────────────────────────


class TestValidatePlaceholders:
    def test_valid_keys(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([_ServiceA()]))
        result = builder.validate_placeholders(["key_a1", "key_a2"])
        assert result["key_a1"] is True
        assert result["key_a2"] is True

    def test_invalid_keys(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([_ServiceA()]))
        result = builder.validate_placeholders(["nonexistent_key"])
        assert result["nonexistent_key"] is False

    def test_mixed(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([_ServiceA()]))
        result = builder.validate_placeholders(["key_a1", "missing_key"])
        assert result["key_a1"] is True
        assert result["missing_key"] is False

    def test_empty_list(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([_ServiceA()]))
        result = builder.validate_placeholders([])
        assert result == {}


# ── build_contract_context ────────────────────────────────────────


class TestBuildContractContext:
    def test_contract_not_found(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([]))
        with patch(
            "apps.documents.services.infrastructure.wiring.get_contract_service"
        ) as mock_get:
            mock_svc = MagicMock()
            mock_svc.get_contract_internal.return_value = None
            mock_get.return_value = mock_svc
            with pytest.raises(ValidationException, match="合同不存在"):
                builder.build_contract_context(999)

    def test_success(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([_ServiceA()]))
        with patch(
            "apps.documents.services.infrastructure.wiring.get_contract_service"
        ) as mock_get:
            mock_svc = MagicMock()
            mock_svc.get_contract_internal.return_value = {"name": "test"}
            mock_svc.get_contract_model_internal.return_value = MagicMock()
            mock_get.return_value = mock_svc
            result = builder.build_contract_context(1)
            assert isinstance(result, dict)

    def test_model_not_found(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([]))
        with patch(
            "apps.documents.services.infrastructure.wiring.get_contract_service"
        ) as mock_get:
            mock_svc = MagicMock()
            mock_svc.get_contract_internal.return_value = {"name": "test"}
            mock_svc.get_contract_model_internal.return_value = None
            mock_get.return_value = mock_svc
            with pytest.raises(ValidationException, match="合同不存在"):
                builder.build_contract_context(1)

    def test_generic_exception_wrapped(self) -> None:
        builder = EnhancedContextBuilder(registry=_RegistryStub([]))
        with patch(
            "apps.documents.services.infrastructure.wiring.get_contract_service",
            side_effect=RuntimeError("db error"),
        ):
            with pytest.raises(ValidationException, match="构建合同上下文失败"):
                builder.build_contract_context(1)
