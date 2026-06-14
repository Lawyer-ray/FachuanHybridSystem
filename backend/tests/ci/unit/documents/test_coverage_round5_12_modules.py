"""Coverage tests for documents app — 12 modules.

Covers:
1. models/evidence.py — EvidenceList.__str__, start_order/start_page (via service mock),
   EvidenceItem.__str__
2. services/template/template_service.py — DocumentTemplateService all methods
3. services/extractors/judgment_pdf_extractor.py — JudgmentPdfExtractor
4. services/generation/context_builder.py — ContextBuilder
5. services/generation/contract_generation_service.py — wrappers + ContractGenerationService
6. services/generation/supplementary_agreement_generation_service.py
7. services/folder_template/command_service.py — FolderTemplateCommandService
8. services/placeholders/lawyer/lawyer_info_service.py
9. services/placeholders/party/principal_info_service.py
10. services/template/template_matching_service.py — _matches_case_folder_template, normalize helpers
11. services/template/contract_template/binding_service.py
12. services/template/folder_service.py
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ====================================================================
# 1. Evidence models (evidence.py)
# ====================================================================


class TestEvidenceListStr:
    def test_str_format(self):
        from apps.evidence.models import EvidenceList

        el = EvidenceList.__new__(EvidenceList)
        el._state = MagicMock()
        el.__dict__["case"] = MagicMock()
        el.case.name = "张三诉李四"
        el.title = "证据清单一"
        assert str(el) == "张三诉李四 - 证据清单一"

    def test_str_with_empty_title(self):
        from apps.evidence.models import EvidenceList

        el = EvidenceList.__new__(EvidenceList)
        el._state = MagicMock()
        el.__dict__["case"] = MagicMock()
        el.case.name = "案件A"
        el.title = ""
        assert str(el) == "案件A - "


class TestEvidenceListStartOrder:
    @patch("apps.evidence.models.evidence._get_evidence_service")
    def test_start_order_delegates_to_service(self, mock_factory):
        from apps.evidence.models import EvidenceList

        svc = MagicMock()
        svc.calculate_start_order.return_value = 5
        mock_factory.return_value = svc
        el = EvidenceList.__new__(EvidenceList)
        el._state = MagicMock()
        assert el.start_order == 5
        svc.calculate_start_order.assert_called_once_with(el)


class TestEvidenceListStartPage:
    @patch("apps.evidence.models.evidence._get_evidence_service")
    def test_start_page_delegates_to_service(self, mock_factory):
        from apps.evidence.models import EvidenceList

        svc = MagicMock()
        svc.calculate_start_page.return_value = 3
        mock_factory.return_value = svc
        el = EvidenceList.__new__(EvidenceList)
        el._state = MagicMock()
        assert el.start_page == 3
        svc.calculate_start_page.assert_called_once_with(el)


class TestEvidenceItemStr:
    def test_str_format(self):
        from apps.evidence.models import EvidenceItem

        item = EvidenceItem.__new__(EvidenceItem)
        item.order = 1
        item.name = "起诉状"
        assert str(item) == "1. 起诉状"

    def test_str_zero_order(self):
        from apps.evidence.models import EvidenceItem

        item = EvidenceItem.__new__(EvidenceItem)
        item.order = 0
        item.name = "合同"
        assert str(item) == "0. 合同"


# ====================================================================
# 2. DocumentTemplateService (template_service.py)
# ====================================================================


class TestDocumentTemplateServiceInit:
    def test_default_init(self):
        from apps.documents.services.template.template_service import DocumentTemplateService

        svc = DocumentTemplateService()
        assert svc._repo is None
        assert svc._validator is None
        assert svc._workflow is None

    def test_injected_init(self):
        from apps.documents.services.template.template_service import DocumentTemplateService

        mock_repo = MagicMock()
        mock_validator = MagicMock()
        mock_workflow = MagicMock()
        svc = DocumentTemplateService(repo=mock_repo, validator=mock_validator, workflow=mock_workflow)
        assert svc.repo is mock_repo
        assert svc.validator is mock_validator
        assert svc.workflow is mock_workflow


class TestDocumentTemplateServiceLazyRepo:
    def test_repo_lazy_init(self):
        from apps.documents.services.template.template_service import (
            DocumentTemplateService,
            DocumentTemplateRepo,
        )

        svc = DocumentTemplateService()
        with patch(
            "apps.documents.services.template.template_service.DocumentTemplateRepo",
            return_value=MagicMock(spec=DocumentTemplateRepo),
        ):
            repo = svc.repo
            assert repo is not None


class TestDocumentTemplateServiceValidateFilePath:
    def test_empty_path_returns_false(self):
        from apps.documents.services.template.template_service import DocumentTemplateService

        svc = DocumentTemplateService()
        assert svc.validate_file_path("") is False
        assert svc.validate_file_path(None) is False  # type: ignore[arg-type]

    def test_valid_path_delegates(self):
        from apps.documents.services.template.template_service import DocumentTemplateService

        svc = DocumentTemplateService()
        svc._validator = MagicMock()
        svc._validator.validate_file_path.return_value = True
        assert svc.validate_file_path("/path/to/template.docx") is True


class TestDocumentTemplateServiceGetFullFilePath:
    def test_file_does_not_exist(self):
        from apps.documents.services.template.template_service import DocumentTemplateService

        svc = DocumentTemplateService()
        template = MagicMock()
        template.name = "Test"
        template.pk = 1
        template.get_file_location.return_value = "/nonexistent/path.docx"
        with patch("apps.documents.services.template.template_service.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            result = svc.get_full_file_path(template)
            assert result is None

    def test_file_location_none(self):
        from apps.documents.services.template.template_service import DocumentTemplateService

        svc = DocumentTemplateService()
        template = MagicMock()
        template.name = "Test"
        template.pk = 1
        template.get_file_location.return_value = None
        result = svc.get_full_file_path(template)
        assert result is None

    def test_file_exists(self):
        from apps.documents.services.template.template_service import DocumentTemplateService

        svc = DocumentTemplateService()
        template = MagicMock()
        template.name = "Test"
        template.pk = 1
        template.get_file_location.return_value = "/path/to/file.docx"
        with patch("apps.documents.services.template.template_service.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            result = svc.get_full_file_path(template)
            assert result == "/path/to/file.docx"


class TestDocumentTemplateServiceExtractPlaceholders:
    def test_file_not_found_returns_empty(self):
        from apps.documents.services.template.template_service import DocumentTemplateService

        svc = DocumentTemplateService()
        template = MagicMock()
        template.name = "Test"
        template.pk = 1
        svc.get_full_file_path = MagicMock(return_value=None)
        result = svc.extract_placeholders(template)
        assert result == []

    def test_extraction_succeeds(self):
        from apps.documents.services.template.template_service import DocumentTemplateService

        svc = DocumentTemplateService()
        template = MagicMock()
        template.name = "Test"
        template.pk = 1
        svc.get_full_file_path = MagicMock(return_value="/path/to/file.docx")
        with patch(
            "apps.documents.services.template.template_service.extract_placeholders_from_file",
            return_value=["plaintiff_name", "defendant_name"],
        ):
            result = svc.extract_placeholders(template)
            assert "plaintiff_name" in result

    def test_extraction_exception_propagates(self):
        from apps.documents.services.template.template_service import DocumentTemplateService

        svc = DocumentTemplateService()
        template = MagicMock()
        template.name = "Test"
        template.pk = 1
        svc.get_full_file_path = MagicMock(return_value="/path/to/file.docx")
        with patch(
            "apps.documents.services.template.template_service.extract_placeholders_from_file",
            side_effect=RuntimeError("parse error"),
        ):
            with pytest.raises(RuntimeError, match="parse error"):
                svc.extract_placeholders(template)


class TestDocumentTemplateServiceGetUndefinedPlaceholders:
    def test_no_template_placeholders(self):
        from apps.documents.services.template.template_service import DocumentTemplateService

        svc = DocumentTemplateService()
        template = MagicMock()
        svc.extract_placeholders = MagicMock(return_value=[])
        result = svc.get_undefined_placeholders(template)
        assert result == []

    @pytest.mark.django_db
    def test_all_defined(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        from apps.documents.models import Placeholder

        Placeholder.objects.create(key="name", display_name="Name", is_active=True)
        svc = DocumentTemplateService()
        template = MagicMock()
        svc.extract_placeholders = MagicMock(return_value=["name"])
        result = svc.get_undefined_placeholders(template)
        assert result == []

    @pytest.mark.django_db
    def test_some_undefined(self):
        from apps.documents.services.template.template_service import DocumentTemplateService
        from apps.documents.models import Placeholder

        Placeholder.objects.create(key="name", display_name="Name", is_active=True)
        svc = DocumentTemplateService()
        template = MagicMock()
        svc.extract_placeholders = MagicMock(return_value=["name", "unknown_key"])
        result = svc.get_undefined_placeholders(template)
        assert "unknown_key" in result
        assert "name" not in result


class TestDocumentTemplateServiceGetTemplateById:
    def test_not_found_raises(self):
        from apps.core.exceptions import NotFoundError
        from apps.documents.services.template.template_service import DocumentTemplateService

        svc = DocumentTemplateService()
        svc._repo = MagicMock()
        svc._repo.get_by_id.side_effect = MagicMock(side_effect=type("DoesNotExist", (Exception,), {}))
        # Simulate model DoesNotExist
        from apps.documents.models import DocumentTemplate

        svc._repo.get_by_id.side_effect = DocumentTemplate.DoesNotExist
        with pytest.raises(NotFoundError):
            svc.get_template_by_id(9999)


class TestDocumentTemplateServiceDeleteTemplate:
    @pytest.mark.django_db
    def test_soft_delete(self):
        from apps.documents.services.template.template_service import DocumentTemplateService

        svc = DocumentTemplateService()
        template = MagicMock()
        template.pk = 1
        template.name = "Test"
        svc._repo = MagicMock()
        svc._repo.get_by_id.return_value = template
        result = svc.delete_template(1)
        assert result is True
        assert template.is_active is False
        template.save.assert_called_once()

    def test_delete_not_found_raises(self):
        from apps.core.exceptions import NotFoundError
        from apps.documents.services.template.template_service import DocumentTemplateService
        from apps.documents.models import DocumentTemplate

        svc = DocumentTemplateService()
        svc._repo = MagicMock()
        svc._repo.get_by_id.side_effect = DocumentTemplate.DoesNotExist
        with pytest.raises(NotFoundError):
            svc.delete_template(9999)


class TestDocumentTemplateServiceCreateFromDict:
    def test_delegates_to_workflow(self):
        from apps.documents.services.template.template_service import DocumentTemplateService

        svc = DocumentTemplateService()
        svc._workflow = MagicMock()
        svc._workflow.create_from_dict.return_value = MagicMock()
        result = svc.create_template_from_dict({"name": "Test"})
        svc._workflow.create_from_dict.assert_called_once_with({"name": "Test"})
        assert result is not None


class TestDocumentTemplateServiceUpdateFromDict:
    def test_not_found_raises(self):
        from apps.core.exceptions import NotFoundError
        from apps.documents.services.template.template_service import DocumentTemplateService
        from apps.documents.models import DocumentTemplate

        svc = DocumentTemplateService()
        svc._repo = MagicMock()
        svc._repo.get_by_id.side_effect = DocumentTemplate.DoesNotExist
        with pytest.raises(NotFoundError):
            svc.update_template_from_dict(9999, {"name": "Test"})


# ====================================================================
# 3. JudgmentPdfExtractor (judgment_pdf_extractor.py)
# ====================================================================


class TestExtractionResult:
    def test_default_values(self):
        from apps.documents.services.extractors.judgment_pdf_extractor import ExtractionResult

        r = ExtractionResult()
        assert r.number is None
        assert r.document_name is None
        assert r.content is None

    def test_custom_values(self):
        from apps.documents.services.extractors.judgment_pdf_extractor import ExtractionResult

        r = ExtractionResult(number="2024粤0605民初123号", document_name="民事判决书", content="判决如下：...")
        assert r.number == "2024粤0605民初123号"
        assert r.document_name == "民事判决书"
        assert "判决如下" in r.content


class TestJudgmentPdfExtractorCaseNumber:
    def _make_extractor(self):
        from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

        return JudgmentPdfExtractor()

    def test_extract_standard_case_number(self):
        ext = self._make_extractor()
        text = "广东省佛山市顺德区人民法院（2024）粤0605民初3356号民事判决书"
        result = ext._extract_case_number(text)
        assert result is not None
        assert "粤0605民初3356号" in result

    def test_extract_case_number_with_spaces(self):
        ext = self._make_extractor()
        text = "（2026）黔01 民终1960 号"
        result = ext._extract_case_number(text)
        assert result is not None

    def test_extract_case_number_with_keyword_prefix(self):
        ext = self._make_extractor()
        text = "案号：（2024）粤0606民初38361号"
        result = ext._extract_case_number(text)
        assert result is not None

    def test_no_case_number_returns_none(self):
        ext = self._make_extractor()
        result = ext._extract_case_number("没有案号的文本")
        assert result is None


class TestJudgmentPdfExtractorDocumentName:
    def _make_extractor(self):
        from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

        return JudgmentPdfExtractor()

    def test_find_judgment(self):
        ext = self._make_extractor()
        assert ext._extract_document_name("广东省民事判决书") == "民事判决书"

    def test_find_mediation(self):
        ext = self._make_extractor()
        assert ext._extract_document_name("民事调解书内容") == "民事调解书"

    def test_find_execution_cert(self):
        ext = self._make_extractor()
        assert ext._extract_document_name("执行证书模板") == "执行证书"

    def test_not_found(self):
        ext = self._make_extractor()
        assert ext._extract_document_name("没有任何关键词") is None


class TestJudgmentPdfExtractorMainText:
    def _make_extractor(self):
        from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

        return JudgmentPdfExtractor()

    def test_extract_after_judgment_keyword(self):
        ext = self._make_extractor()
        text = "本院认为，判决如下：一、被告赔偿原告损失10000元。如不服本判决，可上诉。"
        result = ext._extract_main_text(text)
        assert result is not None
        assert "被告赔偿原告损失" in result

    def test_extract_after_mediation_keyword(self):
        ext = self._make_extractor()
        text = "自愿达成如下协议：一、双方解除合同。案件受理费100元"
        result = ext._extract_main_text(text)
        assert result is not None
        assert "双方解除合同" in result

    def test_extract_with_self_reconciliation(self):
        ext = self._make_extractor()
        text = "各方当事人自行和解达成如下协议：一、和解条款。审判员"
        result = ext._extract_main_text(text)
        assert result is not None
        assert "和解条款" in result

    def test_no_keyword_returns_none(self):
        ext = self._make_extractor()
        result = ext._extract_main_text("没有判决关键词的普通文本")
        assert result is None

    def test_extract_truncated_at_end_keyword(self):
        ext = self._make_extractor()
        text = "判决如下：一、赔偿。二、承担诉讼费。案件受理费50元由被告负担。"
        result = ext._extract_main_text(text)
        assert result is not None
        # Should be truncated before "案件受理费"
        assert "案件受理费" not in result


class TestJudgmentPdfExtractorMapNormalized:
    def test_exact_match(self):
        from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

        ext = JudgmentPdfExtractor()
        assert ext._map_normalized_to_original("abc", 0) == 0
        assert ext._map_normalized_to_original("abc", 1) == 1
        assert ext._map_normalized_to_original("abc", 3) == 3

    def test_with_whitespace(self):
        from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

        ext = JudgmentPdfExtractor()
        # "a b c" normalized is "abc" (indices 0,1,2 in normalized)
        assert ext._map_normalized_to_original("a b c", 0) == 0
        assert ext._map_normalized_to_original("a b c", 1) == 2
        assert ext._map_normalized_to_original("a b c", 2) == 4

    def test_index_beyond_text(self):
        from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

        ext = JudgmentPdfExtractor()
        assert ext._map_normalized_to_original("abc", 10) == 3


class TestJudgmentPdfExtractorSanitize:
    def _make_extractor(self):
        from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

        return JudgmentPdfExtractor()

    def test_empty_text(self):
        ext = self._make_extractor()
        assert ext._sanitize_extracted_text(None) == ""
        assert ext._sanitize_extracted_text("") == ""

    def test_normalize_line_endings(self):
        ext = self._make_extractor()
        result = ext._sanitize_extracted_text("line1\r\nline2\rline3")
        assert "\r" not in result

    def test_remove_page_numbers(self):
        ext = self._make_extractor()
        result = ext._sanitize_extracted_text("content\n1\nnext content")
        assert "1\n" not in result or result.count("\n") < 3

    def test_remove_page_noise_literals(self):
        ext = self._make_extractor()
        result = ext._sanitize_extracted_text("正文内容本页无正文后续")
        assert "本页无正文" not in result

    def test_remove_page_noise_patterns(self):
        ext = self._make_extractor()
        result = ext._sanitize_extracted_text("内容第1页共10页内容")
        assert "第1页共10页" not in result

    def test_merge_newlines(self):
        ext = self._make_extractor()
        result = ext._sanitize_extracted_text("line1\n\n\n\nline2")
        assert "\n\n" not in result

    def test_merge_intra_sentence_newline(self):
        ext = self._make_extractor()
        result = ext._sanitize_extracted_text("9991\n号")
        assert "9991号" in result


class TestJudgmentPdfExtractorOllama:
    def _make_extractor(self):
        from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

        return JudgmentPdfExtractor()

    @patch("apps.documents.services.extractors.judgment_pdf_extractor.JudgmentPdfExtractor._extract_with_ollama")
    def test_extract_fallback_to_ollama(self, mock_ollama):
        from apps.documents.services.extractors.judgment_pdf_extractor import ExtractionResult

        mock_ollama.return_value = ExtractionResult(
            number="2024粤01民初1号",
            document_name="民事判决书",
            content="判决如下：一、赔偿10万",
        )
        ext = self._make_extractor()
        # Mock _extract_full_text to return text with no judgment keyword
        with patch.object(ext, "_extract_full_text", return_value=("some text without keyword", "pdf_direct")):
            with patch.object(ext, "_extract_main_text", return_value=None):
                with patch.object(ext, "_extract_case_number", return_value=None):
                    with patch.object(ext, "_extract_document_name", return_value=None):
                        result = ext.extract("/fake/path.pdf")
                        assert result.content is not None
                        mock_ollama.assert_called_once()

    def test_ollama_unavailable(self):
        from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

        ext = JudgmentPdfExtractor()
        with patch(
            "apps.documents.services.extractors.judgment_pdf_extractor.JudgmentPdfExtractor._extract_with_ollama",
            return_value=None,
        ):
            result = ext._extract_with_ollama("text")
            # The method itself should return None when Ollama is unavailable
            assert result is None


class TestJudgmentPdfExtractorExtractRaises:
    @patch("apps.documents.services.extractors.judgment_pdf_extractor.JudgmentPdfExtractor._extract_with_ollama")
    def test_raises_when_no_content(self, mock_ollama):
        from apps.core.exceptions import BusinessException
        from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

        ext = JudgmentPdfExtractor()
        mock_ollama.return_value = None
        with patch.object(ext, "_extract_full_text", return_value=("no keyword text", "pdf_direct")):
            with patch.object(ext, "_extract_main_text", return_value=None):
                with pytest.raises(BusinessException):
                    ext.extract("/fake.pdf")

    def test_raises_on_empty_text(self):
        from apps.core.exceptions import BusinessException
        from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

        ext = JudgmentPdfExtractor()
        with patch.object(ext, "_extract_full_text", return_value=("", "")):
            with pytest.raises(BusinessException):
                ext.extract("/fake.pdf")


# ====================================================================
# 4. ContextBuilder (context_builder.py)
# ====================================================================


class TestContextBuilderInit:
    def test_default_date_format(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder()
        assert cb.date_format == "%Y年%m月%d日"

    def test_custom_date_format(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder(date_format="%Y-%m-%d")
        assert cb.date_format == "%Y-%m-%d"

    def test_use_enhanced_flag(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder(use_enhanced=True)
        assert cb._use_enhanced is True

    def test_injected_contract_service(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        mock_svc = MagicMock()
        cb = ContextBuilder(contract_service=mock_svc)
        assert cb.contract_service is mock_svc


class TestContextBuilderContractServiceLazy:
    @patch("apps.documents.services.generation.context_builder.get_contract_service", create=True)
    def test_lazy_load(self, mock_get):
        from apps.documents.services.generation.context_builder import ContextBuilder

        mock_svc = MagicMock()
        mock_get.return_value = mock_svc
        with patch(
            "apps.documents.services.infrastructure.wiring.get_contract_service",
            return_value=mock_svc,
        ):
            cb = ContextBuilder()
            svc = cb.contract_service
            assert svc is mock_svc


class TestContextBuilderBuildContractContextDirectly:
    def test_contract_not_found_returns_empty(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder()
        cb._contract_service = MagicMock()
        cb._contract_service.get_contract_with_details_internal.return_value = None
        result = cb._build_contract_context_directly(1)
        assert result == {}

    def test_basic_context_building(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder()
        cb._contract_service = MagicMock()
        cb._contract_service.get_contract_with_details_internal.return_value = {
            "name": "测试合同",
            "case_type": "civil",
            "case_type_display": "民商事",
            "status_display": "进行中",
            "specified_date": None,
            "start_date": None,
            "end_date": None,
            "fee_mode": "fixed",
            "fee_mode_display": "固定收费",
            "fixed_amount": Decimal("50000"),
            "risk_rate": Decimal("0.15"),
            "custom_terms": "自定义条款",
            "representation_stages": ["一审", "二审"],
            "contract_parties": [],
            "assignments": [],
        }
        result = cb._build_contract_context_directly(1)
        assert result["contract_name"] == "测试合同"
        assert result["contract_type"] == "民商事"
        assert result["fixed_amount"] == "50,000.00"
        assert "一审" in result["representation_stages"]

    def test_principal_party_fields(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder()
        cb._contract_service = MagicMock()
        cb._contract_service.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [
                {
                    "role": "PRINCIPAL",
                    "client": {"name": "张三", "id_number": "110101", "phone": "13800", "address": "北京"},
                },
                {
                    "role": "BENEFICIARY",
                    "client": {"name": "李四", "id_number": "110102"},
                },
                {
                    "role": "OPPOSING",
                    "client": {"name": "王五"},
                },
            ],
            "assignments": [],
        }
        result = cb._build_contract_context_directly(1)
        assert result["principal_name"] == "张三"
        assert result["principal_id_number"] == "110101"
        assert result["beneficiary_name"] == "李四"
        assert result["opposing_party_name"] == "王五"

    def test_no_parties(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder()
        cb._contract_service = MagicMock()
        cb._contract_service.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [],
            "assignments": [],
        }
        result = cb._build_contract_context_directly(1)
        assert result["principal_name"] == ""
        assert result["beneficiary_name"] == ""
        assert result["opposing_party_name"] == ""

    def test_flat_party_format(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder()
        cb._contract_service = MagicMock()
        cb._contract_service.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [
                {
                    "role": "PRINCIPAL",
                    "client_name": "扁平客户",
                    "id_number": "999",
                    "phone": "123",
                    "address": "地址",
                },
            ],
            "assignments": [],
        }
        result = cb._build_contract_context_directly(1)
        assert result["principal_name"] == "扁平客户"

    def test_primary_lawyer(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder()
        cb._contract_service = MagicMock()
        cb._contract_service.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [],
            "assignments": [
                {
                    "is_primary": True,
                    "lawyer": {"real_name": "律师A", "phone": "111", "license_no": "L001"},
                },
            ],
        }
        result = cb._build_contract_context_directly(1)
        assert result["primary_lawyer_name"] == "律师A"
        assert result["primary_lawyer_license"] == "L001"

    def test_no_primary_uses_first(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder()
        cb._contract_service = MagicMock()
        cb._contract_service.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [],
            "assignments": [
                {
                    "is_primary": False,
                    "lawyer": {"real_name": "律师B", "phone": "222", "license_no": "L002"},
                },
            ],
        }
        result = cb._build_contract_context_directly(1)
        assert result["primary_lawyer_name"] == "律师B"

    def test_no_assignments(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder()
        cb._contract_service = MagicMock()
        cb._contract_service.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "contract_parties": [],
            "assignments": [],
        }
        result = cb._build_contract_context_directly(1)
        assert result["primary_lawyer_name"] == ""
        assert result["all_lawyers"] == []


class TestContextBuilderBuildContractContextEnhanced:
    def test_enhanced_builder_exception_fallback(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder(use_enhanced=True)
        cb._contract_service = MagicMock()
        cb._contract_service.get_contract_with_details_internal.return_value = None
        # Enhanced builder raises
        mock_enhanced = MagicMock()
        mock_enhanced.build_contract_context.side_effect = RuntimeError("fail")
        cb._enhanced_builder = mock_enhanced
        result = cb.build_contract_context(1)
        # Should fall back to direct, which returns empty since contract_service returns None
        assert result == {}

    def test_enhanced_builder_success(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder(use_enhanced=True)
        mock_enhanced = MagicMock()
        mock_enhanced.build_contract_context.return_value = {"key": "enhanced_value"}
        cb._enhanced_builder = mock_enhanced
        result = cb.build_contract_context(1)
        assert result == {"key": "enhanced_value"}


class TestContextBuilderFormatHelpers:
    def test_format_date_none(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder()
        assert cb._format_date(None) == ""

    def test_format_date_valid(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder()
        result = cb._format_date(date(2024, 1, 15))
        assert "2024" in result
        assert "01" in result

    def test_format_currency_none(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder()
        assert cb._format_currency(None) == ""

    def test_format_percentage_none(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        cb = ContextBuilder()
        assert cb._format_percentage(None) == ""


# ====================================================================
# 5. ContractGenerationService (contract_generation_service.py)
# ====================================================================


class TestLawyerWrapper:
    def test_basic_properties(self):
        from apps.documents.services.generation.contract_generation_service import LawyerWrapper

        w = LawyerWrapper({"lawyer_name": "张律师", "username": "zhang", "lawyer_id": 1})
        assert w.real_name == "张律师"
        assert w.username == "zhang"
        assert w.id == 1

    def test_alt_keys(self):
        from apps.documents.services.generation.contract_generation_service import LawyerWrapper

        w = LawyerWrapper({"real_name": "李律师", "id": 2})
        assert w.real_name == "李律师"
        assert w.id == 2

    def test_empty_data(self):
        from apps.documents.services.generation.contract_generation_service import LawyerWrapper

        w = LawyerWrapper({})
        assert w.real_name == ""
        assert w.username == ""
        assert w.id is None

    def test_none_data(self):
        from apps.documents.services.generation.contract_generation_service import LawyerWrapper

        w = LawyerWrapper(None)  # type: ignore[arg-type]
        assert w.real_name == ""


class TestAssignmentWrapper:
    def test_basic(self):
        from apps.documents.services.generation.contract_generation_service import AssignmentWrapper

        w = AssignmentWrapper({"id": 10, "is_primary": True, "order": 1})
        assert w.id == 10
        assert w.is_primary is True
        assert w.order == 1
        assert w.lawyer.real_name == ""

    def test_default_not_primary(self):
        from apps.documents.services.generation.contract_generation_service import AssignmentWrapper

        w = AssignmentWrapper({})
        assert w.is_primary is False


class TestAssignmentListWrapper:
    def test_all(self):
        from apps.documents.services.generation.contract_generation_service import AssignmentListWrapper

        w = AssignmentListWrapper([{"id": 1}, {"id": 2}])
        assert len(w.all()) == 2

    def test_none_items(self):
        from apps.documents.services.generation.contract_generation_service import AssignmentListWrapper

        w = AssignmentListWrapper(None)  # type: ignore[arg-type]
        assert len(w.all()) == 0


class TestContractDataWrapper:
    def test_basic(self):
        from apps.documents.services.generation.contract_generation_service import ContractDataWrapper

        w = ContractDataWrapper({"id": 5, "name": "合同A", "case_type": "civil"})
        assert w.id == 5
        assert w.name == "合同A"
        assert w.case_type == "civil"
        assert len(w.assignments.all()) == 0

    def test_with_assignments(self):
        from apps.documents.services.generation.contract_generation_service import ContractDataWrapper

        w = ContractDataWrapper({"assignments": [{"id": 1}]})
        assert len(w.assignments.all()) == 1


class TestContractGenerationServiceInit:
    def test_default_init(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService

        svc = ContractGenerationService()
        assert svc._contract_service is None
        assert svc._folder_binding_service is None

    def test_injected_init(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService

        mock_cs = MagicMock()
        mock_fbs = MagicMock()
        svc = ContractGenerationService(contract_service=mock_cs, folder_binding_service=mock_fbs)
        assert svc.contract_service is mock_cs
        assert svc.folder_binding_service is mock_fbs


class TestContractGenerationServiceContractNotFound:
    def test_generate_returns_error(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService

        svc = ContractGenerationService()
        svc._contract_service = MagicMock()
        svc._contract_service.get_contract_model_internal.return_value = None
        content, filename, error = svc.generate_contract_document(1)
        assert content is None
        assert error == "合同不存在"


class TestContractGenerationServiceSaveToFolder:
    def test_no_binding_service(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService

        svc = ContractGenerationService()
        result = svc._save_to_bound_folder_if_exists(1, b"data", "file.docx", "subdir")
        assert result is None

    def test_binding_service_succeeds(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService

        svc = ContractGenerationService()
        mock_fbs = MagicMock()
        mock_fbs.save_file_to_bound_folder.return_value = "/saved/path/file.docx"
        svc._folder_binding_service = mock_fbs
        result = svc._save_to_bound_folder_if_exists(1, b"data", "file.docx", "subdir")
        assert result == "/saved/path/file.docx"

    def test_binding_service_exception(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService

        svc = ContractGenerationService()
        mock_fbs = MagicMock()
        mock_fbs.save_file_to_bound_folder.side_effect = RuntimeError("disk error")
        svc._folder_binding_service = mock_fbs
        result = svc._save_to_bound_folder_if_exists(1, b"data", "file.docx", "subdir")
        assert result is None


class TestContractGenerationServiceContractServiceLazy:
    def test_lazy_load(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService

        svc = ContractGenerationService()
        mock_cs = MagicMock()
        with patch(
            "apps.documents.services.infrastructure.wiring.get_contract_service",
            return_value=mock_cs,
        ):
            assert svc.contract_service is mock_cs


# ====================================================================
# 6. SupplementaryAgreementGenerationService
# ====================================================================


class TestSupplementaryAgreementGenerationServiceInit:
    def test_default_init(self):
        from apps.documents.services.generation.supplementary_agreement_generation_service import (
            SupplementaryAgreementGenerationService,
        )

        svc = SupplementaryAgreementGenerationService()
        assert svc._contract_service is None

    def test_injected(self):
        from apps.documents.services.generation.supplementary_agreement_generation_service import (
            SupplementaryAgreementGenerationService,
        )

        mock_cs = MagicMock()
        svc = SupplementaryAgreementGenerationService(contract_service=mock_cs)
        assert svc.contract_service is mock_cs


class TestSupplementaryAgreementContractNotFound:
    def test_generate_contract_data_none(self):
        from apps.documents.services.generation.supplementary_agreement_generation_service import (
            SupplementaryAgreementGenerationService,
        )

        svc = SupplementaryAgreementGenerationService()
        svc._contract_service = MagicMock()
        svc._contract_service.get_contract_with_details_internal.return_value = None
        content, filename, error = svc.generate_supplementary_agreement(1, 1)
        assert error == "合同不存在"

    def test_generate_contract_model_none(self):
        from apps.documents.services.generation.supplementary_agreement_generation_service import (
            SupplementaryAgreementGenerationService,
        )

        svc = SupplementaryAgreementGenerationService()
        svc._contract_service = MagicMock()
        svc._contract_service.get_contract_with_details_internal.return_value = {"case_type": "civil"}
        svc._contract_service.get_contract_model_internal.return_value = None
        content, filename, error = svc.generate_supplementary_agreement(1, 1)
        assert error == "合同不存在"

    def test_generate_agreement_none(self):
        from apps.documents.services.generation.supplementary_agreement_generation_service import (
            SupplementaryAgreementGenerationService,
        )

        svc = SupplementaryAgreementGenerationService()
        svc._contract_service = MagicMock()
        svc._contract_service.get_contract_with_details_internal.return_value = {"case_type": "civil"}
        svc._contract_service.get_contract_model_internal.return_value = MagicMock()
        svc._contract_service.get_supplementary_agreement_model_internal.return_value = None
        content, filename, error = svc.generate_supplementary_agreement(1, 1)
        assert error == "补充协议不存在"


class TestSupplementaryAgreementNoTemplate:
    def test_no_template(self):
        from apps.documents.services.generation.supplementary_agreement_generation_service import (
            SupplementaryAgreementGenerationService,
        )

        svc = SupplementaryAgreementGenerationService()
        svc._contract_service = MagicMock()
        svc._contract_service.get_contract_with_details_internal.return_value = {"case_type": "civil"}
        svc._contract_service.get_contract_model_internal.return_value = MagicMock()
        svc._contract_service.get_supplementary_agreement_model_internal.return_value = MagicMock()
        with patch(
            "apps.documents.services.generation.pipeline.TemplateMatcher",
        ) as mock_tm:
            mock_tm.return_value.match_supplementary_agreement_template.return_value = None
            content, filename, error = svc.generate_supplementary_agreement(1, 1)
            assert error == "请先添加补充协议模板"


class TestSupplementaryAgreementSaveToFolder:
    def test_no_binding(self):
        from apps.documents.services.generation.supplementary_agreement_generation_service import (
            SupplementaryAgreementGenerationService,
        )

        svc = SupplementaryAgreementGenerationService()
        result = svc._save_to_bound_folder_if_exists(1, b"data", "file.docx", "sub")
        assert result is None

    def test_binding_exception(self):
        from apps.documents.services.generation.supplementary_agreement_generation_service import (
            SupplementaryAgreementGenerationService,
        )

        svc = SupplementaryAgreementGenerationService()
        mock_fbs = MagicMock()
        mock_fbs.save_file_for_contract.side_effect = RuntimeError("IO error")
        svc._folder_binding_service = mock_fbs
        result = svc._save_to_bound_folder_if_exists(1, b"data", "file.docx", "sub")
        assert result is None


class TestSupplementaryAgreementContextHelpers:
    def _make_service(self):
        from apps.documents.services.generation.supplementary_agreement_generation_service import (
            SupplementaryAgreementGenerationService,
        )

        return SupplementaryAgreementGenerationService()

    def test_get_agreement_principals(self):
        svc = self._make_service()
        mock_agreement = MagicMock()
        mock_party = MagicMock()
        mock_party.client = "client1"
        mock_agreement.parties.filter.return_value = [mock_party]
        result = svc._get_agreement_principals(mock_agreement)
        assert len(result) == 1
        mock_agreement.parties.filter.assert_called_with(role="PRINCIPAL")

    def test_get_contract_principals(self):
        svc = self._make_service()
        mock_contract = MagicMock()
        mock_cp = MagicMock()
        mock_cp.client = "client2"
        mock_contract.contract_parties.filter.return_value = [mock_cp]
        result = svc._get_contract_principals(mock_contract)
        assert len(result) == 1

    def test_get_agreement_opposing(self):
        svc = self._make_service()
        mock_agreement = MagicMock()
        mock_party = MagicMock()
        mock_party.client = "opposing_client"
        mock_agreement.parties.filter.return_value = [mock_party]
        result = svc._get_agreement_opposing(mock_agreement)
        assert result == ["opposing_client"]


# ====================================================================
# 7. FolderTemplateCommandService (command_service.py)
# ====================================================================


class TestFolderTemplateCommandServiceCreate:
    def _make_service(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService

        mock_repo = MagicMock()
        mock_validation = MagicMock()
        mock_structure = MagicMock()
        return FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_structure,
        )

    @pytest.mark.django_db
    def test_create_template_success(self):
        svc = self._make_service()
        svc.validation_service.validate_structure.return_value = (True, "")
        svc.structure_rules.validate_structure_ids.return_value = (True, [])
        svc.repo.create.return_value = MagicMock()
        result = svc.create_template(
            name="Test",
            case_type="civil",
            case_stage="first_trial",
            structure={"children": []},
        )
        assert result is not None
        svc.repo.create.assert_called_once()

    @pytest.mark.django_db
    def test_create_template_invalid_structure(self):
        from apps.core.exceptions import ValidationException

        svc = self._make_service()
        svc.validation_service.validate_structure.return_value = (False, "结构无效")
        with pytest.raises(ValidationException, match="结构无效"):
            svc.create_template(
                name="Test",
                case_type="civil",
                case_stage="first_trial",
                structure={"children": []},
            )

    @pytest.mark.django_db
    def test_create_template_invalid_ids(self):
        from apps.core.exceptions import ValidationException

        svc = self._make_service()
        svc.validation_service.validate_structure.return_value = (True, "")
        svc.structure_rules.validate_structure_ids.return_value = (False, ["重复ID"])
        with pytest.raises(ValidationException, match="文件夹结构验证失败"):
            svc.create_template(
                name="Test",
                case_type="civil",
                case_stage="first_trial",
                structure={"children": []},
            )


class TestFolderTemplateCommandServiceUpdateStructure:
    @pytest.mark.django_db
    def test_template_not_found(self):
        from apps.core.exceptions import NotFoundError
        from apps.documents.models import FolderTemplate
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService

        svc = self._make_service()
        svc.repo.get_by_id.side_effect = FolderTemplate.DoesNotExist
        with pytest.raises(NotFoundError):
            svc.update_structure(template_id=999, structure={"children": []})

    @pytest.mark.django_db
    def test_update_success(self):
        svc = self._make_service()
        mock_template = MagicMock()
        svc.repo.get_by_id.return_value = mock_template
        svc.validation_service.validate_structure.return_value = (True, "")
        svc.structure_rules.validate_structure_ids.return_value = (True, [])
        result = svc.update_structure(template_id=1, structure={"children": []})
        assert result is not None
        mock_template.save.assert_called_once()

    def _make_service(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService

        mock_repo = MagicMock()
        mock_validation = MagicMock()
        mock_structure = MagicMock()
        return FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_structure,
        )


class TestFolderTemplateCommandServiceDelete:
    @pytest.mark.django_db
    def test_delete_success(self):
        svc = self._make_service()
        mock_template = MagicMock()
        svc.repo.get_by_id.return_value = mock_template
        result = svc.delete_template(template_id=1)
        assert result is True
        assert mock_template.is_active is False
        mock_template.save.assert_called_once()

    @pytest.mark.django_db
    def test_delete_not_found(self):
        from apps.core.exceptions import NotFoundError
        from apps.documents.models import FolderTemplate

        svc = self._make_service()
        svc.repo.get_by_id.side_effect = FolderTemplate.DoesNotExist
        with pytest.raises(NotFoundError):
            svc.delete_template(template_id=999)

    def _make_service(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService

        mock_repo = MagicMock()
        mock_validation = MagicMock()
        mock_structure = MagicMock()
        return FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_structure,
        )


class TestFolderTemplateCommandServiceCreateFromDict:
    @pytest.mark.django_db
    def test_create_from_dict(self):
        svc = self._make_service()
        svc.validation_service.validate_structure.return_value = (True, "")
        svc.structure_rules.validate_structure_ids.return_value = (True, [])
        svc.repo.create.return_value = MagicMock()
        data = {
            "name": "Test",
            "case_type": "civil",
            "case_stage": "first_trial",
            "structure": {"children": []},
        }
        result = svc.create_template_from_dict(data=data)
        assert result is not None

    @pytest.mark.django_db
    def test_create_from_dict_with_extra_fields(self):
        svc = self._make_service()
        svc.validation_service.validate_structure.return_value = (True, "")
        svc.structure_rules.validate_structure_ids.return_value = (True, [])
        svc.repo.create.return_value = MagicMock()
        data = {
            "name": "Test",
            "case_type": "civil",
            "case_stage": "first_trial",
            "structure": {"children": []},
            "template_type": "contract",
            "case_types": ["civil"],
        }
        result = svc.create_template_from_dict(data=data)
        assert result is not None

    def _make_service(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService

        mock_repo = MagicMock()
        mock_validation = MagicMock()
        mock_structure = MagicMock()
        return FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_structure,
        )


class TestFolderTemplateCommandServiceUpdateFromDict:
    @pytest.mark.django_db
    def test_update_from_dict_with_structure(self):
        svc = self._make_service()
        mock_template = MagicMock()
        svc.repo.get_by_id.return_value = mock_template
        svc.validation_service.validate_structure.return_value = (True, "")
        svc.structure_rules.validate_structure_ids.return_value = (True, [])
        result = svc.update_template_from_dict(
            template_id=1,
            data={"structure": {"children": []}, "name": "Updated"},
        )
        assert result is not None

    def test_update_from_dict_no_structure(self):
        svc = self._make_service()
        mock_template = MagicMock()
        svc.repo.get_by_id.return_value = mock_template
        result = svc.update_template_from_dict(
            template_id=1,
            data={"name": "Updated"},
        )
        assert result is not None

    def test_get_template_or_404_not_found(self):
        from apps.core.exceptions import NotFoundError
        from apps.documents.models import FolderTemplate

        svc = self._make_service()
        svc.repo.get_by_id.side_effect = FolderTemplate.DoesNotExist
        with pytest.raises(NotFoundError):
            svc.get_template_or_404(999)

    def _make_service(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService

        mock_repo = MagicMock()
        mock_validation = MagicMock()
        mock_structure = MagicMock()
        return FolderTemplateCommandService(
            repo=mock_repo,
            validation_service=mock_validation,
            structure_rules=mock_structure,
        )


class TestFolderTemplateCommandServiceClearCache:
    @patch("apps.core.infrastructure.bump_cache_version")
    @patch("apps.core.infrastructure.CacheKeys")
    @patch("apps.core.infrastructure.CacheTimeout")
    def test_clear_cache(self, mock_timeout, mock_keys, mock_bump):
        svc = self._make_service()
        svc._clear_folder_template_cache()
        mock_bump.assert_called_once()

    def _make_service(self):
        from apps.documents.services.folder_template.command_service import FolderTemplateCommandService

        return FolderTemplateCommandService(
            repo=MagicMock(),
            validation_service=MagicMock(),
            structure_rules=MagicMock(),
        )


# ====================================================================
# 8. LawyerInfoService (lawyer_info_service.py)
# ====================================================================


class TestLawyerInfoServiceGenerate:
    def _make_service(self):
        from apps.documents.services.placeholders.lawyer.lawyer_info_service import LawyerInfoService

        return LawyerInfoService.__new__(LawyerInfoService)

    def test_no_contract(self):
        svc = self._make_service()
        result = svc.generate({})
        assert result == {}

    def test_with_assignments(self):
        svc = self._make_service()
        mock_lawyer = MagicMock()
        mock_lawyer.real_name = "律师A"
        mock_lawyer.username = "a"
        mock_assignment = MagicMock()
        mock_assignment.lawyer = mock_lawyer
        mock_assignment.is_primary = True
        mock_contract = MagicMock()
        mock_contract.assignments.all.return_value = [mock_assignment]
        result = svc.generate({"contract": mock_contract})
        assert "律师姓名" in result
        assert "主办律师" in result
        assert "协办律师" in result

    def test_with_multiple_lawyers(self):
        svc = self._make_service()
        mock_lawyer1 = MagicMock()
        mock_lawyer1.real_name = "主办律师"
        mock_lawyer1.username = "p"
        mock_lawyer2 = MagicMock()
        mock_lawyer2.real_name = "协办律师"
        mock_lawyer2.username = "a"
        mock_a1 = MagicMock()
        mock_a1.lawyer = mock_lawyer1
        mock_a1.is_primary = True
        mock_a2 = MagicMock()
        mock_a2.lawyer = mock_lawyer2
        mock_a2.is_primary = False
        mock_contract = MagicMock()
        mock_contract.assignments.all.return_value = [mock_a1, mock_a2]
        result = svc.generate({"contract": mock_contract})
        assert "、" in result["律师姓名"]


class TestLawyerInfoServiceFormatLawyerNames:
    def _make_service(self):
        from apps.documents.services.placeholders.lawyer.lawyer_info_service import LawyerInfoService

        return LawyerInfoService.__new__(LawyerInfoService)

    def test_empty_assignments(self):
        svc = self._make_service()
        assert svc.format_lawyer_names([]) == ""


class TestLawyerInfoServiceGetPrimaryLawyer:
    def _make_service(self):
        from apps.documents.services.placeholders.lawyer.lawyer_info_service import LawyerInfoService

        return LawyerInfoService.__new__(LawyerInfoService)

    def test_no_primary_returns_first(self):
        svc = self._make_service()
        mock_lawyer = MagicMock()
        mock_lawyer.real_name = "律师A"
        mock_lawyer.username = "a"
        mock_assignment = MagicMock()
        mock_assignment.lawyer = mock_lawyer
        mock_assignment.is_primary = False
        result = svc._get_primary_lawyer_name([mock_assignment])
        assert result == "律师A"

    def test_empty_list(self):
        svc = self._make_service()
        assert svc._get_primary_lawyer_name([]) == ""


class TestLawyerInfoServiceGetLawyerName:
    def _make_service(self):
        from apps.documents.services.placeholders.lawyer.lawyer_info_service import LawyerInfoService

        return LawyerInfoService.__new__(LawyerInfoService)

    def test_real_name_preferred(self):
        svc = self._make_service()
        mock_lawyer = MagicMock()
        mock_lawyer.real_name = "真实姓名"
        mock_lawyer.username = "username"
        mock_assignment = MagicMock()
        mock_assignment.lawyer = mock_lawyer
        mock_assignment.id = 1
        assert svc._get_lawyer_name(mock_assignment) == "真实姓名"

    def test_username_fallback(self):
        svc = self._make_service()
        mock_lawyer = MagicMock()
        mock_lawyer.real_name = ""
        mock_lawyer.username = "fallback_name"
        mock_assignment = MagicMock()
        mock_assignment.lawyer = mock_lawyer
        mock_assignment.id = 1
        assert svc._get_lawyer_name(mock_assignment) == "fallback_name"

    def test_no_lawyer(self):
        svc = self._make_service()
        mock_assignment = MagicMock()
        mock_assignment.lawyer = None
        mock_assignment.id = 1
        assert svc._get_lawyer_name(mock_assignment) == ""

    def test_exception_returns_empty(self):
        svc = self._make_service()

        class BadLawyer:
            def __getattr__(self, name):
                raise RuntimeError("error")

        mock_assignment = MagicMock()
        mock_assignment.lawyer = BadLawyer()
        mock_assignment.id = 1
        # The method catches all exceptions and returns ""
        result = svc._get_lawyer_name(mock_assignment)
        assert result == ""


class TestLawyerInfoServiceGetAssistantLawyers:
    def _make_service(self):
        from apps.documents.services.placeholders.lawyer.lawyer_info_service import LawyerInfoService

        return LawyerInfoService.__new__(LawyerInfoService)

    def test_only_assistants(self):
        svc = self._make_service()
        mock_lawyer = MagicMock()
        mock_lawyer.real_name = "助手律师"
        mock_lawyer.username = "a"
        mock_a = MagicMock()
        mock_a.lawyer = mock_lawyer
        mock_a.is_primary = False
        mock_a.id = 1
        result = svc._get_assistant_lawyer_names([mock_a])
        assert "助手律师" in result

    def test_no_assistants(self):
        svc = self._make_service()
        mock_lawyer = MagicMock()
        mock_lawyer.real_name = "主办律师"
        mock_lawyer.username = "p"
        mock_a = MagicMock()
        mock_a.lawyer = mock_lawyer
        mock_a.is_primary = True
        mock_a.id = 1
        result = svc._get_assistant_lawyer_names([mock_a])
        assert result == ""


# ====================================================================
# 9. PrincipalInfoService (principal_info_service.py)
# ====================================================================


class TestPrincipalInfoServiceGenerate:
    def _make_service(self):
        from apps.documents.services.placeholders.party.principal_info_service import PrincipalInfoService

        return PrincipalInfoService.__new__(PrincipalInfoService)

    def test_no_contract(self):
        svc = self._make_service()
        result = svc.generate({})
        assert result == {}

    def test_with_principals(self):
        svc = self._make_service()
        mock_client = MagicMock()
        mock_client.name = "张三"
        mock_client.client_type = "natural"
        mock_client.id_number = "110101"
        mock_client.address = "北京"
        mock_client.phone = "13800"
        mock_cp = MagicMock()
        mock_cp.role = "PRINCIPAL"
        mock_cp.client = mock_client
        mock_contract = MagicMock()
        mock_contract.contract_parties.all.return_value = [mock_cp]
        result = svc.generate({"contract": mock_contract})
        assert "委托人名称" in result
        assert result["委托人名称"] == "张三"
        assert result["委托人数量"] == 1


class TestPrincipalInfoServiceGetPrincipals:
    def _make_service(self):
        from apps.documents.services.placeholders.party.principal_info_service import PrincipalInfoService

        return PrincipalInfoService.__new__(PrincipalInfoService)

    def test_filters_principal_role(self):
        svc = self._make_service()
        mock_cp1 = MagicMock()
        mock_cp1.role = "PRINCIPAL"
        mock_cp1.client = "client1"
        mock_cp2 = MagicMock()
        mock_cp2.role = "BENEFICIARY"
        mock_cp2.client = "client2"
        mock_contract = MagicMock()
        mock_contract.contract_parties.all.return_value = [mock_cp1, mock_cp2]
        result = svc._get_principals(mock_contract)
        assert len(result) == 1


class TestPrincipalInfoServiceFormatPrincipalNames:
    def _make_service(self):
        from apps.documents.services.placeholders.party.principal_info_service import PrincipalInfoService

        return PrincipalInfoService.__new__(PrincipalInfoService)

    def test_empty(self):
        svc = self._make_service()
        assert svc.format_principal_names([]) == ""

    def test_single(self):
        svc = self._make_service()
        mock_client = MagicMock()
        mock_client.name = "张三"
        assert svc.format_principal_names([mock_client]) == "张三"

    def test_multiple(self):
        svc = self._make_service()
        c1 = MagicMock(name="c1")
        c1.name = "张三"
        c2 = MagicMock(name="c2")
        c2.name = "李四"
        result = svc.format_principal_names([c1, c2])
        assert "张三、李四" in result


class TestPrincipalInfoServiceFormatPrincipalInfo:
    def _make_service(self):
        from apps.documents.services.placeholders.party.principal_info_service import PrincipalInfoService

        return PrincipalInfoService.__new__(PrincipalInfoService)

    def test_empty(self):
        svc = self._make_service()
        assert svc.format_principal_info([]) == ""

    def test_single_natural(self):
        svc = self._make_service()
        mock_client = MagicMock()
        mock_client.name = "张三"
        mock_client.client_type = "natural"
        mock_client.id_number = "110101"
        mock_client.address = "北京"
        mock_client.phone = "13800"
        mock_client.legal_representative = ""
        result = svc.format_principal_info([mock_client])
        assert "甲方：张三" in result
        assert "身份证号码" in result

    def test_single_legal(self):
        svc = self._make_service()
        mock_client = MagicMock()
        mock_client.name = "某公司"
        mock_client.client_type = "legal"
        mock_client.id_number = "91440101"
        mock_client.address = "广州"
        mock_client.phone = "0201234"
        mock_client.legal_representative = "法定代表人A"
        result = svc.format_principal_info([mock_client])
        assert "甲方：某公司" in result
        assert "统一社会信用代码" in result
        assert "法定代表人" in result

    def test_multiple(self):
        svc = self._make_service()
        c1 = MagicMock()
        c1.name = "张三"
        c1.client_type = "natural"
        c1.id_number = "110"
        c1.address = "北京"
        c1.phone = "111"
        c1.legal_representative = ""
        c2 = MagicMock()
        c2.name = "李四"
        c2.client_type = "natural"
        c2.id_number = "220"
        c2.address = "上海"
        c2.phone = "222"
        c2.legal_representative = ""
        result = svc.format_principal_info([c1, c2])
        assert "甲方一" in result
        assert "甲方二" in result


class TestPrincipalInfoServiceFormatClientDetails:
    def _make_service(self):
        from apps.documents.services.placeholders.party.principal_info_service import PrincipalInfoService

        return PrincipalInfoService.__new__(PrincipalInfoService)

    def test_natural_person(self):
        svc = self._make_service()
        mock_client = MagicMock()
        mock_client.client_type = "natural"
        mock_client.id_number = "110101"
        mock_client.address = "北京"
        mock_client.phone = "138"
        mock_client.legal_representative = ""
        result = svc._format_client_details(mock_client)
        assert any("身份证号码" in line for line in result)

    def test_legal_person(self):
        svc = self._make_service()
        mock_client = MagicMock()
        mock_client.client_type = "legal"
        mock_client.id_number = "91440101"
        mock_client.address = "广州"
        mock_client.phone = "020"
        mock_client.legal_representative = "法人代表"
        result = svc._format_client_details(mock_client)
        assert any("统一社会信用代码" in line for line in result)
        assert any("法定代表人" in line for line in result)

    def test_no_client_type(self):
        svc = self._make_service()
        mock_client = MagicMock()
        mock_client.client_type = None
        mock_client.id_number = ""
        mock_client.address = "地址"
        mock_client.phone = "电话"
        mock_client.legal_representative = ""
        result = svc._format_client_details(mock_client)
        assert any("地址" in line for line in result)


# ====================================================================
# 10. TemplateMatchingService (template_matching_service.py)
# ====================================================================


class TestTemplateMatchingServiceMatchesCaseFolder:
    def _make_service(self):
        from apps.documents.services.template.template_matching_service import TemplateMatchingService

        return TemplateMatchingService()

    def test_case_type_not_matching(self):
        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.case_types = ["criminal"]
        tmpl.legal_statuses = []
        assert svc._matches_case_folder_template(tmpl, "civil", set()) is False

    def test_case_type_matching(self):
        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.case_types = ["civil"]
        tmpl.legal_statuses = []
        assert svc._matches_case_folder_template(tmpl, "civil", set()) is True

    def test_case_type_all(self):
        from apps.documents.models.choices import LegalStatusMatchMode

        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.case_types = [LegalStatusMatchMode.ALL]
        tmpl.legal_statuses = []
        assert svc._matches_case_folder_template(tmpl, "civil", set()) is True

    def test_empty_case_types(self):
        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.case_types = []
        tmpl.legal_statuses = []
        assert svc._matches_case_folder_template(tmpl, "civil", set()) is True

    def test_legal_status_any_match(self):
        from apps.documents.models.choices import LegalStatusMatchMode

        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.case_types = ["civil"]
        tmpl.legal_statuses = ["defendant"]
        tmpl.legal_status_match_mode = LegalStatusMatchMode.ANY
        assert svc._matches_case_folder_template(tmpl, "civil", {"defendant"}) is True

    def test_legal_status_any_no_match(self):
        from apps.documents.models.choices import LegalStatusMatchMode

        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.case_types = ["civil"]
        tmpl.legal_statuses = ["defendant"]
        tmpl.legal_status_match_mode = LegalStatusMatchMode.ANY
        assert svc._matches_case_folder_template(tmpl, "civil", {"plaintiff"}) is False

    def test_legal_status_any_empty_input(self):
        from apps.documents.models.choices import LegalStatusMatchMode

        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.case_types = ["civil"]
        tmpl.legal_statuses = ["defendant"]
        tmpl.legal_status_match_mode = LegalStatusMatchMode.ANY
        # Empty case_legal_statuses_set → returns True (no filter)
        assert svc._matches_case_folder_template(tmpl, "civil", set()) is True

    def test_legal_status_all_match(self):
        from apps.documents.models.choices import LegalStatusMatchMode

        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.case_types = ["civil"]
        tmpl.legal_statuses = ["defendant", "plaintiff"]
        tmpl.legal_status_match_mode = LegalStatusMatchMode.ALL
        assert svc._matches_case_folder_template(tmpl, "civil", {"defendant", "plaintiff"}) is True

    def test_legal_status_all_partial(self):
        from apps.documents.models.choices import LegalStatusMatchMode

        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.case_types = ["civil"]
        tmpl.legal_statuses = ["defendant", "plaintiff"]
        tmpl.legal_status_match_mode = LegalStatusMatchMode.ALL
        assert svc._matches_case_folder_template(tmpl, "civil", {"defendant"}) is False

    def test_legal_status_exact_match(self):
        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.case_types = ["civil"]
        tmpl.legal_statuses = ["defendant"]
        tmpl.legal_status_match_mode = "exact"
        assert svc._matches_case_folder_template(tmpl, "civil", {"defendant"}) is True

    def test_legal_status_exact_mismatch(self):
        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.case_types = ["civil"]
        tmpl.legal_statuses = ["defendant", "plaintiff"]
        tmpl.legal_status_match_mode = "exact"
        assert svc._matches_case_folder_template(tmpl, "civil", {"defendant"}) is False

    def test_legal_status_none_defaults_any(self):
        from apps.documents.models.choices import LegalStatusMatchMode

        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.case_types = ["civil"]
        tmpl.legal_statuses = ["defendant"]
        tmpl.legal_status_match_mode = None
        # defaults to ANY
        assert svc._matches_case_folder_template(tmpl, "civil", {"defendant"}) is True


class TestTemplateMatchingServiceNormalizeInstitutions:
    def _make_service(self):
        from apps.documents.services.template.template_matching_service import TemplateMatchingService

        return TemplateMatchingService()

    def test_empty(self):
        svc = self._make_service()
        assert svc._normalize_institutions(None) == []
        assert svc._normalize_institutions([]) == []

    def test_dedup(self):
        svc = self._make_service()
        result = svc._normalize_institutions(["广州", "广州", "深圳"])
        assert result == ["广州", "深圳"]

    def test_blank_filtered(self):
        svc = self._make_service()
        result = svc._normalize_institutions(["", "  ", "valid"])
        assert result == ["valid"]


class TestTemplateMatchingServiceNormalizeCaseStage:
    def _make_service(self):
        from apps.documents.services.template.template_matching_service import TemplateMatchingService

        return TemplateMatchingService()

    def test_empty(self):
        svc = self._make_service()
        assert svc._normalize_case_stage_for_document("") == []

    def test_retrial_maps_to_retrial(self):
        from apps.documents.models.choices import DocumentCaseStage

        svc = self._make_service()
        result = svc._normalize_case_stage_for_document("retrial_first")
        assert DocumentCaseStage.RETRIAL in result

    def test_normal_stage(self):
        svc = self._make_service()
        result = svc._normalize_case_stage_for_document("first_trial")
        assert "first_trial" in result


class TestTemplateMatchingServiceMatchesTemplateInstitutions:
    def _make_service(self):
        from apps.documents.services.template.template_matching_service import TemplateMatchingService

        return TemplateMatchingService()

    def test_no_template_institutions_guangzhou(self):
        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.applicable_institutions = None
        tmpl.name = "广州法院模板"
        assert svc._matches_template_institutions(tmpl, ["广州"]) is True

    def test_no_template_institutions_no_guangzhou(self):
        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.applicable_institutions = None
        tmpl.name = "深圳法院模板"
        assert svc._matches_template_institutions(tmpl, ["广州"]) is True

    def test_template_institutions_match(self):
        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.applicable_institutions = ["广州"]
        assert svc._matches_template_institutions(tmpl, ["广州"]) is True

    def test_no_case_institutions(self):
        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.applicable_institutions = ["广州"]
        assert svc._matches_template_institutions(tmpl, []) is False

    def test_partial_match(self):
        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.applicable_institutions = ["广州"]
        assert svc._matches_template_institutions(tmpl, ["广州市中级人民法院"]) is True


# ====================================================================
# 11. DocumentTemplateBindingService (binding_service.py)
# ====================================================================


class TestBindingServiceCalculateFolderPath:
    def _make_service(self):
        from apps.documents.services.template.contract_template.binding_service import (
            DocumentTemplateBindingService,
        )

        return DocumentTemplateBindingService()

    def test_empty_structure(self):
        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.structure = {}
        assert svc.calculate_folder_path(tmpl, "node1") == ""

    def test_node_found_at_top_level(self):
        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.structure = {
            "children": [
                {"id": "node1", "name": "一级目录"},
            ],
        }
        assert svc.calculate_folder_path(tmpl, "node1") == "一级目录"

    def test_node_found_nested(self):
        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.structure = {
            "children": [
                {
                    "id": "parent",
                    "name": "父目录",
                    "children": [
                        {"id": "child1", "name": "子目录"},
                    ],
                },
            ],
        }
        assert svc.calculate_folder_path(tmpl, "child1") == "父目录/子目录"

    def test_node_not_found(self):
        svc = self._make_service()
        tmpl = MagicMock()
        tmpl.structure = {
            "children": [{"id": "a", "name": "A"}],
        }
        assert svc.calculate_folder_path(tmpl, "nonexistent") == ""


class TestBindingServiceFindNodePath:
    def _make_service(self):
        from apps.documents.services.template.contract_template.binding_service import (
            DocumentTemplateBindingService,
        )

        return DocumentTemplateBindingService()

    def test_found_direct(self):
        svc = self._make_service()
        children = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        path_parts: list[str] = []
        assert svc._find_node_path(children, "a", path_parts) is True
        assert path_parts == ["A"]

    def test_found_nested(self):
        svc = self._make_service()
        children = [
            {
                "id": "parent",
                "name": "Parent",
                "children": [{"id": "child", "name": "Child"}],
            }
        ]
        path_parts: list[str] = []
        assert svc._find_node_path(children, "child", path_parts) is True
        assert "Parent" in path_parts
        assert "Child" in path_parts

    def test_not_found(self):
        svc = self._make_service()
        children = [{"id": "a", "name": "A"}]
        path_parts: list[str] = []
        assert svc._find_node_path(children, "missing", path_parts) is False
        assert path_parts == []


# ====================================================================
# 12. FolderTemplateService (folder_service.py)
# ====================================================================


class TestFolderTemplateServiceCheckCircularReference:
    def _make_service(self):
        from apps.documents.services.template.folder_service import FolderTemplateService

        svc = FolderTemplateService.__new__(FolderTemplateService)
        svc.usecases = MagicMock()
        return svc

    def test_no_children(self):
        svc = self._make_service()
        assert svc._check_circular_reference({}) == (False, "")

    def test_no_cycle(self):
        svc = self._make_service()
        structure = {
            "children": [
                {"id": "a", "name": "A"},
                {"id": "b", "name": "B", "children": [{"id": "c", "name": "C"}]},
            ]
        }
        has_cycle, path = svc._check_circular_reference(structure)
        assert has_cycle is False

    def test_circular_reference(self):
        svc = self._make_service()
        structure = {
            "children": [
                {
                    "id": "a",
                    "name": "A",
                    "children": [
                        {
                            "id": "b",
                            "name": "B",
                            "children": [
                                {"id": "a", "name": "A"},
                            ],
                        },
                    ],
                },
            ]
        }
        has_cycle, path = svc._check_circular_reference(structure)
        assert has_cycle is True
        assert "A" in path

    def test_children_not_list(self):
        svc = self._make_service()
        assert svc._check_circular_reference({"children": "not a list"}) == (False, "")

    def test_child_not_dict(self):
        svc = self._make_service()
        assert svc._check_circular_reference({"children": ["string"]}) == (False, "")


class TestFolderTemplateServiceCheckInvalidChars:
    def _make_service(self):
        from apps.documents.services.template.folder_service import FolderTemplateService

        svc = FolderTemplateService.__new__(FolderTemplateService)
        svc.usecases = MagicMock()
        return svc

    def test_no_children(self):
        svc = self._make_service()
        assert svc._check_invalid_chars({}) == (False, "")

    def test_invalid_chars_found(self):
        svc = self._make_service()
        structure = {"children": [{"name": "test/file"}]}
        has_invalid, info = svc._check_invalid_chars(structure)
        assert has_invalid is True
        assert "test/file" in info

    def test_valid_name(self):
        svc = self._make_service()
        structure = {"children": [{"name": "正常文件名"}]}
        has_invalid, _ = svc._check_invalid_chars(structure)
        assert has_invalid is False

    def test_children_not_list(self):
        svc = self._make_service()
        assert svc._check_invalid_chars({"children": "not a list"}) == (False, "")

    def test_child_not_dict(self):
        svc = self._make_service()
        assert svc._check_invalid_chars({"children": ["string"]}) == (False, "")

    def test_nested_invalid(self):
        svc = self._make_service()
        structure = {
            "children": [
                {
                    "name": "parent",
                    "children": [{"name": "child/name"}],
                }
            ]
        }
        has_invalid, info = svc._check_invalid_chars(structure)
        assert has_invalid is True


class TestFolderTemplateServiceDelegation:
    def _make_service(self):
        from apps.documents.services.template.folder_service import FolderTemplateService

        svc = FolderTemplateService.__new__(FolderTemplateService)
        svc.usecases = MagicMock()
        return svc

    def test_validate_and_fix_structure_ids(self):
        svc = self._make_service()
        svc.usecases.validate_and_fix_structure_ids.return_value = (False, {}, [])
        result = svc.validate_and_fix_structure_ids({})
        assert result == (False, {}, [])

    def test_validate_structure_ids(self):
        svc = self._make_service()
        svc.usecases.validate_structure_ids.return_value = (True, [])
        result = svc.validate_structure_ids({})
        assert result == (True, [])

    def test_get_duplicate_id_report(self):
        svc = self._make_service()
        svc.usecases.get_duplicate_id_report.return_value = {}
        assert svc.get_duplicate_id_report() == {}

    def test_create_template(self):
        svc = self._make_service()
        svc.usecases.create_template.return_value = MagicMock()
        result = svc.create_template("name", "civil", "first_trial", {"children": []})
        assert result is not None

    def test_update_structure(self):
        svc = self._make_service()
        svc.usecases.update_structure.return_value = MagicMock()
        result = svc.update_structure(1, {"children": []})
        assert result is not None

    def test_get_template_for_case(self):
        svc = self._make_service()
        svc.usecases.get_template_for_case.return_value = None
        assert svc.get_template_for_case("civil", "first_trial") is None

    def test_get_template_by_id(self):
        svc = self._make_service()
        svc.usecases.get_template_by_id.return_value = MagicMock()
        result = svc.get_template_by_id(1)
        assert result is not None

    def test_validate_structure(self):
        svc = self._make_service()
        svc.usecases.validate_structure.return_value = (True, "")
        assert svc.validate_structure({}) == (True, "")

    def test_list_templates(self):
        svc = self._make_service()
        svc.usecases.list_templates.return_value = []
        assert svc.list_templates() == []

    def test_delete_template(self):
        svc = self._make_service()
        svc.usecases.delete_template.return_value = True
        assert svc.delete_template(1) is True

    def test_create_template_from_dict(self):
        svc = self._make_service()
        svc.usecases.create_template_from_dict.return_value = MagicMock()
        result = svc.create_template_from_dict({"name": "Test"})
        assert result is not None

    def test_update_template_from_dict(self):
        svc = self._make_service()
        svc.usecases.update_template_from_dict.return_value = MagicMock()
        result = svc.update_template_from_dict(1, {"name": "Updated"})
        assert result is not None
