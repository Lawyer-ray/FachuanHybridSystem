"""documents 模块真实执行测试 - 覆盖 placeholders/fallback, path_utils, generation/result, outputs, evidence 等。"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ============================================================
# documents/services/placeholders/fallback.py
# ============================================================


class TestPlaceholderFallback:
    def test_normalize_placeholder_value_none(self) -> None:
        from apps.documents.services.placeholders.fallback import normalize_placeholder_value

        assert normalize_placeholder_value(None) == "/"

    def test_normalize_placeholder_value_empty_str(self) -> None:
        from apps.documents.services.placeholders.fallback import normalize_placeholder_value

        assert normalize_placeholder_value("") == "/"
        assert normalize_placeholder_value("   ") == "/"

    def test_normalize_placeholder_value_nonempty(self) -> None:
        from apps.documents.services.placeholders.fallback import normalize_placeholder_value

        assert normalize_placeholder_value("hello") == "hello"
        assert normalize_placeholder_value(42) == 42

    def test_normalize_placeholder_value_custom_fallback(self) -> None:
        from apps.documents.services.placeholders.fallback import normalize_placeholder_value

        assert normalize_placeholder_value(None, fallback_value="N/A") == "N/A"

    def test_get_service_placeholder_keys_with_getter(self) -> None:
        from apps.documents.services.placeholders.fallback import get_service_placeholder_keys

        svc = MagicMock()
        svc.get_placeholder_keys.return_value = ["key1", "key2"]
        keys = get_service_placeholder_keys(svc)
        assert keys == ["key1", "key2"]

    def test_get_service_placeholder_keys_with_attr(self) -> None:
        from apps.documents.services.placeholders.fallback import get_service_placeholder_keys

        svc = SimpleNamespace(placeholder_keys=["a", "b"])
        keys = get_service_placeholder_keys(svc)
        assert keys == ["a", "b"]

    def test_get_service_placeholder_keys_empty(self) -> None:
        from apps.documents.services.placeholders.fallback import get_service_placeholder_keys

        svc = SimpleNamespace(placeholder_keys=[])
        assert get_service_placeholder_keys(svc) == []

    def test_normalize_service_result_basic(self) -> None:
        from apps.documents.services.placeholders.fallback import normalize_service_result

        result = normalize_service_result({"key1": "val1", "key2": None}, expected_keys=["key1", "key3"])
        assert result["key1"] == "val1"
        assert result["key2"] == "/"
        assert result["key3"] == "/"

    def test_normalize_service_result_none(self) -> None:
        from apps.documents.services.placeholders.fallback import normalize_service_result

        result = normalize_service_result(None, expected_keys=["k"])
        assert result["k"] == "/"

    def test_ensure_required_placeholders(self) -> None:
        from apps.documents.services.placeholders.fallback import ensure_required_placeholders

        ctx = {"a": "1", "b": None}
        result = ensure_required_placeholders(ctx, ["a", "b", "c"])
        assert result["a"] == "1"
        assert result["b"] == "/"
        assert result["c"] == "/"

    def test_resolve_render_variable_found(self) -> None:
        from apps.documents.services.placeholders.fallback import resolve_render_variable

        found, value = resolve_render_variable({"x": "hello"}, "x")
        assert found is True
        assert value == "hello"

    def test_resolve_render_variable_missing(self) -> None:
        from apps.documents.services.placeholders.fallback import resolve_render_variable

        found, value = resolve_render_variable({}, "x")
        assert found is False
        assert value == "/"

    def test_resolve_render_variable_none_value(self) -> None:
        from apps.documents.services.placeholders.fallback import resolve_render_variable

        found, value = resolve_render_variable({"x": None}, "x")
        assert found is False

    def test_build_docx_render_context(self) -> None:
        from apps.documents.services.placeholders.fallback import build_docx_render_context

        doc = MagicMock()
        doc.get_undeclared_template_variables.return_value = {"missing_var"}
        result = build_docx_render_context(doc=doc, context={"existing": "val"})
        assert result["existing"] == "val"
        assert result["missing_var"] == "/"


# ============================================================
# documents/services/placeholders/base.py
# ============================================================


class TestBasePlaceholderService:
    def test_get_placeholder_keys(self) -> None:
        from apps.documents.services.placeholders.base import BasePlaceholderService

        class TestService(BasePlaceholderService):
            name = "test"
            placeholder_keys = ["a", "b"]

            def generate(self, context_data):
                return {}

        svc = TestService()
        assert svc.get_placeholder_keys() == ["a", "b"]

    def test_str_repr(self) -> None:
        from apps.documents.services.placeholders.base import BasePlaceholderService

        class TestService(BasePlaceholderService):
            name = "test_svc"

            def generate(self, context_data):
                return {}

        svc = TestService()
        assert "test_svc" in str(svc)
        assert "test_svc" in repr(svc)

    def test_get_placeholder_metadata(self) -> None:
        from apps.documents.services.placeholders.base import BasePlaceholderService

        class TestService(BasePlaceholderService):
            name = "test"
            placeholder_metadata = {"k": {"type": "text"}}

            def generate(self, context_data):
                return {}

        svc = TestService()
        meta = svc.get_placeholder_metadata()
        assert meta["k"]["type"] == "text"


# ============================================================
# documents/services/placeholders/basic/date_service.py
# ============================================================


class TestDatePlaceholderService:
    def test_format_chinese_date(self) -> None:
        from apps.documents.services.placeholders.basic.date_service import DatePlaceholderService

        svc = DatePlaceholderService()
        result = svc.format_chinese_date(date(2026, 3, 8))
        assert result == "2026年03月08日"

    def test_format_chinese_date_none(self) -> None:
        from apps.documents.services.placeholders.basic.date_service import DatePlaceholderService

        svc = DatePlaceholderService()
        assert svc.format_chinese_date(None) == ""

    def test_generate_with_case_dates(self) -> None:
        from apps.documents.services.placeholders.basic.date_service import DatePlaceholderService

        svc = DatePlaceholderService()
        case = SimpleNamespace(specified_date=date(2026, 1, 1))
        result = svc.generate({"case": case})
        assert result["指定日期"] == "2026年01月01日"

    def test_generate_with_contract_dates(self) -> None:
        from apps.documents.services.placeholders.basic.date_service import DatePlaceholderService

        svc = DatePlaceholderService()
        contract = SimpleNamespace(
            signing_date=date(2026, 2, 15),
            start_date=date(2026, 3, 1),
            end_date=date(2027, 3, 1),
        )
        result = svc.generate({"contract": contract})
        assert result["签约日期"] == "2026年02月15日"
        assert result["开始日期"] == "2026年03月01日"
        assert result["结束日期"] == "2027年03月01日"

    def test_generate_empty_context(self) -> None:
        from apps.documents.services.placeholders.basic.date_service import DatePlaceholderService

        svc = DatePlaceholderService()
        result = svc.generate({})
        assert result["指定日期"] == ""
        assert result["签约日期"] == ""


# ============================================================
# documents/services/placeholders/basic/number_service.py
# ============================================================


class TestNumberPlaceholderService:
    def test_number_to_chinese_zero(self) -> None:
        from apps.documents.services.placeholders.basic.number_service import NumberPlaceholderService

        svc = NumberPlaceholderService()
        assert svc.number_to_chinese(0) == "零"
        assert svc.number_to_chinese(None) == "零"

    def test_number_to_chinese_basic(self) -> None:
        from apps.documents.services.placeholders.basic.number_service import NumberPlaceholderService

        svc = NumberPlaceholderService()
        result = svc.number_to_chinese(100)
        assert "壹" in result
        assert "元" in result

    def test_number_to_chinese_decimal(self) -> None:
        from apps.documents.services.placeholders.basic.number_service import NumberPlaceholderService

        svc = NumberPlaceholderService()
        result = svc.number_to_chinese(12.50)
        assert "角" in result

    def test_number_to_chinese_string_input(self) -> None:
        from apps.documents.services.placeholders.basic.number_service import NumberPlaceholderService

        svc = NumberPlaceholderService()
        result = svc.number_to_chinese("1000")
        assert "壹" in result

    def test_convert_decimal_part_zero(self) -> None:
        from apps.documents.services.placeholders.basic.number_service import NumberPlaceholderService

        svc = NumberPlaceholderService()
        assert svc._convert_decimal_part("00") == "整"

    def test_convert_decimal_part_jiao_fen(self) -> None:
        from apps.documents.services.placeholders.basic.number_service import NumberPlaceholderService

        svc = NumberPlaceholderService()
        result = svc._convert_decimal_part("56")
        assert "伍角" in result
        assert "陆分" in result


# ============================================================
# documents/services/placeholders/basic/year_service.py
# ============================================================


class TestYearPlaceholderService:
    def test_generate_year(self) -> None:
        from apps.documents.services.placeholders.basic.year_service import YearPlaceholderService

        svc = YearPlaceholderService()
        result = svc.generate({})
        assert result["年份"] == str(date.today().year)


# ============================================================
# documents/services/generation/path_utils.py
# ============================================================


class TestPathUtils:
    def test_resolve_media_path_empty(self) -> None:
        from apps.documents.services.generation.path_utils import resolve_media_path

        assert resolve_media_path("/media", "") == ""
        assert resolve_media_path("/media", "   ") == ""

    def test_resolve_media_path_http(self) -> None:
        from apps.documents.services.generation.path_utils import resolve_media_path

        assert resolve_media_path("/media", "https://example.com/file.pdf") == ""
        assert resolve_media_path("/media", "http://example.com/file.pdf") == ""

    def test_resolve_media_path_relative(self) -> None:
        from apps.documents.services.generation.path_utils import resolve_media_path

        result = resolve_media_path("/var/media", "docs/test.pdf")
        assert result == "/var/media/docs/test.pdf"

    def test_resolve_media_path_absolute(self) -> None:
        from apps.documents.services.generation.path_utils import resolve_media_path

        result = resolve_media_path("/var/media", "/tmp/test.pdf")
        assert result == "/tmp/test.pdf"

    def test_resolve_media_path_with_prefix(self) -> None:
        from apps.documents.services.generation.path_utils import resolve_media_path

        result = resolve_media_path("/var/media", "/media/docs/test.pdf")
        assert result == "/var/media/docs/test.pdf"

    def test_safe_name_basic(self) -> None:
        from apps.documents.services.generation.path_utils import safe_name

        assert safe_name("test.txt") == "test.txt"
        assert safe_name("") == "未命名"

    def test_safe_name_slash(self) -> None:
        from apps.documents.services.generation.path_utils import safe_name

        result = safe_name("path/to/file")
        assert "/" not in result
        assert "／" in result

    def test_safe_arcname(self) -> None:
        from apps.documents.services.generation.path_utils import safe_arcname

        result = safe_arcname("path/to/file.txt")
        assert "/" in result
        assert "\\" not in result


# ============================================================
# documents/services/generation/result.py
# ============================================================


class TestGenerationResult:
    def test_success_result(self) -> None:
        from apps.documents.services.generation.result import GenerationResult

        result = GenerationResult(success=True, file_path="/tmp/test.docx", file_name="test.docx")
        assert result.success is True
        assert result.file_path == "/tmp/test.docx"

    def test_failure_result(self) -> None:
        from apps.documents.services.generation.result import GenerationResult

        result = GenerationResult(success=False, error_message="failed")
        assert result.success is False
        assert result.error_message == "failed"

    def test_success_without_path_raises(self) -> None:
        from apps.documents.services.generation.result import GenerationResult

        with pytest.raises(ValueError):
            GenerationResult(success=True)

    def test_failure_without_error_raises(self) -> None:
        from apps.documents.services.generation.result import GenerationResult

        with pytest.raises(ValueError):
            GenerationResult(success=False)

    def test_negative_duration_raises(self) -> None:
        from apps.documents.services.generation.result import GenerationResult

        with pytest.raises(ValueError):
            GenerationResult(success=True, file_path="/tmp/test.docx", duration_ms=-1)


# ============================================================
# documents/services/generation/outputs.py
# ============================================================


class TestGenerationOutputs:
    def test_party_info(self) -> None:
        from apps.documents.services.generation.outputs import PartyInfo

        p = PartyInfo(name="Test", role="plaintiff")
        assert p.name == "Test"
        assert p.id_number == ""

    def test_complaint_output(self) -> None:
        from apps.documents.services.generation.outputs import ComplaintOutput, PartyInfo

        output = ComplaintOutput(
            title="Complaint",
            parties=[PartyInfo(name="A", role="plaintiff")],
            litigation_request="request",
            facts_and_reasons="facts",
        )
        assert len(output.parties) == 1
        assert output.evidence == []

    def test_defense_output(self) -> None:
        from apps.documents.services.generation.outputs import DefenseOutput, PartyInfo

        output = DefenseOutput(
            title="Defense",
            parties=[PartyInfo(name="B", role="defendant")],
            defense_opinion="opinion",
            defense_reasons="reasons",
        )
        assert output.evidence == []

    def test_execution_request_output_defaults(self) -> None:
        from apps.documents.services.generation.outputs import ExecutionRequestOutput

        output = ExecutionRequestOutput()
        assert output.principal is None
        assert output.rate_type == "lpr"
        assert output.confirmed_interest == 0
