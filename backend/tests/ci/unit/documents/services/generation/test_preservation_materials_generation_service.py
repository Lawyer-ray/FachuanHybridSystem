"""Tests for preservation_materials_generation_service.py — uncovered branches.

Covers: lazy properties, _generate_missing_clues_report, _build_filename,
        _get_template_path_by_function_code, has_template,
        generate_preservation_application (template-not-found), generate_delay_delivery_application,
        get_missing_clues_report.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


@pytest.fixture
def svc() -> Any:
    from apps.documents.services.generation.preservation_materials_generation_service import (
        PreservationMaterialsGenerationService,
    )

    return PreservationMaterialsGenerationService(
        party_service=MagicMock(),
        signature_service=MagicMock(),
        property_clue_service=MagicMock(),
        template_service=MagicMock(),
    )


@pytest.fixture
def svc_lazy() -> Any:
    from apps.documents.services.generation.preservation_materials_generation_service import (
        PreservationMaterialsGenerationService,
    )

    return PreservationMaterialsGenerationService()


# ── lazy properties ──────────────────────────────────────────────


class TestLazyProperties:
    def test_party_service_injected(self, svc: Any) -> None:
        assert svc.party_service is not None

    def test_signature_service_injected(self, svc: Any) -> None:
        assert svc.signature_service is not None

    def test_property_clue_service_injected(self, svc: Any) -> None:
        assert svc.property_clue_service is not None

    def test_lazy_loads_party_service(self, svc_lazy: Any) -> None:
        """The lazy property should create a PreservationPartyService on first access."""
        result = svc_lazy.party_service
        assert result is not None

    def test_lazy_loads_signature_service(self, svc_lazy: Any) -> None:
        """The lazy property should create a PreservationSignatureService on first access."""
        result = svc_lazy.signature_service
        assert result is not None

    def test_lazy_loads_property_clue_service(self, svc_lazy: Any) -> None:
        """The lazy property should create a PreservationPropertyClueService on first access."""
        result = svc_lazy.property_clue_service
        assert result is not None


# ── _generate_missing_clues_report ───────────────────────────────


class TestGenerateMissingCluesReport:
    def test_generates_report(self, svc: Any) -> None:
        result = svc._generate_missing_clues_report(["张三", "李四"])
        assert "# 当前保全手续所缺材料" in result
        assert "1. 张三" in result
        assert "2. 李四" in result

    def test_single_respondent(self, svc: Any) -> None:
        result = svc._generate_missing_clues_report(["王五"])
        assert "1. 王五" in result
        assert result.count("\n") >= 3  # header + blank + item

    def test_empty_list(self, svc: Any) -> None:
        result = svc._generate_missing_clues_report([])
        assert "# 当前保全手续所缺材料" in result
        # No numbered items
        lines = result.strip().split("\n")
        assert lines[-1] == "以下被申请人暂无财产线索,请补充:"


# ── get_missing_clues_report ─────────────────────────────────────


class TestGetMissingCluesReport:
    def test_returns_none_when_all_have_clues(self, svc: Any) -> None:
        svc.property_clue_service.get_respondents_without_clues.return_value = []
        result = svc.get_missing_clues_report(1)
        assert result is None

    def test_returns_report_when_missing(self, svc: Any) -> None:
        svc.property_clue_service.get_respondents_without_clues.return_value = ["Alice"]
        result = svc.get_missing_clues_report(1)
        assert result is not None
        assert "Alice" in result


# ── _build_filename ──────────────────────────────────────────────


class TestBuildFilename:
    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.timezone"
    )
    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.FilenameTemplateService"
    )
    def test_builds_filename(
        self, MockFTS: MagicMock, mock_tz: MagicMock, svc: Any
    ) -> None:
        mock_tz.now.return_value.strftime.return_value = "20250601"
        MockFTS.render_generated_doc.return_value = "财产保全申请书(测试案件)V1_20250601"
        case = MagicMock()
        case.name = "测试案件"
        result = svc._build_filename("财产保全申请书", case)
        assert result.endswith(".docx")
        MockFTS.render_generated_doc.assert_called_once_with(
            doc_type="财产保全申请书",
            case_name="测试案件",
            version="1",
            date="20250601",
        )

    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.timezone"
    )
    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.FilenameTemplateService"
    )
    def test_empty_case_name_fallback(
        self, MockFTS: MagicMock, mock_tz: MagicMock, svc: Any
    ) -> None:
        mock_tz.now.return_value.strftime.return_value = "20250601"
        MockFTS.render_generated_doc.return_value = "result"
        case = MagicMock()
        case.name = ""
        svc._build_filename("test", case)
        MockFTS.render_generated_doc.assert_called_once_with(
            doc_type="test", case_name="案件", version="1", date="20250601"
        )


# ── _get_case ────────────────────────────────────────────────────


class TestGetCase:
    @patch("apps.documents.services.generation.preservation_materials_generation_service.get_case_service")
    def test_raises_when_not_found(self, mock_get: MagicMock, svc: Any) -> None:
        mock_get.return_value.get_case_model_internal.return_value = None
        with pytest.raises(NotFoundError):
            svc._get_case(999)

    @patch("apps.documents.services.generation.preservation_materials_generation_service.get_case_service")
    def test_returns_case(self, mock_get: MagicMock, svc: Any) -> None:
        case = MagicMock()
        mock_get.return_value.get_case_model_internal.return_value = case
        result = svc._get_case(1)
        assert result is case


# ── has_template ─────────────────────────────────────────────────


class TestHasTemplate:
    @patch.object(
        __import__(
            "apps.documents.services.generation.preservation_materials_generation_service",
            fromlist=["PreservationMaterialsGenerationService"],
        ).PreservationMaterialsGenerationService,
        "_get_template_path_by_function_code",
    )
    def test_returns_true(self, mock_path: MagicMock, svc: Any) -> None:
        mock_path.return_value = MagicMock()
        assert svc.has_template(1, "preservation_application") is True

    @patch.object(
        __import__(
            "apps.documents.services.generation.preservation_materials_generation_service",
            fromlist=["PreservationMaterialsGenerationService"],
        ).PreservationMaterialsGenerationService,
        "_get_template_path_by_function_code",
    )
    def test_returns_false(self, mock_path: MagicMock, svc: Any) -> None:
        mock_path.return_value = None
        assert svc.has_template(1, "preservation_application") is False


# ── generate_preservation_application (no template) ──────────────


class TestGeneratePreservationApplication:
    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.get_case_service"
    )
    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.get_document_service"
    )
    def test_raises_when_no_template(
        self, mock_doc: MagicMock, mock_case: MagicMock, svc: Any
    ) -> None:
        case = MagicMock()
        mock_case.return_value.get_case_model_internal.return_value = case
        mock_case.return_value.get_case_template_bindings_by_name_internal.return_value = []
        with patch(
            "apps.documents.models.DocumentTemplate"
        ) as MockDT:
            MockDT.objects.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError, match="未找到财产保全申请书模板"):
                svc.generate_preservation_application(1)

    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.get_case_service"
    )
    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.get_document_service"
    )
    def test_raises_when_no_template_delay(
        self, mock_doc: MagicMock, mock_case: MagicMock, svc: Any
    ) -> None:
        case = MagicMock()
        mock_case.return_value.get_case_model_internal.return_value = case
        mock_case.return_value.get_case_template_bindings_by_name_internal.return_value = []
        with patch(
            "apps.documents.models.DocumentTemplate"
        ) as MockDT:
            MockDT.objects.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError, match="未找到暂缓送达申请书模板"):
                svc.generate_delay_delivery_application(1)


# ── _get_template_path_by_function_code ──────────────────────────


class TestGetTemplatePathByFunctionCode:
    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.get_case_service"
    )
    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.get_document_service"
    )
    def test_finds_from_binding(
        self, mock_doc: MagicMock, mock_case: MagicMock, svc: Any
    ) -> None:
        binding = MagicMock()
        binding.template_id = 10
        mock_case.return_value.get_case_template_bindings_by_name_internal.return_value = [binding]
        dto = MagicMock()
        dto.file_path = "/path/to/template.docx"
        mock_doc.return_value.get_template_by_id_internal.return_value = dto
        result = svc._get_template_path_by_function_code(1, "preservation_application")
        assert result is not None
        assert str(result) == "/path/to/template.docx"

    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.get_case_service"
    )
    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.get_document_service"
    )
    def test_binding_no_file_path(
        self, mock_doc: MagicMock, mock_case: MagicMock, svc: Any
    ) -> None:
        binding = MagicMock()
        binding.template_id = 10
        mock_case.return_value.get_case_template_bindings_by_name_internal.return_value = [binding]
        dto = MagicMock()
        dto.file_path = None
        mock_doc.return_value.get_template_by_id_internal.return_value = dto
        # Should fall through to DocumentTemplate.objects query
        with patch(
            "apps.documents.models.DocumentTemplate"
        ) as MockDT:
            MockDT.objects.filter.return_value.first.return_value = None
            result = svc._get_template_path_by_function_code(1, "preservation_application")
            assert result is None

    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.get_case_service"
    )
    def test_finds_from_global_template(
        self, mock_case: MagicMock, svc: Any
    ) -> None:
        mock_case.return_value.get_case_template_bindings_by_name_internal.return_value = []
        with patch(
            "apps.documents.models.DocumentTemplate"
        ) as MockDT:
            template = MagicMock()
            template.get_file_location.return_value = "/global/template.docx"
            MockDT.objects.filter.return_value.first.return_value = template
            result = svc._get_template_path_by_function_code(1, "preservation_application")
            assert result is not None
            assert str(result) == "/global/template.docx"

    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.get_case_service"
    )
    def test_global_template_no_location(
        self, mock_case: MagicMock, svc: Any
    ) -> None:
        mock_case.return_value.get_case_template_bindings_by_name_internal.return_value = []
        with patch(
            "apps.documents.models.DocumentTemplate"
        ) as MockDT:
            template = MagicMock()
            template.get_file_location.return_value = None
            MockDT.objects.filter.return_value.first.return_value = template
            result = svc._get_template_path_by_function_code(1, "preservation_application")
            assert result is None


# ── _build_context ───────────────────────────────────────────────


class TestBuildContext:
    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.EnhancedContextBuilder"
    )
    def test_builds_context(self, MockBuilder: MagicMock, svc: Any) -> None:
        mock_builder = MagicMock()
        mock_builder.build_context.return_value = {"key": "val"}
        MockBuilder.return_value = mock_builder
        case = MagicMock()
        result = svc._build_context(case=case)
        assert result == {"key": "val"}
        mock_builder.build_context.assert_called_once_with({"case": case})


# ── _get_respondents ─────────────────────────────────────────────


class TestGetRespondents:
    @patch(
        "apps.documents.services.generation.preservation_materials_generation_service.get_case_service"
    )
    def test_returns_respondents(self, mock_get: MagicMock, svc: Any) -> None:
        respondents = [MagicMock(), MagicMock()]
        mock_get.return_value.get_case_parties_internal.return_value = respondents
        result = svc._get_respondents(1)
        assert len(result) == 2
