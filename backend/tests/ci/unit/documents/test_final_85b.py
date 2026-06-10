"""Coverage boost tests for documents module — placeholders, generation, pdf merge, evidence."""

from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


# ============================================================================
# enforcement_basic_service.py — Enforcement placeholder services
# ============================================================================


class TestEnforcementCaseNumberService:
    def test_generate_returns_empty_when_no_case_id(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementCaseNumberService,
        )

        svc = EnforcementCaseNumberService.__new__(EnforcementCaseNumberService)
        svc.case_details_accessor = Mock()
        result = svc.generate({})
        assert result == {}

    def test_generate_returns_empty_when_case_id_none(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementCaseNumberService,
        )

        svc = EnforcementCaseNumberService.__new__(EnforcementCaseNumberService)
        svc.case_details_accessor = Mock()
        result = svc.generate({"case_id": None, "case": None})
        assert result == {}

    def test_get_case_number_active(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementCaseNumberService,
        )

        svc = EnforcementCaseNumberService.__new__(EnforcementCaseNumberService)
        svc.case_details_accessor = Mock()
        svc.case_details_accessor.require_case_details.return_value = {
            "case_numbers": [
                {"number": "(2025)粤0605民初123号", "is_active": False, "document_name": None},
                {"number": "(2025)粤0605民初456号", "is_active": True, "document_name": "民事调解书"},
            ]
        }
        result = svc.get_case_number(1)
        assert "456号" in result
        assert "民事调解书" in result

    def test_get_case_number_first_when_no_active(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementCaseNumberService,
        )

        svc = EnforcementCaseNumberService.__new__(EnforcementCaseNumberService)
        svc.case_details_accessor = Mock()
        svc.case_details_accessor.require_case_details.return_value = {
            "case_numbers": [
                {"number": "(2025)粤0605民初789号", "is_active": False, "document_name": None},
            ]
        }
        result = svc.get_case_number(1)
        assert result == "(2025)粤0605民初789号"

    def test_get_case_number_empty_when_no_numbers(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementCaseNumberService,
        )

        svc = EnforcementCaseNumberService.__new__(EnforcementCaseNumberService)
        svc.case_details_accessor = Mock()
        svc.case_details_accessor.require_case_details.return_value = {"case_numbers": []}
        result = svc.get_case_number(1)
        assert result == ""

    def test_get_case_number_with_document_name_has_brackets(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementCaseNumberService,
        )

        svc = EnforcementCaseNumberService.__new__(EnforcementCaseNumberService)
        svc.case_details_accessor = Mock()
        svc.case_details_accessor.require_case_details.return_value = {
            "case_numbers": [
                {"number": "(2025)粤0605民初100号", "is_active": True, "document_name": "《民事判决书》"},
            ]
        }
        result = svc.get_case_number(1)
        assert "《民事判决书》" in result
        # Should not double-wrap
        assert "《《" not in result


class TestEnforcementCourtService:
    def test_generate_returns_empty_when_no_case_id(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementCourtService,
        )

        svc = EnforcementCourtService.__new__(EnforcementCourtService)
        svc.case_details_accessor = Mock()
        result = svc.generate({})
        assert result == {}

    def test_get_court_returns_name(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementCourtService,
        )

        svc = EnforcementCourtService.__new__(EnforcementCourtService)
        svc.case_details_accessor = Mock()
        svc.case_details_accessor.require_case_details.return_value = {
            "supervising_authorities": [{"name": "佛山市中级人民法院"}]
        }
        result = svc.get_court(1)
        assert result == "佛山市中级人民法院"

    def test_get_court_returns_empty_when_no_authorities(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementCourtService,
        )

        svc = EnforcementCourtService.__new__(EnforcementCourtService)
        svc.case_details_accessor = Mock()
        svc.case_details_accessor.require_case_details.return_value = {
            "supervising_authorities": []
        }
        result = svc.get_court(1)
        assert result == ""


class TestEnforcementEffectiveDateService:
    def test_generate_returns_empty_when_no_case_id(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementEffectiveDateService,
        )

        svc = EnforcementEffectiveDateService.__new__(EnforcementEffectiveDateService)
        svc.case_details_accessor = Mock()
        result = svc.generate({})
        assert result == {}

    def test_get_effective_date_with_date(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementEffectiveDateService,
        )

        svc = EnforcementEffectiveDateService.__new__(EnforcementEffectiveDateService)
        svc.case_details_accessor = Mock()
        svc.case_details_accessor.require_case_details.return_value = {"effective_date": "2025-06-15"}
        svc.case_details_accessor._coerce_date.return_value = date(2025, 6, 15)
        result = svc.get_effective_date(1)
        assert "2025" in result
        assert "06" in result
        assert "15" in result

    def test_get_effective_date_empty_when_none(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementEffectiveDateService,
        )

        svc = EnforcementEffectiveDateService.__new__(EnforcementEffectiveDateService)
        svc.case_details_accessor = Mock()
        svc.case_details_accessor.require_case_details.return_value = {"effective_date": None}
        svc.case_details_accessor._coerce_date.return_value = None
        result = svc.get_effective_date(1)
        assert result == ""


class TestEnforcementTargetAmountService:
    def test_generate_returns_empty_when_no_case_id(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementTargetAmountService,
        )

        svc = EnforcementTargetAmountService.__new__(EnforcementTargetAmountService)
        svc.case_details_accessor = Mock()
        result = svc.generate({})
        assert result == {}

    def test_get_target_amount_with_value(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementTargetAmountService,
        )

        svc = EnforcementTargetAmountService.__new__(EnforcementTargetAmountService)
        svc.case_details_accessor = Mock()
        svc.case_details_accessor.require_case_details.return_value = {"target_amount": 100000.50}
        result = svc.get_target_amount(1)
        assert "100000.50" in result
        assert "元" in result

    def test_get_target_amount_empty_when_none(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementTargetAmountService,
        )

        svc = EnforcementTargetAmountService.__new__(EnforcementTargetAmountService)
        svc.case_details_accessor = Mock()
        svc.case_details_accessor.require_case_details.return_value = {"target_amount": None}
        result = svc.get_target_amount(1)
        assert result == ""


class TestEnforcementCauseOfActionService:
    def test_generate_returns_default_when_empty(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementCauseOfActionService,
        )

        svc = EnforcementCauseOfActionService()
        result = svc.generate({})
        assert result == {"案由": "民事纠纷"}

    def test_resolve_cause_from_case(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementCauseOfActionService,
        )

        svc = EnforcementCauseOfActionService()
        case = SimpleNamespace(cause_of_action="合同纠纷")
        result = svc._resolve_cause_of_action({"case": case})
        assert result == "合同纠纷"

    def test_resolve_cause_from_case_dto(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementCauseOfActionService,
        )

        svc = EnforcementCauseOfActionService()
        case_dto = SimpleNamespace(cause_of_action="侵权纠纷")
        result = svc._resolve_cause_of_action({"case_dto": case_dto})
        assert result == "侵权纠纷"

    def test_resolve_cause_returns_empty(self):
        from apps.documents.services.placeholders.litigation.enforcement_basic_service import (
            EnforcementCauseOfActionService,
        )

        svc = EnforcementCauseOfActionService()
        result = svc._resolve_cause_of_action({})
        assert result == ""


# ============================================================================
# preservation_property_clue_service.py
# ============================================================================


class TestPreservationPropertyClueService:
    def test_generate_returns_empty_when_no_case_id(self):
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )

        svc = PreservationPropertyClueService()
        result = svc.generate({})
        assert result == {"财产保全申请书财产线索": ""}

    def test_get_chinese_number_in_range(self):
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )

        svc = PreservationPropertyClueService()
        assert svc._get_chinese_number(0) == "一"
        assert svc._get_chinese_number(1) == "二"
        assert svc._get_chinese_number(9) == "十"

    def test_get_chinese_number_out_of_range(self):
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )

        svc = PreservationPropertyClueService()
        assert svc._get_chinese_number(20) == "21"

    def test_parse_clue_content_empty(self):
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )

        svc = PreservationPropertyClueService()
        assert svc._parse_clue_content("bank", "") == []

    def test_parse_clue_content_with_lines(self):
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )

        svc = PreservationPropertyClueService()
        result = svc._parse_clue_content("bank", "开户行: 中国银行\n账号: 123456")
        assert len(result) == 2
        assert "开户行" in result[0]

    def test_parse_clue_content_with_colon(self):
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )

        svc = PreservationPropertyClueService()
        result = svc._parse_clue_content("bank", "户名: 张三")
        assert len(result) == 1

    def test_generate_property_clue_info_no_respondents(self):
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )

        svc = PreservationPropertyClueService()
        with patch("apps.documents.services.infrastructure.wiring.get_case_service") as mock_cs:
            with patch("apps.documents.services.infrastructure.wiring.get_client_service") as mock_cls:
                mock_cs.return_value.get_case_parties_internal.return_value = []
                result = svc.generate_property_clue_info(1)
                assert result == ""


# ============================================================================
# pdf_merge_service.py — PDFMergeValidator
# ============================================================================


class TestPDFMergeValidator:
    def test_assert_supported_format_valid(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator

        validator = PDFMergeValidator()
        validator.assert_supported_format(".pdf", "/path/file.pdf")  # no exception

    def test_assert_supported_format_invalid(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator

        validator = PDFMergeValidator()
        with pytest.raises(Exception):
            validator.assert_supported_format(".exe", "/path/file.exe")

    def test_get_items_raises_when_empty(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator

        validator = PDFMergeValidator()
        mock_list = Mock()
        mock_list.pk = 1
        mock_list.items.filter.return_value.exclude.return_value.order_by.return_value.exists.return_value = False
        with pytest.raises(ValidationException):
            validator.get_items(mock_list)


class TestPDFMergeWorkflow:
    def test_validator_lazy(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeWorkflow

        wf = PDFMergeWorkflow()
        assert wf._validator is None
        v = wf.validator
        assert wf._validator is not None

    def test_generate_merged_filename_with_evidence_prefix(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeWorkflow

        wf = PDFMergeWorkflow()
        mock_list = Mock()
        mock_list.case.name = "张某诉李某"
        mock_list.title = "证据清单（一）"
        mock_list.export_version = 1
        with patch("apps.documents.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20250609"
            result = wf._generate_merged_filename(mock_list)
            assert "张某诉李某" in result
            assert "（一）" in result

    def test_generate_merged_filename_with_supplement(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeWorkflow

        wf = PDFMergeWorkflow()
        mock_list = Mock()
        mock_list.case.name = "Test"
        mock_list.title = "补充证据清单"
        mock_list.export_version = 2
        with patch("apps.documents.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20250609"
            result = wf._generate_merged_filename(mock_list)
            assert "Test" in result

    def test_generate_merged_filename_other_title(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeWorkflow

        wf = PDFMergeWorkflow()
        mock_list = Mock()
        mock_list.case.name = "Test"
        mock_list.title = "其他标题"
        mock_list.export_version = 3
        with patch("apps.documents.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20250609"
            result = wf._generate_merged_filename(mock_list)
            assert "Test" in result


class TestPDFMergeService:
    def test_workflow_lazy(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService

        svc = PDFMergeService()
        assert svc._workflow is None
        w = svc.workflow
        assert svc._workflow is not None

    def test_convert_to_pdf_delegates(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService

        svc = PDFMergeService()
        svc._workflow = Mock()
        svc._workflow.convert_to_pdf.return_value = "/tmp/output.pdf"
        result = svc.convert_to_pdf("/tmp/input.docx")
        assert result == "/tmp/output.pdf"

    def test_add_page_numbers_delegates(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService

        svc = PDFMergeService()
        svc._workflow = Mock()
        svc._workflow.add_page_numbers.return_value = b"pdf_bytes"
        result = svc.add_page_numbers(io.BytesIO(b"input"))
        assert result == b"pdf_bytes"

    def test_get_pdf_page_count_delegates(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService

        svc = PDFMergeService()
        svc._workflow = Mock()
        svc._workflow.get_pdf_page_count.return_value = 5
        result = svc.get_pdf_page_count(io.BytesIO(b"pdf"))
        assert result == 5


# ============================================================================
# case_detail_service.py — CaseDetailService
# ============================================================================


class TestCaseDetailServiceFormatCaseNumber:
    def test_format_case_number(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService

        svc = CaseDetailService()
        assert "案件一" in svc._format_case_number(1)
        assert "案件二" in svc._format_case_number(2)
        assert "案件三" in svc._format_case_number(3)
        assert "案件十" in svc._format_case_number(10)

    def test_format_case_number_out_of_range(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService

        svc = CaseDetailService()
        assert "11" in svc._format_case_number(11)


class TestCaseDetailServiceExtractCauseOfAction:
    def test_with_dash(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService

        svc = CaseDetailService()
        case = SimpleNamespace(cause_of_action="合同纠纷-买卖合同")
        result = svc._extract_cause_of_action(case)
        assert result == "合同纠纷"

    def test_without_dash(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService

        svc = CaseDetailService()
        case = SimpleNamespace(cause_of_action="侵权纠纷")
        result = svc._extract_cause_of_action(case)
        assert result == "侵权纠纷"

    def test_empty(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService

        svc = CaseDetailService()
        case = SimpleNamespace(cause_of_action=None)
        result = svc._extract_cause_of_action(case)
        assert result == ""


class TestCaseDetailServiceExtractSupervisingAuthority:
    def test_returns_trial_authority(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService
        from apps.core.models.enums import AuthorityType

        svc = CaseDetailService()
        authority = Mock()
        authority.authority_type = AuthorityType.TRIAL
        authority.name = "佛山市中级人民法院"
        case = Mock()
        case.supervising_authorities.all.return_value = [authority]
        result = svc._extract_supervising_authority(case)
        assert result == "佛山市中级人民法院"

    def test_returns_empty_when_no_trial(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService

        svc = CaseDetailService()
        case = Mock()
        case.supervising_authorities.all.return_value = []
        result = svc._extract_supervising_authority(case)
        assert result == ""


class TestCaseDetailServiceFormatTargetAmount:
    def test_with_amount(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService

        svc = CaseDetailService()
        case = SimpleNamespace(target_amount=Decimal("100000.50"))
        result = svc._format_target_amount(case)
        assert "100000.50" in result
        assert "元" in result

    def test_none_amount(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService

        svc = CaseDetailService()
        case = SimpleNamespace(target_amount=None)
        result = svc._format_target_amount(case)
        assert result == ""


class TestCaseDetailServiceFormatWithoutCases:
    def test_format_without_cases(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService

        svc = CaseDetailService()
        client = Mock()
        client.name = "张三"
        client.is_our_client = False
        cp = Mock()
        cp.role = "OPPOSING"
        cp.client = client
        contract = Mock()
        contract.contract_parties.all.return_value = [cp]
        result = svc._format_without_cases(contract)
        assert "张三" in result
        assert "对方当事人名称" in result


class TestCaseDetailServiceFormatWithCases:
    def test_format_with_empty_cases(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService

        svc = CaseDetailService()
        result = svc._format_with_cases([])
        assert result == ""


class TestCaseDetailServiceExtractOpposingParties:
    def test_extracts_opposing(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService

        svc = CaseDetailService()
        client = Mock()
        client.is_our_client = False
        client.name = "李四"
        party = Mock()
        party.client = client
        case = Mock()
        case.parties.all.return_value = [party]
        result = svc._extract_opposing_parties_from_case(case)
        assert "李四" in result

    def test_excludes_our_client(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService

        svc = CaseDetailService()
        client = Mock()
        client.is_our_client = True
        client.name = "我方"
        party = Mock()
        party.client = client
        case = Mock()
        case.parties.all.return_value = [party]
        result = svc._extract_opposing_parties_from_case(case)
        assert len(result) == 0


# ============================================================================
# preservation_materials_generation_service.py
# ============================================================================


class TestPreservationMaterialsGenerationService:
    def test_properties_lazy(self):
        from apps.documents.services.generation.preservation_materials_generation_service import (
            PreservationMaterialsGenerationService,
        )

        svc = PreservationMaterialsGenerationService()
        assert svc._party_service is None
        with patch(
            "apps.documents.services.placeholders.litigation.PreservationPartyService"
        ) as MockPS:
            _ = svc.party_service
            assert svc._party_service is not None

    def test_signature_service_lazy(self):
        from apps.documents.services.generation.preservation_materials_generation_service import (
            PreservationMaterialsGenerationService,
        )

        svc = PreservationMaterialsGenerationService()
        assert svc._signature_service is None
        with patch(
            "apps.documents.services.placeholders.litigation.PreservationSignatureService"
        ) as MockSS:
            _ = svc.signature_service
            assert svc._signature_service is not None

    def test_property_clue_service_lazy(self):
        from apps.documents.services.generation.preservation_materials_generation_service import (
            PreservationMaterialsGenerationService,
        )

        svc = PreservationMaterialsGenerationService()
        assert svc._property_clue_service is None
        with patch(
            "apps.documents.services.placeholders.litigation.PreservationPropertyClueService"
        ) as MockPCS:
            _ = svc.property_clue_service
            assert svc._property_clue_service is not None

    def test_get_missing_clues_report_none_when_all_have_clues(self):
        from apps.documents.services.generation.preservation_materials_generation_service import (
            PreservationMaterialsGenerationService,
        )

        svc = PreservationMaterialsGenerationService()
        svc._property_clue_service = Mock()
        svc._property_clue_service.get_respondents_without_clues.return_value = []
        result = svc.get_missing_clues_report(1)
        assert result is None

    def test_get_missing_clues_report_generates_report(self):
        from apps.documents.services.generation.preservation_materials_generation_service import (
            PreservationMaterialsGenerationService,
        )

        svc = PreservationMaterialsGenerationService()
        svc._property_clue_service = Mock()
        svc._property_clue_service.get_respondents_without_clues.return_value = ["张三", "李四"]
        result = svc.get_missing_clues_report(1)
        assert "张三" in result
        assert "李四" in result

    def test_generate_missing_clues_report(self):
        from apps.documents.services.generation.preservation_materials_generation_service import (
            PreservationMaterialsGenerationService,
        )

        svc = PreservationMaterialsGenerationService()
        result = svc._generate_missing_clues_report(["A", "B", "C"])
        assert "1. A" in result
        assert "2. B" in result
        assert "3. C" in result

    def test_build_filename(self):
        from apps.documents.services.generation.preservation_materials_generation_service import (
            PreservationMaterialsGenerationService,
        )

        svc = PreservationMaterialsGenerationService()
        case = SimpleNamespace(name="张某诉李某")
        with patch(
            "apps.documents.services.generation.preservation_materials_generation_service.timezone"
        ) as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20250609"
            with patch(
                "apps.documents.services.generation.preservation_materials_generation_service.FilenameTemplateService"
            ) as mock_fts:
                mock_fts.render_generated_doc.return_value = "财产保全申请书(张某诉李某)V1_20250609"
                result = svc._build_filename("财产保全申请书", case)
                assert result.endswith(".docx")


# ============================================================================
# litigation_generation_service.py — LitigationGenerationService
# ============================================================================


class TestLitigationGenerationService:
    def test_properties_lazy(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

        svc = LitigationGenerationService()
        assert svc._llm_generator is None
        with patch(
            "apps.documents.services.generation.litigation_generation_service.LitigationLLMGenerator"
        ):
            _ = svc.llm_generator
            assert svc._llm_generator is not None

    def test_context_builder_lazy(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

        svc = LitigationGenerationService()
        assert svc._context_builder is None
        with patch(
            "apps.documents.services.generation.litigation_generation_service.LitigationContextBuilder"
        ):
            _ = svc.context_builder
            assert svc._context_builder is not None

    def test_generate_filename_invalid_type_raises(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

        svc = LitigationGenerationService()
        with patch(
            "apps.documents.services.placeholders.litigation.FilenameService"
        ) as MockFS:
            with pytest.raises(ValidationException):
                svc._generate_filename(1, "invalid_type")

    def test_generate_complaint_delegates(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

        svc = LitigationGenerationService()
        svc._llm_generator = Mock()
        svc._llm_generator.generate_complaint.return_value = Mock()
        result = svc.generate_complaint({"cause_of_action": "test"})
        assert result is not None

    def test_generate_defense_delegates(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

        svc = LitigationGenerationService()
        svc._llm_generator = Mock()
        svc._llm_generator.generate_defense.return_value = Mock()
        result = svc.generate_defense({"cause_of_action": "test"})
        assert result is not None

    def test_render_template_raises_when_not_found(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

        svc = LitigationGenerationService()
        mock_path = Mock()
        mock_path.exists.return_value = False
        with pytest.raises(ValidationException, match="模板文件不存在"):
            svc._render_template(mock_path, {})

    def test_get_mock_complaint_output(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

        svc = LitigationGenerationService()
        result = svc._get_mock_complaint_output({"cause_of_action": "合同纠纷", "plaintiff": "张三", "defendant": "李四"})
        assert "合同纠纷" in result.title
        assert len(result.parties) == 2
        assert result.parties[0].role == "原告"

    def test_get_mock_defense_output(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

        svc = LitigationGenerationService()
        result = svc._get_mock_defense_output({"cause_of_action": "侵权", "plaintiff": "A", "defendant": "B"})
        assert "侵权" in result.title
        assert len(result.parties) == 2

    def test_generate_complaint_document_raises_when_no_case(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

        svc = LitigationGenerationService()
        mock_cs = Mock()
        mock_cs.get_case_by_id_internal.return_value = None
        with patch(
            "apps.documents.services.generation.litigation_generation_service.ServiceLocator"
        ) as MockSL:
            MockSL.get_case_service.return_value = mock_cs
            with pytest.raises(NotFoundError):
                svc.generate_complaint_document(999)

    def test_generate_defense_document_raises_when_no_case(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

        svc = LitigationGenerationService()
        mock_cs = Mock()
        mock_cs.get_case_by_id_internal.return_value = None
        with patch(
            "apps.documents.services.generation.litigation_generation_service.ServiceLocator"
        ) as MockSL:
            MockSL.get_case_service.return_value = mock_cs
            with pytest.raises(NotFoundError):
                svc.generate_defense_document(999)
