"""Tests for documents generation result, outputs, base placeholder service, and fallback module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.documents.services.generation.result import GenerationResult
from apps.documents.services.generation.outputs import (
    ComplaintOutput,
    DefenseOutput,
    ExecutionRequestOutput,
    PartyInfo,
)
from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.fallback import (
    PLACEHOLDER_FALLBACK_VALUE,
    build_docx_render_context,
    ensure_required_placeholders,
    get_service_placeholder_keys,
    normalize_placeholder_value,
    normalize_service_result,
    resolve_render_variable,
)
from apps.documents.services.placeholders.types import PlaceholderContextData


# ---------------------------------------------------------------------------
# GenerationResult
# ---------------------------------------------------------------------------


class TestGenerationResult:
    def test_success(self) -> None:
        r = GenerationResult(success=True, file_path="/path/doc.pdf", file_name="doc.pdf")
        assert r.success is True
        assert r.file_path == "/path/doc.pdf"
        assert r.duration_ms == 0

    def test_success_without_path_raises(self) -> None:
        with pytest.raises(ValueError, match="文件路径"):
            GenerationResult(success=True)

    def test_failure_with_error(self) -> None:
        r = GenerationResult(success=False, error_message="something failed")
        assert r.success is False
        assert r.error_message == "something failed"

    def test_failure_without_error_raises(self) -> None:
        with pytest.raises(ValueError, match="错误信息"):
            GenerationResult(success=False)

    def test_negative_duration_raises(self) -> None:
        with pytest.raises(ValueError, match="不能为负数"):
            GenerationResult(success=True, file_path="/path", duration_ms=-1)


# ---------------------------------------------------------------------------
# Pydantic outputs
# ---------------------------------------------------------------------------


class TestPartyInfo:
    def test_create(self) -> None:
        p = PartyInfo(name="Zhang San", role="原告")
        assert p.name == "Zhang San"
        assert p.id_number == ""
        assert p.address == ""


class TestComplaintOutput:
    def test_create(self) -> None:
        c = ComplaintOutput(
            title="起诉状",
            parties=[PartyInfo(name="Zhang", role="原告")],
            litigation_request="请求法院判令",
            facts_and_reasons="事实与理由",
        )
        assert c.title == "起诉状"
        assert c.evidence == []


class TestDefenseOutput:
    def test_create(self) -> None:
        d = DefenseOutput(
            title="答辩状",
            parties=[PartyInfo(name="Li", role="被告")],
            defense_opinion="不同意",
            defense_reasons="理由",
        )
        assert d.title == "答辩状"
        assert d.evidence == []


class TestExecutionRequestOutput:
    def test_defaults(self) -> None:
        e = ExecutionRequestOutput()
        assert e.principal is None
        assert e.confirmed_interest == 0
        assert e.attorney_fee == 0
        assert e.rate_type == "lpr"

    def test_with_values(self) -> None:
        e = ExecutionRequestOutput(principal=100000, attorney_fee=5000, rate_type="fixed", fixed_rate=4.5)
        assert e.principal == 100000
        assert e.rate_type == "fixed"


# ---------------------------------------------------------------------------
# BasePlaceholderService
# ---------------------------------------------------------------------------


class TestBasePlaceholderService:
    def test_abstract(self) -> None:
        with pytest.raises(TypeError):
            BasePlaceholderService()  # type: ignore[abstract]

    def test_concrete_subclass(self) -> None:
        class MyService(BasePlaceholderService):
            name = "test"
            placeholder_keys = ["key1", "key2"]

            def generate(self, context_data: dict) -> dict:
                return {"key1": "v1"}

        svc = MyService()
        assert svc.get_placeholder_keys() == ["key1", "key2"]
        assert str(svc) == "MyService(test)"
        assert repr(svc) == "<MyService: test>"

    def test_get_placeholder_metadata(self) -> None:
        class MyService(BasePlaceholderService):
            name = "test"
            placeholder_metadata = {"key1": {"desc": "test key"}}

            def generate(self, context_data: dict) -> dict:
                return {}

        svc = MyService()
        meta = svc.get_placeholder_metadata()
        assert "key1" in meta


# ---------------------------------------------------------------------------
# Fallback module
# ---------------------------------------------------------------------------


class TestNormalizePlaceholderValue:
    def test_none_returns_fallback(self) -> None:
        assert normalize_placeholder_value(None) == PLACEHOLDER_FALLBACK_VALUE

    def test_empty_string_returns_fallback(self) -> None:
        assert normalize_placeholder_value("") == PLACEHOLDER_FALLBACK_VALUE

    def test_whitespace_string_returns_fallback(self) -> None:
        assert normalize_placeholder_value("   ") == PLACEHOLDER_FALLBACK_VALUE

    def test_valid_value_returned(self) -> None:
        assert normalize_placeholder_value("hello") == "hello"

    def test_non_string_returned(self) -> None:
        assert normalize_placeholder_value(42) == 42

    def test_custom_fallback(self) -> None:
        assert normalize_placeholder_value(None, fallback_value="N/A") == "N/A"


class TestGetServicePlaceholderKeys:
    def test_with_getter_method(self) -> None:
        svc = MagicMock()
        svc.get_placeholder_keys.return_value = ["k1", "k2"]
        assert get_service_placeholder_keys(svc) == ["k1", "k2"]

    def test_with_attribute(self) -> None:
        svc = MagicMock(spec=[])
        svc.placeholder_keys = ["a1", "a2"]
        assert get_service_placeholder_keys(svc) == ["a1", "a2"]

    def test_with_empty_keys(self) -> None:
        svc = MagicMock(spec=[])
        svc.placeholder_keys = []
        assert get_service_placeholder_keys(svc) == []

    def test_with_string_keys_returns_empty(self) -> None:
        svc = MagicMock(spec=[])
        svc.placeholder_keys = "not_a_list"
        assert get_service_placeholder_keys(svc) == []

    def test_filters_empty_strings(self) -> None:
        svc = MagicMock(spec=[])
        svc.placeholder_keys = ["k1", "", "  ", "k2"]
        result = get_service_placeholder_keys(svc)
        assert result == ["k1", "k2"]


class TestNormalizeServiceResult:
    def test_none_result(self) -> None:
        result = normalize_service_result(None, expected_keys=["k1"])
        assert result == {"k1": PLACEHOLDER_FALLBACK_VALUE}

    def test_with_values(self) -> None:
        result = normalize_service_result({"k1": "v1", "k2": ""}, expected_keys=["k1", "k2", "k3"])
        assert result["k1"] == "v1"
        assert result["k2"] == PLACEHOLDER_FALLBACK_VALUE  # empty string
        assert result["k3"] == PLACEHOLDER_FALLBACK_VALUE  # missing

    def test_custom_fallback(self) -> None:
        result = normalize_service_result({}, expected_keys=["k"], fallback_value="N/A")
        assert result["k"] == "N/A"


class TestEnsureRequiredPlaceholders:
    def test_basic(self) -> None:
        result = ensure_required_placeholders({"k1": "v1"}, ["k1", "k2"])
        assert result["k1"] == "v1"
        assert result["k2"] == PLACEHOLDER_FALLBACK_VALUE

    def test_none_value_normalized(self) -> None:
        result = ensure_required_placeholders({"k1": None}, ["k1"])
        assert result["k1"] == PLACEHOLDER_FALLBACK_VALUE

    def test_no_required(self) -> None:
        result = ensure_required_placeholders({"k1": "v1"}, None)
        assert result["k1"] == "v1"


class TestResolveRenderVariable:
    def test_found(self) -> None:
        found, val = resolve_render_variable({"key": "value"}, "key")
        assert found is True
        assert val == "value"

    def test_not_found(self) -> None:
        found, val = resolve_render_variable({}, "missing")
        assert found is False
        assert val == PLACEHOLDER_FALLBACK_VALUE

    def test_none_value(self) -> None:
        found, val = resolve_render_variable({"key": None}, "key")
        assert found is False
        assert val == PLACEHOLDER_FALLBACK_VALUE


class TestBuildDocxRenderContext:
    def test_with_doc_getter(self) -> None:
        doc = MagicMock()
        doc.get_undeclared_template_variables.return_value = {"missing_key"}
        result = build_docx_render_context(doc=doc, context={"known": "val"})
        assert result["known"] == "val"
        assert result["missing_key"] == PLACEHOLDER_FALLBACK_VALUE

    def test_without_doc_getter(self) -> None:
        doc = MagicMock(spec=[])  # no get_undeclared_template_variables
        result = build_docx_render_context(doc=doc, context={"k": "v"})
        assert result["k"] == "v"

    def test_getter_raises_type_error(self) -> None:
        doc = MagicMock()
        doc.get_undeclared_template_variables.side_effect = TypeError("bad sig")
        # Should fall back to calling with positional arg
        doc.get_undeclared_template_variables.return_value = set()
        result = build_docx_render_context(doc=doc, context={"k": "v"})
        assert "k" in result

    def test_getter_returns_non_set(self) -> None:
        doc = MagicMock()
        doc.get_undeclared_template_variables.return_value = "not a set"
        result = build_docx_render_context(doc=doc, context={"k": "v"})
        assert "k" in result


class TestPlaceholderContextData:
    def test_typed_dict(self) -> None:
        data: PlaceholderContextData = {"contract_id": 1, "case_id": 2}
        assert data["contract_id"] == 1
