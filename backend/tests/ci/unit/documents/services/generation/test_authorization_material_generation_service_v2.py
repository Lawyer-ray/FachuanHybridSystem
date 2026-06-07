"""Tests for AuthorizationMaterialGenerationService."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch, AsyncMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(**overrides: Any) -> Any:
    """Build service with mocked dependencies."""
    from apps.documents.services.generation.authorization_material_generation_service import (
        AuthorizationMaterialGenerationService,
    )

    defaults: dict[str, Any] = {
        "case_service": MagicMock(),
        "client_service": MagicMock(),
        "document_service": MagicMock(),
    }
    defaults.update(overrides)
    return AuthorizationMaterialGenerationService(**defaults)


def _make_case(*, case_id: int = 1, name: str = "张三诉李四案", **extra: Any) -> MagicMock:
    case = MagicMock()
    case.id = case_id
    case.name = name
    for k, v in extra.items():
        setattr(case, k, v)
    return case


def _make_party(
    *,
    client_id: int = 10,
    client_name: str = "张三",
    is_our: bool = True,
    client_type: str = "natural",
    legal_representative: str = "",
    id_number: str = "110101199001011234",
    phone: str = "13800000000",
    address: str = "北京市朝阳区",
) -> MagicMock:
    party = MagicMock()
    client = MagicMock()
    client.id = client_id
    client.name = client_name
    client.is_our_client = is_our
    client.client_type = client_type
    client.legal_representative = legal_representative
    client.id_number = id_number
    client.phone = phone
    client.address = address
    party.client = client
    party.client_id = client_id
    return party


# ---------------------------------------------------------------------------
# Service property tests
# ---------------------------------------------------------------------------

class TestServiceProperties:
    def test_case_service_raises_when_none(self):
        svc = _make_service(case_service=None)
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.case_service

    def test_client_service_raises_when_none(self):
        svc = _make_service(client_service=None)
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.client_service

    def test_document_service_raises_when_none(self):
        svc = _make_service(document_service=None)
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.document_service

    def test_services_return_injected_objects(self):
        cs = MagicMock()
        svc = _make_service(case_service=cs)
        assert svc.case_service is cs


# ---------------------------------------------------------------------------
# _get_case
# ---------------------------------------------------------------------------

class TestGetCase:
    def test_returns_case_when_found(self):
        case = _make_case()
        svc = _make_service()
        svc.case_service.get_case_model_internal.return_value = case
        assert svc._get_case(1) is case

    def test_raises_when_not_found(self):
        svc = _make_service()
        svc.case_service.get_case_model_internal.return_value = None
        from apps.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            svc._get_case(999)


# ---------------------------------------------------------------------------
# _get_our_client
# ---------------------------------------------------------------------------

class TestGetOurClient:
    def test_returns_matching_our_client(self):
        party = _make_party(client_id=10, is_our=True)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = [party]
        svc = _make_service()
        result = svc._get_our_client(case, client_id=10)
        assert result.id == 10

    def test_raises_when_not_our_client(self):
        party = _make_party(client_id=10, is_our=False)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = [party]
        svc = _make_service()
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException, match="我方当事人不存在或不合法"):
            svc._get_our_client(case, client_id=10)

    def test_raises_when_no_parties(self):
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = []
        svc = _make_service()
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException):
            svc._get_our_client(case, client_id=10)


# ---------------------------------------------------------------------------
# _get_our_legal_client
# ---------------------------------------------------------------------------

class TestGetOurLegalClient:
    def test_returns_matching_legal_client(self):
        party = _make_party(client_id=10, is_our=True, client_type="legal")
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = [party]
        svc = _make_service()
        result = svc._get_our_legal_client(case, client_id=10)
        assert result.id == 10

    def test_raises_when_natural(self):
        party = _make_party(client_id=10, is_our=True, client_type="natural")
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = [party]
        svc = _make_service()
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException, match="我方当事人法人不存在或不合法"):
            svc._get_our_legal_client(case, client_id=10)


# ---------------------------------------------------------------------------
# _build_context / _build_power_of_attorney_context
# ---------------------------------------------------------------------------

class TestBuildContext:
    @patch("apps.documents.services.generation.authorization_material_generation_service.EnhancedContextBuilder")
    def test_build_context_includes_case(self, mock_builder_cls):
        mock_builder_cls.return_value.build_context.return_value = {"case": "c"}
        svc = _make_service()
        result = svc._build_context(case="c")
        mock_builder_cls.return_value.build_context.assert_called_once_with({"case": "c"})

    @patch("apps.documents.services.generation.authorization_material_generation_service.EnhancedContextBuilder")
    def test_build_context_includes_client(self, mock_builder_cls):
        mock_builder_cls.return_value.build_context.return_value = {"case": "c", "client": "cl"}
        svc = _make_service()
        svc._build_context(case="c", client="cl")
        call_args = mock_builder_cls.return_value.build_context.call_args
        assert call_args[0][0] == {"case": "c", "client": "cl"}

    @patch("apps.documents.services.generation.authorization_material_generation_service.EnhancedContextBuilder")
    def test_build_poa_context_has_required_placeholders(self, mock_builder_cls):
        mock_builder_cls.return_value.build_context.return_value = {}
        svc = _make_service()
        svc._build_power_of_attorney_context(case="c", selected_clients=["cl"])
        call_kwargs = mock_builder_cls.return_value.build_context.call_args[1]
        assert "required_placeholders" in call_kwargs
        assert "授权委托书_代理事项" in call_kwargs["required_placeholders"]


# ---------------------------------------------------------------------------
# _get_template_path
# ---------------------------------------------------------------------------

class TestGetTemplatePath:
    def test_valid_path(self):
        from apps.core.utils.path import Path as CorePath

        tmpl = MagicMock()
        tmpl.get_file_location.return_value = "/some/path.docx"
        svc = _make_service()
        result = svc._get_template_path(tmpl)
        assert isinstance(result, CorePath)

    def test_empty_path_raises(self):
        tmpl = MagicMock()
        tmpl.get_file_location.return_value = ""
        tmpl.pk = 42
        svc = _make_service()
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException, match="模板文件路径为空"):
            svc._get_template_path(tmpl)


# ---------------------------------------------------------------------------
# _get_power_of_attorney_template_from_db
# ---------------------------------------------------------------------------

class TestGetPoATemplateFromDb:
    @patch("apps.documents.services.generation.authorization_material_generation_service.DocumentTemplate")
    def test_returns_template_when_found(self, mock_model):
        tmpl = MagicMock()
        mock_model.objects.filter.return_value.order_by.return_value.first.return_value = tmpl
        svc = _make_service()
        result = svc._get_power_of_attorney_template_from_db()
        assert result is tmpl

    @patch("apps.documents.services.generation.authorization_material_generation_service.DocumentTemplate")
    def test_raises_when_not_found(self, mock_model):
        mock_model.objects.filter.return_value.order_by.return_value.first.return_value = None
        svc = _make_service()
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException, match="未找到"):
            svc._get_power_of_attorney_template_from_db()


# ---------------------------------------------------------------------------
# _validate_power_of_attorney_context
# ---------------------------------------------------------------------------

class TestValidatePoAContext:
    def test_always_passes(self):
        svc = _make_service()
        # Should not raise
        svc._validate_power_of_attorney_context({"代理事项": ""})


# ---------------------------------------------------------------------------
# _count_our_parties
# ---------------------------------------------------------------------------

class TestCountOurParties:
    def test_counts_our_parties(self):
        p1 = _make_party(is_our=True)
        p2 = _make_party(is_our=False, client_id=20)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = [p1, p2]
        svc = _make_service()
        assert svc._count_our_parties(case) == 1

    def test_returns_0_on_exception(self):
        case = _make_case()
        case.parties.select_related.return_value.all.side_effect = Exception("db error")
        svc = _make_service()
        assert svc._count_our_parties(case) == 0


# ---------------------------------------------------------------------------
# _get_our_parties / _get_all_parties
# ---------------------------------------------------------------------------

class TestParties:
    def test_get_our_parties_filters(self):
        p1 = _make_party(is_our=True)
        p2 = _make_party(is_our=False, client_id=20)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = [p1, p2]
        svc = _make_service()
        result = svc._get_our_parties(case)
        assert len(result) == 1
        assert result[0].client.is_our_client is True

    def test_get_our_parties_empty_on_error(self):
        case = _make_case()
        case.parties.select_related.return_value.all.side_effect = RuntimeError
        svc = _make_service()
        assert svc._get_our_parties(case) == []

    def test_get_all_parties_returns_all(self):
        p1 = _make_party(is_our=True)
        p2 = _make_party(is_our=False, client_id=20)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = [p1, p2]
        svc = _make_service()
        result = svc._get_all_parties(case)
        assert len(result) == 2

    def test_get_all_parties_empty_on_error(self):
        case = _make_case()
        case.parties.select_related.return_value.all.side_effect = RuntimeError
        svc = _make_service()
        assert svc._get_all_parties(case) == []


# ---------------------------------------------------------------------------
# Filename builders
# ---------------------------------------------------------------------------

class TestFilenameBuilders:
    @patch("apps.documents.services.generation.authorization_material_generation_service.FilenameTemplateService")
    @patch("apps.documents.services.generation.authorization_material_generation_service.timezone")
    def test_build_authority_letter_filename(self, mock_tz, mock_fts):
        mock_tz.now.return_value.strftime.return_value = "20260607"
        mock_fts.render_generated_doc.return_value = "所函_张三诉李四案_V1_20260607"
        svc = _make_service()
        result = svc._build_authority_letter_filename(case_name="张三诉李四案")
        assert result.endswith(".docx")
        mock_fts.render_generated_doc.assert_called_once()

    @patch("apps.documents.services.generation.authorization_material_generation_service.FilenameTemplateService")
    @patch("apps.documents.services.generation.authorization_material_generation_service.timezone")
    def test_build_legal_rep_certificate_filename(self, mock_tz, mock_fts):
        mock_tz.now.return_value.strftime.return_value = "20260607"
        mock_fts.render_generated_doc.return_value = "cert_file"
        svc = _make_service()
        result = svc._build_legal_rep_certificate_filename(company_name="甲公司")
        assert result.endswith(".docx")

    @patch("apps.documents.services.generation.authorization_material_generation_service.FilenameTemplateService")
    @patch("apps.documents.services.generation.authorization_material_generation_service.timezone")
    def test_build_poa_filename_single_party(self, mock_tz, mock_fts):
        mock_tz.now.return_value.strftime.return_value = "20260607"
        mock_fts.render_generated_doc.return_value = "poa"
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = []
        svc = _make_service()
        result = svc._build_power_of_attorney_filename(case=case, selected_clients=[])
        assert result.endswith(".docx")


# ---------------------------------------------------------------------------
# generate_authority_letter_document
# ---------------------------------------------------------------------------

class TestGenerateAuthorityLetter:
    @patch("apps.documents.services.generation.authorization_material_generation_service.FilenameTemplateService")
    @patch("apps.documents.services.generation.authorization_material_generation_service.EnhancedContextBuilder")
    def test_uses_case_binding_when_found(self, mock_builder_cls, mock_fts):
        mock_fts.render_generated_doc.return_value = "所函_文件"
        mock_builder_cls.return_value.build_context.return_value = {}
        case = _make_case()
        svc = _make_service()
        svc.case_service.get_case_model_internal.return_value = case
        svc.case_service.get_case_template_bindings_by_name_internal.return_value = [
            MagicMock(template_id=100)
        ]
        mock_dto = MagicMock()
        mock_dto.file_path = "/templates/suohan.docx"
        svc.document_service.get_template_by_id_internal.return_value = mock_dto
        # Mock Path.exists for the template path check
        with patch("apps.documents.services.generation.authorization_material_generation_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            MockPath.return_value = mock_path
            # DocxRenderer is a local import inside _render_template, patch at source
            with patch("apps.documents.services.generation.pipeline.DocxRenderer") as mock_renderer:
                mock_renderer.return_value.render.return_value = b"content"
                content, filename = svc.generate_authority_letter_document(case_id=1)
                assert content == b"content"
                assert filename.endswith(".docx")

    @patch("apps.documents.services.generation.authorization_material_generation_service.FilenameTemplateService")
    @patch("apps.documents.services.generation.authorization_material_generation_service.EnhancedContextBuilder")
    def test_falls_back_to_hardcoded_path(self, mock_builder_cls, mock_fts):
        mock_fts.render_generated_doc.return_value = "所函_文件"
        mock_builder_cls.return_value.build_context.return_value = {}
        case = _make_case()
        svc = _make_service()
        svc.case_service.get_case_model_internal.return_value = case
        svc.case_service.get_case_template_bindings_by_name_internal.return_value = []
        svc.case_service.get_case_internal.return_value = MagicMock(case_type="litigation", current_stage="first_trial")
        svc.case_service.get_case_template_bindings_by_name_internal.return_value = []
        # Mock the filter query for document templates
        with patch("apps.documents.services.generation.authorization_material_generation_service.DocumentTemplate") as mock_tmpl:
            mock_tmpl.objects.filter.return_value = []
            with patch("apps.documents.services.generation.authorization_material_generation_service.Path") as MockPath:
                mock_path = MagicMock()
                mock_path.exists.return_value = True
                MockPath.return_value = mock_path
                with patch("apps.documents.services.generation.authorization_material_generation_service.get_docx_templates_root") as mock_root:
                    mock_root.return_value.__truediv__ = MagicMock(return_value=MagicMock(__truediv__=MagicMock(return_value=mock_path)))
                    with patch("apps.documents.services.generation.pipeline.DocxRenderer") as mock_renderer:
                        mock_renderer.return_value.render.return_value = b"content"
                        content, filename = svc.generate_authority_letter_document(case_id=1)
                        assert content == b"content"


# ---------------------------------------------------------------------------
# generate_legal_rep_certificate_document
# ---------------------------------------------------------------------------

class TestGenerateLegalRepCertificate:
    @patch("apps.documents.services.generation.authorization_material_generation_service.FilenameTemplateService")
    @patch("apps.documents.services.generation.authorization_material_generation_service.EnhancedContextBuilder")
    def test_basic_generation(self, mock_builder_cls, mock_fts):
        mock_fts.render_generated_doc.return_value = "cert_file"
        mock_builder_cls.return_value.build_context.return_value = {}
        party = _make_party(client_id=10, is_our=True, client_type="legal", client_name="甲公司")
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = [party]
        svc = _make_service()
        svc.case_service.get_case_model_internal.return_value = case
        svc.case_service.get_case_template_bindings_by_name_internal.return_value = []
        svc.case_service.get_case_internal.return_value = MagicMock(case_type="litigation", current_stage="first_trial")
        with patch("apps.documents.services.generation.authorization_material_generation_service.DocumentTemplate") as mock_tmpl:
            mock_tmpl.objects.filter.return_value = []
            with patch("apps.documents.services.generation.authorization_material_generation_service.Path") as MockPath:
                mock_path = MagicMock()
                mock_path.exists.return_value = True
                MockPath.return_value = mock_path
                with patch("apps.documents.services.generation.authorization_material_generation_service.get_docx_templates_root") as mock_root:
                    mock_root.return_value.__truediv__ = MagicMock(return_value=MagicMock(__truediv__=MagicMock(return_value=mock_path)))
                    with patch("apps.documents.services.generation.pipeline.DocxRenderer") as mock_renderer:
                        mock_renderer.return_value.render.return_value = b"cert"
                        content, fn = svc.generate_legal_rep_certificate_document(case_id=1, client_id=10)
                        assert content == b"cert"
                        assert fn.endswith(".docx")


# ---------------------------------------------------------------------------
# generate_power_of_attorney_document
# ---------------------------------------------------------------------------

class TestGeneratePowerOfAttorney:
    @patch("apps.documents.services.generation.authorization_material_generation_service.FilenameTemplateService")
    @patch("apps.documents.services.generation.authorization_material_generation_service.EnhancedContextBuilder")
    def test_uses_case_binding_when_available(self, mock_builder_cls, mock_fts):
        mock_fts.render_generated_doc.return_value = "poa_file"
        mock_builder_cls.return_value.build_context.return_value = {}
        party = _make_party(client_id=10, is_our=True)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = [party]
        svc = _make_service()
        svc.case_service.get_case_model_internal.return_value = case
        svc.case_service.get_case_template_bindings_by_name_internal.return_value = [
            MagicMock(template_id=200)
        ]
        mock_dto = MagicMock()
        mock_dto.file_path = "/templates/poa.docx"
        svc.document_service.get_template_by_id_internal.return_value = mock_dto
        with patch("apps.documents.services.generation.authorization_material_generation_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            MockPath.return_value = mock_path
            with patch("apps.documents.services.generation.pipeline.DocxRenderer") as mock_renderer:
                mock_renderer.return_value.render.return_value = b"poa_content"
                content, fn = svc.generate_power_of_attorney_document(case_id=1, client_id=10)
                assert content == b"poa_content"
                assert fn.endswith(".docx")

    @patch("apps.documents.services.generation.authorization_material_generation_service.FilenameTemplateService")
    @patch("apps.documents.services.generation.authorization_material_generation_service.EnhancedContextBuilder")
    def test_falls_back_to_db_template(self, mock_builder_cls, mock_fts):
        mock_fts.render_generated_doc.return_value = "poa_file"
        mock_builder_cls.return_value.build_context.return_value = {}
        party = _make_party(client_id=10, is_our=True)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = [party]
        svc = _make_service()
        svc.case_service.get_case_model_internal.return_value = case
        svc.case_service.get_case_template_bindings_by_name_internal.return_value = []
        svc.case_service.get_case_internal.return_value = MagicMock(case_type="litigation", current_stage="first_trial")
        with patch("apps.documents.services.generation.authorization_material_generation_service.DocumentTemplate") as mock_tmpl:
            # first call: get_template_path_from_case_bindings -> empty filter
            # second call: _get_power_of_attorney_template_from_db -> returns template
            mock_tmpl.objects.filter.return_value.order_by.return_value.first.return_value = MagicMock(
                get_file_location=MagicMock(return_value="/db/path.docx"), pk=1
            )
            with patch("apps.documents.services.generation.authorization_material_generation_service.Path") as MockPath:
                mock_path = MagicMock()
                mock_path.exists.return_value = True
                MockPath.return_value = mock_path
                with patch("apps.documents.services.generation.pipeline.DocxRenderer") as mock_renderer:
                    mock_renderer.return_value.render.return_value = b"poa"
                    content, fn = svc.generate_power_of_attorney_document(case_id=1, client_id=10)
                    assert content == b"poa"


# ---------------------------------------------------------------------------
# generate_power_of_attorney_combined_document
# ---------------------------------------------------------------------------

class TestGeneratePOACombined:
    @patch("apps.documents.services.generation.authorization_material_generation_service.FilenameTemplateService")
    @patch("apps.documents.services.generation.authorization_material_generation_service.EnhancedContextBuilder")
    def test_multiple_clients(self, mock_builder_cls, mock_fts):
        mock_fts.render_generated_doc.return_value = "poa_combined_file"
        mock_builder_cls.return_value.build_context.return_value = {}
        p1 = _make_party(client_id=10, is_our=True, client_name="张三")
        p2 = _make_party(client_id=20, is_our=True, client_name="李四")
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = [p1, p2]
        svc = _make_service()
        svc.case_service.get_case_model_internal.return_value = case
        svc.case_service.get_case_template_bindings_by_name_internal.return_value = [
            MagicMock(template_id=300)
        ]
        mock_dto = MagicMock()
        mock_dto.file_path = "/templates/poa_combined.docx"
        svc.document_service.get_template_by_id_internal.return_value = mock_dto
        with patch("apps.documents.services.generation.authorization_material_generation_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            MockPath.return_value = mock_path
            with patch("apps.documents.services.generation.pipeline.DocxRenderer") as mock_renderer:
                mock_renderer.return_value.render.return_value = b"combined"
                content, fn = svc.generate_power_of_attorney_combined_document(
                    case_id=1, client_ids=[10, 20]
                )
                assert content == b"combined"


# ---------------------------------------------------------------------------
# _render_template
# ---------------------------------------------------------------------------

class TestRenderTemplate:
    def test_raises_when_file_missing(self):
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with patch("apps.documents.services.generation.authorization_material_generation_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path
            with pytest.raises(ValidationException, match="模板文件不存在"):
                svc._render_template(mock_path, {})

    def test_raises_on_render_error(self):
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with patch("apps.documents.services.generation.authorization_material_generation_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            MockPath.return_value = mock_path
            with patch("apps.documents.services.generation.pipeline.DocxRenderer") as mock_renderer:
                mock_renderer.return_value.render.side_effect = RuntimeError("boom")
                with pytest.raises(ValidationException, match="模板渲染失败"):
                    svc._render_template(mock_path, {})


# ---------------------------------------------------------------------------
# _zip_add_missing_markdown
# ---------------------------------------------------------------------------

class TestZipAddMissingMarkdown:
    def test_writes_deduped_markdown(self):
        svc = _make_service()
        zf = MagicMock()
        svc._zip_add_missing_markdown(zf, missing_lines=["缺少A", "缺少A", "缺少B"])
        zf.writestr.assert_called_once()
        body = zf.writestr.call_args[0][1]
        assert "- 缺少A" in body
        assert "- 缺少B" in body
        # Deduplication: only one "缺少A"
        assert body.count("缺少A") == 1


# ---------------------------------------------------------------------------
# generate_full_authorization_package
# ---------------------------------------------------------------------------

class TestGenerateFullAuthorizationPackage:
    def test_raises_when_no_our_parties(self):
        svc = _make_service()
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = []
        svc.case_service.get_case_model_internal.return_value = case
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="没有我方当事人"):
            svc.generate_full_authorization_package(case_id=1)

    @patch("apps.documents.services.generation.authorization_material_generation_service.zipfile")
    @patch("django.conf.settings")
    def test_generates_zip_with_our_parties(self, mock_settings, mock_zipfile_cls):
        party = _make_party(is_our=True)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value = [party]
        svc = _make_service()
        svc.case_service.get_case_model_internal.return_value = case
        mock_settings.MEDIA_ROOT = "/tmp/media"

        # Mock zip operations
        mock_zf = MagicMock()
        mock_zipfile_cls.ZipFile.return_value.__enter__ = MagicMock(return_value=mock_zf)
        mock_zipfile_cls.ZipFile.return_value.__exit__ = MagicMock(return_value=False)

        with patch("apps.documents.services.generation.authorization_material_generation_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260607"
            # Mock _zip_add_entrust_docs to avoid side effects
            svc._zip_add_entrust_docs = MagicMock()
            svc._zip_add_identity_docs_flat = MagicMock()

            content, filename = svc.generate_full_authorization_package(case_id=1)
            assert filename.endswith(".zip")
            assert isinstance(content, bytes)


# ---------------------------------------------------------------------------
# _DOC_TYPE_LABELS and class constants
# ---------------------------------------------------------------------------

class TestClassConstants:
    def test_doc_type_labels_has_expected_keys(self):
        from apps.documents.services.generation.authorization_material_generation_service import (
            AuthorizationMaterialGenerationService,
        )
        labels = AuthorizationMaterialGenerationService._DOC_TYPE_LABELS
        assert "id_card" in labels
        assert "business_license" in labels
        assert "legal_rep_id_card" in labels

    def test_our_legal_required(self):
        from apps.documents.services.generation.authorization_material_generation_service import (
            AuthorizationMaterialGenerationService,
        )
        assert AuthorizationMaterialGenerationService._OUR_LEGAL_REQUIRED == {"business_license", "legal_rep_id_card"}


# ---------------------------------------------------------------------------
# _has_template_in_case_bindings
# ---------------------------------------------------------------------------

class TestHasTemplateInCaseBindings:
    def test_returns_true_when_path_found(self):
        svc = _make_service()
        svc._get_template_path_from_case_bindings = MagicMock(return_value=Path("/x"))
        assert svc._has_template_in_case_bindings(1, "所函") is True

    def test_returns_false_when_none(self):
        svc = _make_service()
        svc._get_template_path_from_case_bindings = MagicMock(return_value=None)
        assert svc._has_template_in_case_bindings(1, "所函") is False


# ---------------------------------------------------------------------------
# _get_template_path_from_case_bindings
# ---------------------------------------------------------------------------

class TestGetTemplatePathFromCaseBindings:
    def test_returns_path_from_binding(self):
        svc = _make_service()
        svc.case_service.get_case_template_bindings_by_name_internal.return_value = [MagicMock(template_id=100)]
        mock_dto = MagicMock()
        mock_dto.file_path = "/t/a.docx"
        svc.document_service.get_template_by_id_internal.return_value = mock_dto
        result = svc._get_template_path_from_case_bindings(1, "所函")
        assert result is not None

    def test_returns_none_when_no_bindings_and_no_case(self):
        svc = _make_service()
        svc.case_service.get_case_template_bindings_by_name_internal.return_value = []
        svc.case_service.get_case_internal.return_value = None
        result = svc._get_template_path_from_case_bindings(1, "所函")
        assert result is None
