"""Tests for documents.services.generation.litigation_generation_service.

Covers: __init__, llm_generator/context_builder properties, generate_complaint,
generate_defense, generate_complaint_document, generate_defense_document,
_generate_filename, _get_mock_complaint_output, _get_mock_defense_output,
_render_template.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestLitigationGenerationServiceInit:
    def test_default_init(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        svc = LitigationGenerationService()
        assert svc._llm_generator is None
        assert svc._context_builder is None

    def test_injected_init(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        llm = MagicMock()
        ctx = MagicMock()
        svc = LitigationGenerationService(llm_generator=llm, context_builder=ctx)
        assert svc.llm_generator is llm
        assert svc.context_builder is ctx

    def test_llm_generator_lazy(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        svc = LitigationGenerationService()
        with patch("apps.documents.services.generation.litigation_generation_service.LitigationLLMGenerator") as MockLLM:
            gen = svc.llm_generator
            assert gen is MockLLM.return_value
            assert svc._llm_generator is gen  # cached

    def test_context_builder_lazy(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        svc = LitigationGenerationService()
        with patch("apps.documents.services.generation.litigation_generation_service.LitigationContextBuilder") as MockCtx:
            builder = svc.context_builder
            assert builder is MockCtx.return_value
            assert svc._context_builder is builder


class TestGenerateComplaint:
    def test_delegates_to_llm(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        llm_gen = MagicMock()
        llm_gen.generate_complaint.return_value = "complaint_output"
        svc = LitigationGenerationService(llm_generator=llm_gen)
        result = svc.generate_complaint({"cause": "合同纠纷"})
        assert result == "complaint_output"
        llm_gen.generate_complaint.assert_called_once_with({"cause": "合同纠纷"})


class TestGenerateDefense:
    def test_delegates_to_llm(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        llm_gen = MagicMock()
        llm_gen.generate_defense.return_value = "defense_output"
        svc = LitigationGenerationService(llm_generator=llm_gen)
        result = svc.generate_defense({"cause": "合同纠纷"})
        assert result == "defense_output"
        llm_gen.generate_defense.assert_called_once_with({"cause": "合同纠纷"})


class TestGenerateFilename:
    def test_complaint(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        svc = LitigationGenerationService()
        with patch("apps.documents.services.placeholders.litigation.FilenameService") as MockFS:
            MockFS.return_value.generate_complaint_filename.return_value = "complaint_1.docx"
            result = svc._generate_filename(1, "complaint")
            assert result == "complaint_1.docx"

    def test_defense(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        svc = LitigationGenerationService()
        with patch("apps.documents.services.placeholders.litigation.FilenameService") as MockFS:
            MockFS.return_value.generate_defense_filename.return_value = "defense_1.docx"
            result = svc._generate_filename(1, "defense")
            assert result == "defense_1.docx"

    def test_invalid_type(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        svc = LitigationGenerationService()
        with pytest.raises(Exception, match="不支持的文档类型"):
            svc._generate_filename(1, "invalid")


class TestGetMockComplaintOutput:
    def test_basic(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        svc = LitigationGenerationService()
        case_data = {
            "cause_of_action": "借款纠纷",
            "plaintiff": "原告A",
            "defendant": "被告B",
        }
        result = svc._get_mock_complaint_output(case_data)
        assert "借款纠纷" in result.title
        assert len(result.parties) == 2
        assert result.parties[0].name == "原告A"
        assert result.parties[1].name == "被告B"
        assert result.litigation_request != ""
        assert result.facts_and_reasons != ""
        assert len(result.evidence) > 0


class TestGetMockDefenseOutput:
    def test_basic(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        svc = LitigationGenerationService()
        case_data = {
            "cause_of_action": "借款纠纷",
            "plaintiff": "原告A",
            "defendant": "被告B",
        }
        result = svc._get_mock_defense_output(case_data)
        assert "借款纠纷" in result.title
        assert result.defense_opinion != ""
        assert result.defense_reasons != ""


class TestRenderTemplate:
    def test_template_not_found(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        svc = LitigationGenerationService()
        from apps.core.utils.path import Path
        template_path = Path("/nonexistent/template.docx")
        with pytest.raises(Exception, match="模板文件不存在"):
            svc._render_template(template_path, {})

    def test_template_success(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        svc = LitigationGenerationService()
        from apps.core.utils.path import Path
        template_path = Path("/fake/template.docx")
        with patch.object(Path, "exists", return_value=True), \
             patch("apps.documents.services.generation.pipeline.DocxRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = b"rendered_bytes"
            result = svc._render_template(template_path, {"key": "value"})
            assert result == b"rendered_bytes"

    def test_adds_year_if_missing(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        svc = LitigationGenerationService()
        from apps.core.utils.path import Path
        template_path = Path("/fake/template.docx")
        context = {}
        with patch.object(Path, "exists", return_value=True), \
             patch("apps.documents.services.generation.pipeline.DocxRenderer") as MockRenderer:
            MockRenderer.return_value.render.return_value = b"ok"
            svc._render_template(template_path, context)
            assert "年份" in context


class TestGenerateComplaintDocument:
    def test_case_not_found(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        from apps.core.exceptions import NotFoundError
        svc = LitigationGenerationService()
        with patch("apps.documents.services.generation.litigation_generation_service.ServiceLocator") as mock_loc:
            mock_loc.get_case_service.return_value.get_case_by_id_internal.return_value = None
            with pytest.raises(NotFoundError):
                svc.generate_complaint_document(1)

    def test_skip_llm(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        svc = LitigationGenerationService()
        case_dto = SimpleNamespace(id=1)
        with patch("apps.documents.services.generation.litigation_generation_service.ServiceLocator") as mock_loc, \
             patch.object(svc, "_get_mock_complaint_output", return_value=SimpleNamespace()), \
             patch.object(svc, "context_builder") as mock_ctx, \
             patch.object(svc, "_render_template", return_value=b"doc"), \
             patch.object(svc, "_generate_filename", return_value="complaint_1.docx"):
            mock_loc.get_case_service.return_value.get_case_by_id_internal.return_value = case_dto
            mock_ctx.build_complaint_context.return_value = {"ctx": "val"}
            filename, doc = svc.generate_complaint_document(1, skip_llm=True)
            assert filename == "complaint_1.docx"
            assert doc == b"doc"


class TestGenerateDefenseDocument:
    def test_case_not_found(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        from apps.core.exceptions import NotFoundError
        svc = LitigationGenerationService()
        with patch("apps.documents.services.generation.litigation_generation_service.ServiceLocator") as mock_loc:
            mock_loc.get_case_service.return_value.get_case_by_id_internal.return_value = None
            with pytest.raises(NotFoundError):
                svc.generate_defense_document(1)

    def test_skip_llm(self):
        from apps.documents.services.generation.litigation_generation_service import (
            LitigationGenerationService,
        )
        svc = LitigationGenerationService()
        case_dto = SimpleNamespace(id=1)
        with patch("apps.documents.services.generation.litigation_generation_service.ServiceLocator") as mock_loc, \
             patch.object(svc, "_get_mock_defense_output", return_value=SimpleNamespace()), \
             patch.object(svc, "context_builder") as mock_ctx, \
             patch.object(svc, "_render_template", return_value=b"doc"), \
             patch.object(svc, "_generate_filename", return_value="defense_1.docx"):
            mock_loc.get_case_service.return_value.get_case_by_id_internal.return_value = case_dto
            mock_ctx.build_defense_context.return_value = {"ctx": "val"}
            filename, doc = svc.generate_defense_document(1, skip_llm=True)
            assert filename == "defense_1.docx"
            assert doc == b"doc"
