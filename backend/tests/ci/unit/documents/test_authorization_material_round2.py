"""Round 2 coverage tests for AuthorizationMaterialGenerationService — uncovered branches."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_service(**overrides):
    from apps.documents.services.generation.authorization_material_generation_service import (
        AuthorizationMaterialGenerationService,
    )
    defaults = {
        "case_service": MagicMock(),
        "client_service": MagicMock(),
        "document_service": MagicMock(),
    }
    defaults.update(overrides)
    return AuthorizationMaterialGenerationService(**defaults)


def _make_party(*, client_id=10, client_name="张三", is_our=True, client_type="natural"):
    party = MagicMock()
    client = MagicMock()
    client.id = client_id
    client.name = client_name
    client.is_our_client = is_our
    client.client_type = client_type
    party.client = client
    party.client_id = client_id
    return party


def _make_case(*, case_id=1, name="测试案件"):
    case = MagicMock()
    case.id = case_id
    case.name = name
    return case


class TestGetClientExceptionHandling:
    """Test _get_our_client and _get_our_legal_client exception branches."""

    def test_get_our_client_exception_in_parties(self):
        case = _make_case()
        case.parties.select_related.return_value.all.side_effect = Exception("db err")
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="我方当事人不存在或不合法"):
            svc._get_our_client(case, 10)

    def test_get_our_legal_client_exception_in_parties(self):
        case = _make_case()
        case.parties.select_related.return_value.all.side_effect = Exception("db err")
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="我方当事人法人不存在或不合法"):
            svc._get_our_legal_client(case, 10)

    def test_get_our_client_no_match(self):
        party = _make_party(client_id=99, is_our=True)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = [party]
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException):
            svc._get_our_client(case, client_id=10)


class TestRenderTemplate:
    def test_template_path_not_exists(self):
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        path = MagicMock()
        path.exists.return_value = False
        with pytest.raises(ValidationException, match="模板文件不存在"):
            svc._render_template(path, {})

    def test_render_success(self):
        svc = _make_service()
        path = MagicMock()
        path.exists.return_value = True
        with patch("apps.documents.services.generation.pipeline.DocxRenderer") as mock_renderer:
            mock_renderer.return_value.render.return_value = b"rendered"
            result = svc._render_template(path, {"key": "val"})
        assert result == b"rendered"

    def test_render_exception(self):
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        path = MagicMock()
        path.exists.return_value = True
        with patch("apps.documents.services.generation.pipeline.DocxRenderer") as mock_renderer:
            mock_renderer.return_value.render.side_effect = RuntimeError("render fail")
            with pytest.raises(ValidationException, match="模板渲染失败"):
                svc._render_template(path, {})


class TestBuildFilenames:
    def test_build_authority_letter_empty_case_name(self):
        svc = _make_service()
        with patch(
            "apps.documents.services.generation.authorization_material_generation_service.FilenameTemplateService"
        ) as mock_fts, patch(
            "apps.documents.services.generation.authorization_material_generation_service.timezone"
        ) as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260607"
            mock_fts.render_generated_doc.return_value = "doc"
            result = svc._build_authority_letter_filename(case_name="")
        assert result.endswith(".docx")
        mock_fts.render_generated_doc.assert_called_once()
        call_kwargs = mock_fts.render_generated_doc.call_args
        assert call_kwargs[1]["case_name"] == "案件"

    def test_build_legal_rep_empty_company_name(self):
        svc = _make_service()
        with patch(
            "apps.documents.services.generation.authorization_material_generation_service.FilenameTemplateService"
        ) as mock_fts, patch(
            "apps.documents.services.generation.authorization_material_generation_service.timezone"
        ) as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260607"
            mock_fts.render_generated_doc.return_value = "doc"
            result = svc._build_legal_rep_certificate_filename(company_name="")
        assert result.endswith(".docx")
        call_kwargs = mock_fts.render_generated_doc.call_args
        assert call_kwargs[1]["case_name"] == "公司"

    def test_build_poa_filename_combined(self):
        svc = _make_service()
        case = _make_case(name="案件")
        with patch(
            "apps.documents.services.generation.authorization_material_generation_service.FilenameTemplateService"
        ) as mock_fts, patch(
            "apps.documents.services.generation.authorization_material_generation_service.timezone"
        ) as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260607"
            mock_fts.render_generated_doc.return_value = "poa"
            result = svc._build_power_of_attorney_filename(case=case, selected_clients=[], combined=True)
        assert result.endswith(".docx")

    def test_build_poa_filename_single_party(self):
        svc = _make_service()
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = [_make_party(is_our=True)]
        client = MagicMock()
        client.name = "张三"
        with patch(
            "apps.documents.services.generation.authorization_material_generation_service.FilenameTemplateService"
        ) as mock_fts, patch(
            "apps.documents.services.generation.authorization_material_generation_service.timezone"
        ) as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260607"
            mock_fts.render_generated_doc.return_value = "poa"
            result = svc._build_power_of_attorney_filename(
                case=case, selected_clients=[client], combined=False
            )
        assert result.endswith(".docx")

    def test_build_poa_filename_multiple_parties(self):
        svc = _make_service()
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = [_make_party(is_our=True), _make_party(client_id=20, is_our=True)]
        client = MagicMock()
        client.name = "张三"
        with patch(
            "apps.documents.services.generation.authorization_material_generation_service.FilenameTemplateService"
        ) as mock_fts, patch(
            "apps.documents.services.generation.authorization_material_generation_service.timezone"
        ) as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260607"
            mock_fts.render_generated_doc.return_value = "poa"
            result = svc._build_power_of_attorney_filename(
                case=case, selected_clients=[client], combined=False
            )
        assert result.endswith(".docx")
        # Should include client name in parentheses
        call_args = mock_fts.render_generated_doc.call_args
        assert "张三" in call_args[1]["doc_type"]

    def test_build_poa_no_clients_no_parties(self):
        svc = _make_service()
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = []
        with patch(
            "apps.documents.services.generation.authorization_material_generation_service.FilenameTemplateService"
        ) as mock_fts, patch(
            "apps.documents.services.generation.authorization_material_generation_service.timezone"
        ) as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260607"
            mock_fts.render_generated_doc.return_value = "poa"
            result = svc._build_power_of_attorney_filename(
                case=case, selected_clients=[], combined=False
            )
        assert result.endswith(".docx")


class TestCountOurParties:
    def test_with_mixed_parties(self):
        svc = _make_service()
        case = _make_case()
        p1 = _make_party(is_our=True)
        p2 = _make_party(client_id=20, is_our=False)
        p3 = MagicMock()
        p3.client = None
        case.parties.select_related.return_value.all.return_value = [p1, p2, p3]
        assert svc._count_our_parties(case) == 1

    def test_exception_returns_zero(self):
        svc = _make_service()
        case = _make_case()
        case.parties.select_related.return_value.all.side_effect = Exception("err")
        assert svc._count_our_parties(case) == 0


class TestZipAddMissingMarkdown:
    def test_writes_unique_lines(self):
        svc = _make_service()
        zf = MagicMock()
        svc._zip_add_missing_markdown(zf, missing_lines=["A", "A", "B"])
        zf.writestr.assert_called_once()
        body = zf.writestr.call_args[0][1]
        assert body.count("- A") == 1
        assert "- B" in body
        assert "当前授权手续所缺材料" in body


class TestGetTemplatePathFromCaseBindings:
    def test_generic_template_match_type_and_stage(self):
        svc = _make_service()
        svc.case_service.get_case_template_bindings_by_name_internal.return_value = []
        case_dto = MagicMock(case_type="litigation", current_stage="first_trial")
        svc.case_service.get_case_internal.return_value = case_dto

        template = MagicMock()
        template.case_types = ["litigation"]
        template.case_stages = ["first_trial"]
        template.get_file_location.return_value = "/path/to/template.docx"

        with patch(
            "apps.documents.services.generation.authorization_material_generation_service.DocumentTemplate"
        ) as mock_tmpl:
            mock_tmpl.objects.filter.return_value = [template]
            with patch(
                "apps.documents.services.generation.authorization_material_generation_service.Path"
            ) as MockPath:
                result = svc._get_template_path_from_case_bindings(1, "所函")
        assert result is not None

    def test_generic_template_match_all_type(self):
        svc = _make_service()
        svc.case_service.get_case_template_bindings_by_name_internal.return_value = []
        case_dto = MagicMock(case_type="litigation", current_stage="first_trial")
        svc.case_service.get_case_internal.return_value = case_dto

        template = MagicMock()
        template.case_types = ["all"]
        template.case_stages = []
        template.get_file_location.return_value = "/path/to/template.docx"

        with patch(
            "apps.documents.services.generation.authorization_material_generation_service.DocumentTemplate"
        ) as mock_tmpl:
            mock_tmpl.objects.filter.return_value = [template]
            with patch(
                "apps.documents.services.generation.authorization_material_generation_service.Path"
            ) as MockPath:
                result = svc._get_template_path_from_case_bindings(1, "所函")
        assert result is not None

    def test_no_case_stage(self):
        svc = _make_service()
        svc.case_service.get_case_template_bindings_by_name_internal.return_value = []
        case_dto = MagicMock(case_type="litigation", current_stage=None)
        svc.case_service.get_case_internal.return_value = case_dto

        template = MagicMock()
        template.case_types = ["litigation"]
        template.case_stages = ["first_trial"]
        template.get_file_location.return_value = "/path/to/template.docx"

        with patch(
            "apps.documents.services.generation.authorization_material_generation_service.DocumentTemplate"
        ) as mock_tmpl:
            mock_tmpl.objects.filter.return_value = [template]
            with patch(
                "apps.documents.services.generation.authorization_material_generation_service.Path"
            ) as MockPath:
                result = svc._get_template_path_from_case_bindings(1, "所函")
        assert result is not None

    def test_no_file_location(self):
        svc = _make_service()
        svc.case_service.get_case_template_bindings_by_name_internal.return_value = []
        case_dto = MagicMock(case_type="litigation", current_stage="first_trial")
        svc.case_service.get_case_internal.return_value = case_dto

        template = MagicMock()
        template.case_types = ["litigation"]
        template.case_stages = ["first_trial"]
        template.get_file_location.return_value = ""

        with patch(
            "apps.documents.services.generation.authorization_material_generation_service.DocumentTemplate"
        ) as mock_tmpl:
            mock_tmpl.objects.filter.return_value = [template]
            result = svc._get_template_path_from_case_bindings(1, "所函")
        assert result is None
