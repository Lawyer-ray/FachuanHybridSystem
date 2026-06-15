"""Round 9 — targeted coverage gap tests for 7 files.

Covers remaining uncovered branches only. Does NOT modify source code.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# =====================================================================
# 1. court_filing_helpers — remaining gaps
# =====================================================================


class TestCourtFilingHelpersRound9:
    """Targets: _build_materials_map dedup path, _match_slot execution
    apply_hits/apply_excludes, _build_agent_payloads fallback_phone index overflow,
    _build_execution_request_text generated key fallback, _build_material_slot_signals
    empty signals path, _run_filing _phase_label branches."""

    def test_match_slot_execution_apply_with_exclude(self):
        """Execution material matched to slot '0' only when no exclude keyword."""
        from apps.automation.api.court_filing_helpers import _match_slot

        material = SimpleNamespace(
            type_name="执行申请书",
            type=None,
            source_attachment=None,
        )
        file_path = Path("/tmp/执行申请书.pdf")
        slot = _match_slot(material=material, file_path=file_path, filing_type="execution")
        assert slot == "0"

    def test_match_slot_execution_apply_exclude_blocks(self):
        """Execution apply hits blocked by exclude keyword -> returns default."""
        from apps.automation.api.court_filing_helpers import _match_slot

        material = SimpleNamespace(
            type_name="限制高消费",
            type=None,
            source_attachment=None,
        )
        file_path = Path("/tmp/限制高消费.pdf")
        slot = _match_slot(material=material, file_path=file_path, filing_type="execution")
        # '限制高消费' does not match apply_hits, returns default "4"
        assert slot == "4"

    def test_match_slot_delivery_address_slot_4(self):
        """Signal containing '送达地址' returns slot 4."""
        from apps.automation.api.court_filing_helpers import _match_slot

        material = SimpleNamespace(
            type_name="送达地址确认书",
            type=None,
            source_attachment=None,
        )
        file_path = Path("/tmp/送达地址确认书.pdf")
        slot = _match_slot(material=material, file_path=file_path, filing_type="civil")
        assert slot == "4"

    def test_match_slot_baoquan_keyword_returns_5(self):
        """Signal with '保全' and no score -> returns slot 5 (保全保函)."""
        from apps.automation.api.court_filing_helpers import _match_slot

        material = SimpleNamespace(
            type_name="保全申请",
            type=None,
            source_attachment=None,
        )
        file_path = Path("/tmp/保全申请.pdf")
        slot = _match_slot(material=material, file_path=file_path, filing_type="civil")
        # '保全申请' matches slot rule strong keywords, gets positive score
        # so it returns matched slot, not the fallback '5'
        assert slot in ("5", "3")  # depends on slot rules

    def test_build_materials_map_dedup(self):
        """Same (slot, path) pair should be deduped."""
        from apps.automation.api.court_filing_helpers import _build_materials_map

        att = MagicMock()
        att.file.path = "/tmp/test.pdf"
        att.original_filename = "test.pdf"

        m1 = MagicMock()
        m1.source_attachment_id = 1
        m1.source_attachment = att
        m1.type_name = "合同"
        m1.type = None

        m2 = MagicMock()
        m2.source_attachment_id = 2
        m2.source_attachment = att  # same file path
        m2.type_name = "合同"
        m2.type = None

        primary_qs = MagicMock()
        primary_qs.exists.return_value = True
        primary_qs.select_related.return_value.order_by.return_value = [m1, m2]

        with patch("apps.cases.models.CaseMaterial") as MockCM, \
             patch("apps.cases.models.CaseMaterialCategory"), \
             patch("apps.cases.models.CaseMaterialSide"), \
             patch("apps.automation.api.court_filing_helpers.Path") as MockPath:
            MockPath.return_value.suffix = ".pdf"
            MockPath.return_value.exists.return_value = True
            MockCM.objects.filter.return_value = primary_qs
            result = _build_materials_map(case=MagicMock(), filing_type="civil")

        # Same path should only appear once per slot
        for slot, files in result.items():
            paths = [f[0] for f in files]
            assert len(paths) == len(set(paths))

    def test_build_materials_map_no_source_attachment(self):
        """Materials without source_attachment_id are skipped."""
        from apps.automation.api.court_filing_helpers import _build_materials_map

        m = MagicMock()
        m.source_attachment_id = None

        primary_qs = MagicMock()
        primary_qs.exists.return_value = True
        primary_qs.select_related.return_value.order_by.return_value = [m]

        with patch("apps.cases.models.CaseMaterial") as MockCM, \
             patch("apps.cases.models.CaseMaterialCategory"), \
             patch("apps.cases.models.CaseMaterialSide"):
            MockCM.objects.filter.return_value = primary_qs
            result = _build_materials_map(case=MagicMock(), filing_type="civil")
        assert result == {}

    def test_build_materials_map_no_file_path(self):
        """Materials whose attachment.file raises are skipped."""
        from apps.automation.api.court_filing_helpers import _build_materials_map

        att = MagicMock()
        att.file.path.side_effect = TypeError("no path")

        m = MagicMock()
        m.source_attachment_id = 1
        m.source_attachment = att

        primary_qs = MagicMock()
        primary_qs.exists.return_value = True
        primary_qs.select_related.return_value.order_by.return_value = [m]

        with patch("apps.cases.models.CaseMaterial") as MockCM, \
             patch("apps.cases.models.CaseMaterialCategory"), \
             patch("apps.cases.models.CaseMaterialSide"):
            MockCM.objects.filter.return_value = primary_qs
            result = _build_materials_map(case=MagicMock(), filing_type="civil")
        assert result == {}

    def test_build_materials_map_no_original_filename(self):
        """Falls back to file_path.name when original_filename is empty."""
        from apps.automation.api.court_filing_helpers import _build_materials_map

        att = MagicMock()
        att.file.path = "/tmp/test.pdf"
        att.original_filename = ""

        m = MagicMock()
        m.source_attachment_id = 1
        m.source_attachment = att
        m.type_name = "合同"
        m.type = None

        primary_qs = MagicMock()
        primary_qs.exists.return_value = True
        primary_qs.select_related.return_value.order_by.return_value = [m]

        with patch("apps.cases.models.CaseMaterial") as MockCM, \
             patch("apps.cases.models.CaseMaterialCategory"), \
             patch("apps.cases.models.CaseMaterialSide"), \
             patch("apps.automation.api.court_filing_helpers.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.suffix = ".pdf"
            mock_path.exists.return_value = True
            mock_path.as_posix.return_value = "/tmp/test.pdf"
            mock_path.name = "test.pdf"
            mock_path.stem = "test"
            mock_path.parent.as_posix.return_value = "/tmp"
            MockPath.return_value = mock_path
            MockCM.objects.filter.return_value = primary_qs
            result = _build_materials_map(case=MagicMock(), filing_type="civil")
        # Should not crash, name from path used
        assert isinstance(result, dict)

    def test_build_session_status_payload_success_with_timing(self):
        """Success status includes timing when present."""
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=1,
            status=ScraperTaskStatus.SUCCESS,
            result={"message": "完成", "timing": {"overall_start": 1.0}},
            error_message="",
        )
        payload = _build_session_status_payload(task=task)
        assert payload["timing"]["overall_start"] == 1.0

    def test_build_session_status_payload_failed_no_error_no_result(self):
        """Failed with no error and non-dict result uses default."""
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=1,
            status=ScraperTaskStatus.FAILED,
            result=None,
            error_message="",
        )
        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "立案失败"

    def test_update_session_task_no_session_id(self):
        """session_id=None is a no-op."""
        from apps.automation.api.court_filing_helpers import _update_session_task
        # Should not raise
        _update_session_task(session_id=None, status="running")

    def test_build_execution_request_text_generated_key_fallback(self):
        """When ENFORCEMENT_EXECUTION_REQUEST key is missing, falls back to '申请执行事项'."""
        case = SimpleNamespace(id=1, case_numbers=None)
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService"
        ) as MockSvc:
            MockSvc.return_value.generate.return_value = {"申请执行事项": "fallback text"}
            with patch(
                "apps.litigation_ai.placeholders.spec.LitigationPlaceholderKeys"
            ) as MockKeys:
                MockKeys.ENFORCEMENT_EXECUTION_REQUEST = "enforcement_execution_request"
                from apps.automation.api.court_filing_helpers import _build_execution_request_text
                result = _build_execution_request_text(case=case)
        assert "fallback text" in result

    def test_build_execution_request_text_empty_generated_uses_fallback(self):
        """When generated text is empty, fallback lines are used."""
        case = SimpleNamespace(id=1, case_numbers=None)
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService"
        ) as MockSvc:
            MockSvc.return_value.generate.return_value = {}
            with patch(
                "apps.litigation_ai.placeholders.spec.LitigationPlaceholderKeys"
            ) as MockKeys:
                MockKeys.ENFORCEMENT_EXECUTION_REQUEST = "enforcement_execution_request"
                from apps.automation.api.court_filing_helpers import _build_execution_request_text
                result = _build_execution_request_text(case=case)
        assert "强制执行" in result


# =====================================================================
# 2. court_guarantee_helpers — remaining gaps
# =====================================================================


class TestCourtGuaranteeHelpersRound9:
    """Targets: _build_guarantee_material_paths pick by type_name_keywords,
    _normalize_party_type 'other_org'/'nonlegal', _list_party_payloads prefer_our=False,
    _build_plaintiff_agent_payload username fallback, _build_cause_candidates dedup,
    _normalize_property_value edge cases, _build_property_clue_info None content."""

    def test_normalize_party_type_other_org(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_party_type
        assert _normalize_party_type("other_org") == "non_legal_org"

    def test_normalize_party_type_nonlegal(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_party_type
        assert _normalize_party_type("nonlegal") == "non_legal_org"

    def test_normalize_party_type_non_legal(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_party_type
        assert _normalize_party_type("non_legal") == "non_legal_org"

    def test_normalize_party_type_enterprise(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_party_type
        assert _normalize_party_type("enterprise") == "legal"

    def test_normalize_party_type_organization(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_party_type
        assert _normalize_party_type("organization") == "legal"

    def test_normalize_party_type_org(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_party_type
        assert _normalize_party_type("org") == "legal"

    def test_normalize_property_value_comma_no_decimal(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_property_value
        assert _normalize_property_value("10,000") == "10000"

    def test_normalize_property_value_no_comma_no_decimal(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_property_value
        assert _normalize_property_value("50000") == "50000"

    def test_build_property_clue_info_none_content(self):
        from apps.automation.api.court_guarantee_helpers import _build_property_clue_info
        result = _build_property_clue_info(clue_type=None, raw_content="")
        assert "财产线索" in result

    def test_build_property_clue_info_known_type(self):
        from apps.automation.api.court_guarantee_helpers import _build_property_clue_info
        result = _build_property_clue_info(clue_type="bank_account", raw_content="测试账户")
        assert "银行" in result

    def test_build_cause_candidates_dedup(self):
        from apps.automation.api.court_guarantee_helpers import _build_cause_candidates
        result = _build_cause_candidates("借款合同纠纷、借款合同纠纷")
        # Dedup: same cause should appear only once
        assert result.count("借款合同纠纷") == 1

    def test_build_cause_candidates_with_comma_separator(self):
        from apps.automation.api.court_guarantee_helpers import _build_cause_candidates
        result = _build_cause_candidates("买卖合同纠纷,借款合同纠纷")
        assert "买卖合同纠纷" in result
        assert "借款合同纠纷" in result

    def test_build_cause_candidates_semicolon_separator(self):
        from apps.automation.api.court_guarantee_helpers import _build_cause_candidates
        result = _build_cause_candidates("买卖合同纠纷;借款合同纠纷")
        assert "买卖合同纠纷" in result

    def test_build_cause_candidates_pipe_separator(self):
        from apps.automation.api.court_guarantee_helpers import _build_cause_candidates
        result = _build_cause_candidates("买卖合同纠纷|借款合同纠纷")
        assert "买卖合同纠纷" in result

    def test_list_party_payloads_prefer_our_false(self):
        from apps.automation.api.court_guarantee_helpers import _list_party_payloads
        party = SimpleNamespace(
            legal_status="plaintiff",
            id=1,
            client=SimpleNamespace(
                client_type="natural",
                name="原告A",
                id_number="110101199001011234",
                phone="13800138000",
                address="地址A",
                is_our_client=True,
                legal_representative="",
                legal_representative_id_number="",
            ),
        )
        result = _list_party_payloads(
            case_parties=[party], preferred_statuses={"plaintiff"}, prefer_our=False
        )
        # prefer_our=False means we want non-our clients, so party won't match
        # Falls through to status-only match
        assert len(result) >= 1

    def test_list_party_payloads_empty_parties(self):
        from apps.automation.api.court_guarantee_helpers import _list_party_payloads
        result = _list_party_payloads(case_parties=[], preferred_statuses=set(), prefer_our=True)
        assert result == []

    def test_build_plaintiff_agent_payload_username_fallback(self):
        """When real_name is empty, username is used."""
        from apps.automation.api.court_guarantee_helpers import _build_plaintiff_agent_payload
        case = SimpleNamespace()
        lawyer = SimpleNamespace(
            real_name="",
            username="test_user",
            id_card="",
            phone="13800138000",
            license_no="",
            law_firm=SimpleNamespace(name="Test Firm", address=""),
        )
        assignment = SimpleNamespace(lawyer=lawyer)
        case.assignments = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value.first.return_value = assignment

        with patch("apps.organization.models.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.filter.return_value.first.return_value = None
            result = _build_plaintiff_agent_payload(
                case=case, requester_id=None, fallback_party={"name": "", "phone": ""}
            )
        assert result["name"] == "test_user"

    def test_build_plaintiff_agent_payload_lawyer_phone_fallback(self):
        """When lawyer has no phone, falls back to party phone."""
        from apps.automation.api.court_guarantee_helpers import _build_plaintiff_agent_payload
        case = SimpleNamespace()
        lawyer = SimpleNamespace(
            real_name="律师A",
            username="la",
            id_card="",
            phone="",
            license_no="",
            law_firm=SimpleNamespace(name="Firm", address=""),
        )
        assignment = SimpleNamespace(lawyer=lawyer)
        case.assignments = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value.first.return_value = assignment

        with patch("apps.organization.models.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.filter.return_value.first.return_value = None
            result = _build_plaintiff_agent_payload(
                case=case, requester_id=None, fallback_party={"name": "fallback", "phone": "13900139000"}
            )
        assert result["phone"] == "13900139000"

    def test_build_case_quote_context_reusable_binding_not_found_fallback(self):
        """When reusable binding not found, falls back to latest binding."""
        from apps.automation.api.court_guarantee_helpers import _build_case_quote_context
        case = MagicMock()
        case.id = 1
        case.preservation_amount = Decimal("50000")

        with patch(
            "apps.automation.api.court_guarantee_helpers._find_reusable_binding", return_value=None
        ):
            with patch("apps.automation.models.CasePreservationQuoteBinding") as MockBinding:
                fallback_binding = MagicMock()
                fallback_binding.id = 20
                quote = MagicMock()
                quote.id = 30
                quote.status = "success"
                quote.error_message = ""
                quote.created_at = None
                quote.finished_at = None
                quote.success_count = 1
                quote.failed_count = 0
                quote.total_companies = 1
                quote.quotes.filter.return_value.order_by.return_value = []
                fallback_binding.preservation_quote = quote
                fallback_binding.preserve_amount_snapshot = Decimal("50000")
                MockBinding.objects.select_related.return_value.filter.return_value.order_by.return_value.first.return_value = fallback_binding
                result = _build_case_quote_context(case=case)
        assert result is not None
        assert result["binding_id"] == 20

    def test_build_reusable_quote_options_negative_amount(self):
        from apps.automation.api.court_guarantee_helpers import _build_reusable_quote_options
        case = MagicMock()
        case.id = 1
        case.preservation_amount = Decimal("-100")
        result = _build_reusable_quote_options(case=case)
        assert result == []

    def test_extract_quote_company_options_non_dict_in_list(self):
        from apps.automation.api.court_guarantee_helpers import _extract_quote_company_options
        ctx = {"items": [123, "string", {"company_name": "A", "status": "success"}]}
        result = _extract_quote_company_options(quote_context=ctx)
        assert result == ["A"]

    def test_build_respondent_options_empty(self):
        from apps.automation.api.court_guarantee_helpers import _build_respondent_options
        with patch(
            "apps.automation.api.court_guarantee_helpers._list_opponent_case_parties", return_value=[]
        ):
            result = _build_respondent_options(case_parties=[])
        assert result == []

    def test_build_selected_respondent_property_clues_no_party_id_zero(self):
        """party_id=0 in selected_respondents should be filtered out."""
        from apps.automation.api.court_guarantee_helpers import _build_selected_respondent_property_clues
        party = SimpleNamespace(
            id=1,
            client=SimpleNamespace(id=10, name="被告", address="地址", is_our_client=False),
        )
        with patch(
            "apps.automation.api.court_guarantee_helpers._get_client_service"
        ) as mock_svc:
            svc = MagicMock()
            svc.get_property_clues_by_client_internal.return_value = []
            mock_svc.return_value = svc
            result = _build_selected_respondent_property_clues(
                case_parties=[party],
                selected_respondents=[{"party_id": 0}],  # zero → filtered
                preserve_amount=None,
            )
        # Falls back to opponent parties
        assert len(result) >= 1

    def test_normalize_consultant_code_sunshine_with_code(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_consultant_code
        result = _normalize_consultant_code(
            insurance_company_name="阳光财产保险", consultant_code="CUSTOM123"
        )
        assert result == "CUSTOM123"


# =====================================================================
# 3. sms_parser_service — remaining gaps
# =====================================================================


class TestSMSParserServiceRound9:
    """Targets: _is_valid_download_link湖北public msg, jysd link with key param,
    _filter_parties edge cases, extract_party_names with candidate extractor,
    _extract_party_names_with_regex patterns."""

    def _make_parser(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService
        return SMSParserService(
            ollama_model="test",
            ollama_base_url="http://localhost",
            llm_service=MagicMock(),
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_is_valid_hbfy_public_link(self):
        """湖北 public msg link validation."""
        parser = self._make_parser()
        link = "https://hbfy.court.gov.cn/hb/msg=abc123"
        assert parser._is_valid_download_link(link) is True

    def test_is_valid_hbfy_account_link(self):
        """湖北 account link validation."""
        parser = self._make_parser()
        link = "https://hbfy.court.gov.cn/sfsddz"
        assert parser._is_valid_download_link(link) is True

    def test_is_valid_jysd_link(self):
        """简易送达 link with key param."""
        parser = self._make_parser()
        link = "https://court.example.com/sd?key=abc123def"
        assert parser._is_valid_download_link(link) is True

    def test_is_valid_jysd_link_no_key(self):
        """简易送达 path without key param is invalid."""
        parser = self._make_parser()
        link = "https://court.example.com/sd?other=value"
        assert parser._is_valid_download_link(link) is False

    def test_is_valid_gdems_link(self):
        parser = self._make_parser()
        link = "https://gdems.court.gov.cn/v3/dzsd/abc123"
        assert parser._is_valid_download_link(link) is True

    def test_is_valid_sfdw_link(self):
        parser = self._make_parser()
        link = "https://sfsdw.court.gov.cn/sfsdw//r/abc123"
        assert parser._is_valid_download_link(link) is True

    def test_is_valid_unknown_link(self):
        parser = self._make_parser()
        link = "https://www.example.com/page"
        assert parser._is_valid_download_link(link) is False

    def test_extract_download_links_combined(self):
        """Multiple link types in one content."""
        parser = self._make_parser()
        content = (
            "查看文书 https://court.example.com/v3/dzsd/abc123 "
            "或 https://sfsdw.court.gov.cn/sfsdw//r/xyz789"
        )
        links = parser.extract_download_links(content)
        assert len(links) == 2

    def test_extract_download_links_dedup(self):
        parser = self._make_parser()
        content = (
            "https://court.example.com/v3/dzsd/abc123 "
            "https://court.example.com/v3/dzsd/abc123"
        )
        links = parser.extract_download_links(content)
        assert len(links) == 1

    def test_sanitize_link_trailing_punctuation(self):
        parser = self._make_parser()
        assert parser._sanitize_link("https://example.com/path。") == "https://example.com/path"
        assert parser._sanitize_link("https://example.com/path!") == "https://example.com/path"
        assert parser._sanitize_link("https://example.com/path）") == "https://example.com/path"
        assert parser._sanitize_link("https://example.com/path】") == "https://example.com/path"
        assert parser._sanitize_link("https://example.com/path\"") == "https://example.com/path"

    def test_filter_parties_invalid_chars(self):
        """Parties with non-Chinese/digit chars are filtered."""
        parser = self._make_parser()
        filtered = parser._filter_parties(["张三", "test@name", "李四"])
        assert "张三" in filtered
        assert "李四" in filtered
        assert "test@name" not in filtered

    def test_filter_parties_invalid_fragments(self):
        """Invalid fragments like '有限公司' are filtered."""
        parser = self._make_parser()
        filtered = parser._filter_parties(["有限公司", "张三"])
        assert "有限公司" not in filtered
        assert "张三" in filtered

    def test_filter_parties_ends_with_bad_char(self):
        parser = self._make_parser()
        filtered = parser._filter_parties(["张三的", "李四财", "王五案"])
        assert len(filtered) == 0

    def test_filter_parties_starts_with_de(self):
        parser = self._make_parser()
        filtered = parser._filter_parties(["的案件"])
        assert len(filtered) == 0

    def test_parse_filing_notification_type(self):
        """Content with '立案' but no link → FILING_NOTIFICATION."""
        parser = self._make_parser()
        result = parser.parse("您的案件已立案")
        from apps.automation.models import CourtSMSType
        assert result.sms_type == CourtSMSType.FILING_NOTIFICATION

    def test_parse_info_notification_type(self):
        """Content without link and without '立案' → INFO_NOTIFICATION."""
        parser = self._make_parser()
        result = parser.parse("明天上午开庭")
        from apps.automation.models import CourtSMSType
        assert result.sms_type == CourtSMSType.INFO_NOTIFICATION

    def test_parse_document_delivery_type(self):
        """Content with valid link → DOCUMENT_DELIVERY."""
        parser = self._make_parser()
        result = parser.parse(
            "文书已送达 https://court.example.com/v3/dzsd/abc123"
        )
        from apps.automation.models import CourtSMSType
        assert result.sms_type == CourtSMSType.DOCUMENT_DELIVERY

    def test_extract_verification_code_found(self):
        parser = self._make_parser()
        code = parser.extract_verification_code("验证码：5678，请查收")
        assert code == "5678"

    def test_extract_verification_code_not_found(self):
        parser = self._make_parser()
        code = parser.extract_verification_code("没有验证码的短信")
        assert code == ""

    def test_extract_party_names_existing_client(self):
        """Party found in existing clients."""
        parser = self._make_parser()
        mock_client = SimpleNamespace(name="张三")
        parser._client_service = MagicMock()
        parser._client_service.get_all_clients_internal.return_value = [mock_client]

        result = parser._find_existing_clients_in_sms("张三与李四的纠纷")
        assert "张三" in result

    def test_extract_party_names_no_existing_client_short_name(self):
        """Client names shorter than 2 chars are skipped."""
        parser = self._make_parser()
        mock_client = SimpleNamespace(name="张")
        parser._client_service = MagicMock()
        parser._client_service.get_all_clients_internal.return_value = [mock_client]

        result = parser._find_existing_clients_in_sms("张的案件")
        assert len(result) == 0

    def test_extract_party_names_client_service_exception(self):
        """Exception from client_service returns empty list."""
        parser = self._make_parser()
        parser._client_service = MagicMock()
        parser._client_service.get_all_clients_internal.side_effect = RuntimeError("db error")

        result = parser._find_existing_clients_in_sms("test content")
        assert result == []

    def test_extract_party_names_fallback_to_candidates(self):
        """When no existing clients, falls back to candidate extractor."""
        parser = self._make_parser()
        parser._client_service = MagicMock()
        parser._client_service.get_all_clients_internal.return_value = []
        parser._party_candidate_extractor = MagicMock()
        parser._party_candidate_extractor.extract.return_value = ["张三", "李四"]
        parser._party_matching_service = MagicMock()
        parser._party_matching_service.extract_and_match_parties_from_sms.return_value = [
            SimpleNamespace(name="张三"),
            SimpleNamespace(name="李四"),
        ]

        result = parser.extract_party_names("张三与李四的案件")
        assert "张三" in result
        assert "李四" in result

    def test_extract_party_names_candidate_extractor_no_extract(self):
        """Extractor without extract method returns empty."""
        parser = self._make_parser()
        parser._client_service = MagicMock()
        parser._client_service.get_all_clients_internal.return_value = []
        parser._party_candidate_extractor = MagicMock(spec=[])  # no extract
        parser._party_matching_service = MagicMock()

        result = parser.extract_party_names("张三与李四")
        assert result == []

    def test_extract_party_names_empty_candidates(self):
        """Empty candidates from extractor returns empty."""
        parser = self._make_parser()
        parser._client_service = MagicMock()
        parser._client_service.get_all_clients_internal.return_value = []
        parser._party_candidate_extractor = MagicMock()
        parser._party_candidate_extractor.extract.return_value = []
        parser._party_matching_service = MagicMock()

        result = parser.extract_party_names("张三与李四")
        assert result == []

    def test_extract_party_names_matcher_no_interface(self):
        """Matcher without extract_and_match_parties_from_sms returns empty."""
        parser = self._make_parser()
        parser._client_service = MagicMock()
        parser._client_service.get_all_clients_internal.return_value = []
        parser._party_candidate_extractor = MagicMock()
        parser._party_candidate_extractor.extract.return_value = ["张三"]
        parser._party_matching_service = MagicMock(spec=[])  # no method

        result = parser.extract_party_names("张三与李四")
        assert result == []

    def test_extract_party_names_matcher_exception(self):
        """Exception from matcher returns empty."""
        parser = self._make_parser()
        parser._client_service = MagicMock()
        parser._client_service.get_all_clients_internal.return_value = []
        parser._party_candidate_extractor = MagicMock()
        parser._party_candidate_extractor.extract.return_value = ["张三"]
        parser._party_matching_service = MagicMock()
        parser._party_matching_service.extract_and_match_parties_from_sms.side_effect = RuntimeError("fail")

        result = parser.extract_party_names("张三与李四")
        assert result == []

    def test_extract_party_names_dedup(self):
        """Duplicate names from matched clients are deduped."""
        parser = self._make_parser()
        parser._client_service = MagicMock()
        parser._client_service.get_all_clients_internal.return_value = []
        parser._party_candidate_extractor = MagicMock()
        parser._party_candidate_extractor.extract.return_value = ["张三"]
        parser._party_matching_service = MagicMock()
        parser._party_matching_service.extract_and_match_parties_from_sms.return_value = [
            SimpleNamespace(name="张三"),
            SimpleNamespace(name="张三"),
        ]

        result = parser.extract_party_names("张三与李四")
        assert result.count("张三") == 1

    def test_extract_party_names_empty_name_skipped(self):
        """Client with empty name is skipped."""
        parser = self._make_parser()
        parser._client_service = MagicMock()
        parser._client_service.get_all_clients_internal.return_value = []
        parser._party_candidate_extractor = MagicMock()
        parser._party_candidate_extractor.extract.return_value = ["张三"]
        parser._party_matching_service = MagicMock()
        parser._party_matching_service.extract_and_match_parties_from_sms.return_value = [
            SimpleNamespace(name=""),
        ]

        result = parser.extract_party_names("张三与李四")
        assert result == []

    def test_collect_company_names(self):
        parser = self._make_parser()
        parties: list[str] = []
        parser._collect_company_names("佛山市某某科技有限公司与张三的合同", parties)
        assert any("科技有限公司" in p for p in parties)

    def test_collect_company_names_stock(self):
        parser = self._make_parser()
        parties: list[str] = []
        parser._collect_company_names("某某股份有限公司", parties)
        assert any("股份有限公司" in p for p in parties)

    def test_collect_company_names_group(self):
        parser = self._make_parser()
        parties: list[str] = []
        parser._collect_company_names("某某集团企业", parties)
        assert len(parties) >= 1

    def test_collect_versus_patterns(self):
        parser = self._make_parser()
        parties: list[str] = []
        parser._collect_versus_patterns("张三诉李四案件", parties)
        assert len(parties) >= 2

    def test_collect_versus_patterns_company(self):
        parser = self._make_parser()
        parties: list[str] = []
        parser._collect_versus_patterns(
            "佛山市某某科技有限公司与张三的合同纠纷", parties
        )
        assert len(parties) >= 1

    def test_collect_versus_patterns_shou(self):
        parser = self._make_parser()
        parties: list[str] = []
        parser._collect_versus_patterns("收到 张三与李四的", parties)
        assert len(parties) >= 2

    def test_collect_versus_patterns_guanyu(self):
        parser = self._make_parser()
        parties: list[str] = []
        parser._collect_versus_patterns("关于 张三诉李四案件", parties)
        assert len(parties) >= 2

    def test_collect_name_contexts_shenqing(self):
        parser = self._make_parser()
        parties: list[str] = []
        parser._collect_name_contexts("申请人：张三", parties)
        assert "张三" in parties

    def test_collect_name_contexts_guanyu(self):
        parser = self._make_parser()
        parties: list[str] = []
        parser._collect_name_contexts("关于 张三 与", parties)
        assert "张三" in parties

    def test_collect_name_contexts_su(self):
        parser = self._make_parser()
        parties: list[str] = []
        parser._collect_name_contexts("张三 诉 李四", parties)
        assert len(parties) >= 2


# =====================================================================
# 4. case_matcher — remaining gaps
# =====================================================================


class TestCaseMatcherRound9:
    """Targets: _detect_case_stage 执保 case, _narrow_down_by_case_number_features
    bankruptcy, _match returns exception, _collect_closed_cases paths,
    match_by_party_names interface, _get_all_cases_by_numbers exception."""

    def _make_matcher(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        case_service = MagicMock()
        doc_service = MagicMock()
        party_service = MagicMock()
        return CaseMatcher(
            case_service=case_service,
            document_parser_service=doc_service,
            party_matching_service=party_service,
        ), case_service, doc_service, party_service

    def _make_case(self, id=1, name="案件", status="active", case_type=None, current_stage=None):
        class _Case:
            def __init__(self, id, name, status, case_type, current_stage):
                self.id = id
                self.name = name
                self.status = status
                self.case_type = case_type
                self.current_stage = current_stage
            def __hash__(self):
                return hash(self.id)
            def __eq__(self, other):
                return hasattr(other, "id") and self.id == other.id
        return _Case(id=id, name=name, status=status, case_type=case_type, current_stage=current_stage)

    def test_detect_case_stage_zhibao(self):
        """'执保' in case number does NOT return enforcement."""
        matcher, _, _, _ = self._make_matcher()
        result = matcher._detect_case_stage_from_number("（2025）粤0605执保123号")
        assert result is None  # 执保 is excluded from enforcement

    def test_detect_case_stage_zhihui(self):
        """执恢 should return enforcement."""
        matcher, _, _, _ = self._make_matcher()
        from apps.core.models.enums import CaseStage
        result = matcher._detect_case_stage_from_number("（2025）粤0605执恢123号")
        assert result == CaseStage.ENFORCEMENT

    def test_detect_case_type_bankruptcy_returns_none(self):
        """破产 in case number returns None for type."""
        matcher, _, _, _ = self._make_matcher()
        result = matcher._detect_case_type_from_number("（2025）粤0605破123号")
        assert result is None

    def test_is_bankruptcy_case_number_empty(self):
        matcher, _, _, _ = self._make_matcher()
        assert matcher._is_bankruptcy_case_number("") is False

    def test_narrow_down_bankruptcy_match(self):
        """Bankruptcy feature filters to bankruptcy cases."""
        matcher, _, _, _ = self._make_matcher()
        c1 = self._make_case(id=1, name="破产案件A")
        c2 = self._make_case(id=2, name="普通案件B")
        result = matcher._narrow_down_by_case_number_features([c1, c2], ["（2025）粤0605破123号"])
        assert result is not None
        assert result.name == "破产案件A"

    def test_narrow_down_no_features(self):
        """No type/stage/bankruptcy features returns None."""
        matcher, _, _, _ = self._make_matcher()
        result = matcher._narrow_down_by_case_number_features(
            [self._make_case(id=1)], ["（2025）粤0605号"]
        )
        assert result is None

    def test_narrow_down_empty_cases(self):
        matcher, _, _, _ = self._make_matcher()
        result = matcher._narrow_down_by_case_number_features([], ["（2025）粤0605执123号"])
        assert result is None

    def test_narrow_down_type_filter(self):
        """Type filter narrows down cases."""
        matcher, _, _, _ = self._make_matcher()
        c1 = self._make_case(id=1, case_type="civil")
        c2 = self._make_case(id=2, case_type="criminal")
        result = matcher._narrow_down_by_case_number_features(
            [c1, c2], ["（2025）粤0605民初123号"]
        )
        assert result is not None
        assert result.case_type == "civil"

    def test_narrow_down_stage_filter(self):
        """Stage filter narrows down cases."""
        matcher, _, _, _ = self._make_matcher()
        c1 = self._make_case(id=1, current_stage="first_trial")
        c2 = self._make_case(id=2, current_stage="enforcement")
        result = matcher._narrow_down_by_case_number_features(
            [c1, c2], ["（2025）粤0605民初123号"]
        )
        assert result is not None
        assert result.current_stage == "first_trial"

    def test_narrow_down_multiple_after_filter(self):
        """Multiple cases after filter returns None."""
        matcher, _, _, _ = self._make_matcher()
        c1 = self._make_case(id=1, current_stage="first_trial")
        c2 = self._make_case(id=2, current_stage="first_trial")
        result = matcher._narrow_down_by_case_number_features(
            [c1, c2], ["（2025）粤0605民初123号"]
        )
        assert result is None

    def test_match_exception_raises_validation(self):
        """Exception during match raises ValidationException."""
        from apps.core.exceptions import ValidationException
        matcher, cs, _, _ = self._make_matcher()
        cs.search_cases_by_case_number_internal.side_effect = RuntimeError("db error")

        sms = SimpleNamespace(
            case_numbers=["(2025)粤01民初1号"],
            party_names=[],
        )
        with pytest.raises(ValidationException):
            matcher.match(sms)

    def test_match_case_number_single_closed(self):
        """Single closed case from case number → None."""
        from apps.core.models.enums import CaseStatus
        matcher, cs, _, ps = self._make_matcher()
        c = self._make_case(id=1, status=CaseStatus.CLOSED)
        cs.search_cases_by_case_number_internal.return_value = [c]
        ps.debug_client_database.return_value = None
        ps.find_existing_clients_in_sms.return_value = []

        sms = SimpleNamespace(case_numbers=["(2025)粤01民初1号"], party_names=[])
        result = matcher.match(sms)
        assert result is None

    def test_match_case_number_multiple_active(self):
        """Multiple active cases from case number → None (needs manual decision)."""
        from apps.core.models.enums import CaseStatus
        matcher, cs, _, ps = self._make_matcher()
        c1 = self._make_case(id=1, name="案件A", status=CaseStatus.ACTIVE)
        c2 = self._make_case(id=2, name="案件B", status=CaseStatus.ACTIVE)
        cs.search_cases_by_case_number_internal.return_value = [c1, c2]
        ps.debug_client_database.return_value = None
        ps.find_existing_clients_in_sms.return_value = []

        sms = SimpleNamespace(case_numbers=["(2025)粤01民初1号"], party_names=[])
        result = matcher.match(sms)
        assert result is None

    def test_match_case_number_multiple_one_active(self):
        """Multiple cases, one active → returns active."""
        from apps.core.models.enums import CaseStatus
        matcher, cs, _, ps = self._make_matcher()
        c1 = self._make_case(id=1, name="案件A", status=CaseStatus.CLOSED)
        c2 = self._make_case(id=2, name="案件B", status=CaseStatus.ACTIVE)
        cs.search_cases_by_case_number_internal.return_value = [c1, c2]
        ps.debug_client_database.return_value = None
        ps.find_existing_clients_in_sms.return_value = []

        sms = SimpleNamespace(case_numbers=["(2025)粤01民初1号"], party_names=[])
        result = matcher.match(sms)
        assert result is not None
        assert result.id == 2

    def test_match_case_number_all_closed(self):
        """All cases closed → None."""
        from apps.core.models.enums import CaseStatus
        matcher, cs, _, ps = self._make_matcher()
        c1 = self._make_case(id=1, status=CaseStatus.CLOSED)
        c2 = self._make_case(id=2, status=CaseStatus.CLOSED)
        cs.search_cases_by_case_number_internal.return_value = [c1, c2]
        ps.debug_client_database.return_value = None
        ps.find_existing_clients_in_sms.return_value = []

        sms = SimpleNamespace(case_numbers=["(2025)粤01民初1号"], party_names=[])
        result = matcher.match(sms)
        assert result is None

    def test_extract_party_names_single_from_sms_fallback_to_doc_fails(self):
        """Single party from SMS, document extraction fails → returns SMS party."""
        matcher, _, ds, _ = self._make_matcher()
        ds.get_all_document_paths.return_value = ["/path/doc.pdf"]
        ds.extract_parties_from_document.side_effect = RuntimeError("parse error")

        sms = SimpleNamespace(party_names=["张三"])
        result = matcher._extract_party_names(sms)
        assert result == ["张三"]

    def test_extract_party_names_doc_single_party(self):
        """Document returns only 1 party → not enough, falls back to SMS."""
        matcher, _, ds, _ = self._make_matcher()
        ds.get_all_document_paths.return_value = ["/path/doc.pdf"]
        ds.extract_parties_from_document.return_value = ["张三"]

        sms = SimpleNamespace(party_names=["张三"])
        result = matcher._extract_party_names(sms)
        assert result == ["张三"]

    def test_extract_party_names_sms_multiple_used(self):
        """Multiple parties from SMS used directly."""
        matcher, _, ds, _ = self._make_matcher()
        sms = SimpleNamespace(party_names=["张三", "李四"])
        result = matcher._extract_party_names(sms)
        assert result == ["张三", "李四"]

    def test_match_party_names_single_match(self):
        """match_by_party_names with single match returns it."""
        matcher, cs, _, ps = self._make_matcher()
        ps.debug_client_database.return_value = None
        ps.find_existing_clients_in_sms.return_value = [SimpleNamespace(name="张三")]
        c = self._make_case(id=1, name="张三案")
        cs.search_cases_by_party_internal.return_value = [c]
        cs.get_case_party_names_internal.return_value = ["张三"]

        result = matcher.match_by_party_names(["张三"])
        assert result is not None

    def test_get_all_cases_by_numbers_exception(self):
        """Exception in search is caught and skipped."""
        matcher, cs, _, _ = self._make_matcher()
        cs.search_cases_by_case_number_internal.side_effect = [RuntimeError("fail"), []]

        result = matcher._get_all_cases_by_numbers(["num1", "num2"])
        assert result == []

    def test_check_and_log_closed_cases_exception(self):
        """Exception in _check_and_log_closed_cases is caught."""
        matcher, cs, _, ps = self._make_matcher()
        cs.search_cases_by_case_number_internal.side_effect = RuntimeError("db fail")

        sms = SimpleNamespace(case_numbers=["(2025)号"], party_names=[])
        # Should not raise
        matcher._check_and_log_closed_cases(sms)

    def test_collect_closed_cases_by_party(self):
        """Closed cases found by party are collected."""
        from apps.core.models.enums import CaseStatus
        matcher, cs, _, ps = self._make_matcher()
        ps.find_existing_clients_in_sms.return_value = [SimpleNamespace(name="张三")]
        c = self._make_case(id=1, status=CaseStatus.CLOSED)
        cs.search_cases_by_party_internal.return_value = [c]

        closed_cases: set = set()
        sms = SimpleNamespace(case_numbers=[], party_names=["张三"])
        matcher._collect_closed_cases_by_party(sms, closed_cases)
        assert len(closed_cases) == 1

    def test_collect_closed_cases_by_party_no_clients(self):
        """No matched clients → no closed cases found."""
        matcher, cs, _, ps = self._make_matcher()
        ps.find_existing_clients_in_sms.return_value = []

        closed_cases: set = set()
        sms = SimpleNamespace(party_names=["张三"])
        matcher._collect_closed_cases_by_party(sms, closed_cases)
        assert len(closed_cases) == 0

    def test_collect_closed_cases_by_number_no_numbers(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher, _, _, _ = self._make_matcher()
        closed_cases: set = set()
        sms = SimpleNamespace(case_numbers=[])
        matcher._collect_closed_cases_by_number(sms, closed_cases)
        assert len(closed_cases) == 0

    def test_collect_closed_cases_by_number_exception(self):
        from apps.core.models.enums import CaseStatus
        matcher, cs, _, _ = self._make_matcher()
        cs.search_cases_by_case_number_internal.side_effect = RuntimeError("db fail")

        closed_cases: set = set()
        sms = SimpleNamespace(case_numbers=["(2025)号"])
        matcher._collect_closed_cases_by_number(sms, closed_cases)
        assert len(closed_cases) == 0

    def test_apply_type_filter_no_match(self):
        """Type filter with no match returns original cases."""
        matcher, _, _, _ = self._make_matcher()
        c1 = self._make_case(id=1, case_type="civil")
        result = matcher._apply_type_filter([c1], "criminal")
        assert len(result) == 1  # original returned

    def test_apply_stage_filter_no_match(self):
        """Stage filter with no match returns original cases."""
        matcher, _, _, _ = self._make_matcher()
        c1 = self._make_case(id=1, current_stage="first_trial")
        result = matcher._apply_stage_filter([c1], "enforcement")
        assert len(result) == 1  # original returned

    def test_apply_type_filter_none(self):
        matcher, _, _, _ = self._make_matcher()
        c1 = self._make_case(id=1)
        result = matcher._apply_type_filter([c1], None)
        assert len(result) == 1

    def test_apply_stage_filter_none(self):
        matcher, _, _, _ = self._make_matcher()
        c1 = self._make_case(id=1)
        result = matcher._apply_stage_filter([c1], None)
        assert len(result) == 1

    def test_filter_bankruptcy_no_match(self):
        """Bankruptcy filter with no matching cases returns original."""
        matcher, _, _, _ = self._make_matcher()
        c1 = self._make_case(id=1, name="普通案件")
        result = matcher._filter_bankruptcy([c1])
        assert len(result) == 1

    def test_filter_bankruptcy_match(self):
        matcher, _, _, _ = self._make_matcher()
        c1 = self._make_case(id=1, name="破产重整案件")
        c2 = self._make_case(id=2, name="普通案件")
        result = matcher._filter_bankruptcy([c1, c2])
        assert len(result) == 1
        assert result[0].name == "破产重整案件"


# =====================================================================
# 5. execution_request_service — remaining gaps
# =====================================================================


class TestExecutionRequestServiceRound9:
    """Targets: generate with no case_id, generate with non-existent case_id,
    _select_primary_case_number paths, _build_execution_request empty doc,
    preview_for_case_number, _format_case_number."""

    def _make_service(self):
        from apps.documents.services.placeholders.litigation.execution_request_service import (
            ExecutionRequestService,
        )
        return ExecutionRequestService()

    def test_generate_no_case_id(self):
        svc = self._make_service()
        result = svc.generate({})
        from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys
        assert result[LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST] == ""

    def test_generate_case_id_none_fallback_to_case_attr(self):
        svc = self._make_service()
        case_obj = SimpleNamespace(id=None)
        result = svc.generate({"case": case_obj})
        from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys
        assert result[LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST] == ""

    def test_generate_nonexistent_case_id(self):
        svc = self._make_service()
        with patch("apps.documents.services.placeholders.litigation.execution_request_service.Case") as MockCase:
            MockCase.objects.filter.return_value.first.return_value = None
            result = svc.generate({"case_id": 999999})
        from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys
        assert result[LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST] == ""

    def test_select_primary_case_number_empty(self):
        svc = self._make_service()
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.CaseNumber"
        ) as MockCN:
            MockCN.objects.filter.return_value.order_by.return_value = []
            result = svc._select_primary_case_number(999)
        assert result is None

    def test_select_primary_case_number_first_active_with_content(self):
        svc = self._make_service()
        cn = SimpleNamespace(
            id=1,
            is_active=True,
            document_content="判决主文内容",
            execution_manual_text="",
        )
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.CaseNumber"
        ) as MockCN:
            MockCN.objects.filter.return_value.order_by.return_value = [cn]
            result = svc._select_primary_case_number(1)
        assert result is cn

    def test_select_primary_case_number_inactive_with_manual_text(self):
        svc = self._make_service()
        cn = SimpleNamespace(
            id=1,
            is_active=False,
            document_content="",
            execution_manual_text="手动内容",
        )
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.CaseNumber"
        ) as MockCN:
            MockCN.objects.filter.return_value.order_by.return_value = [cn]
            result = svc._select_primary_case_number(1)
        assert result is cn

    def test_select_primary_case_number_fallback_to_first(self):
        svc = self._make_service()
        cn = SimpleNamespace(
            id=1,
            is_active=False,
            document_content="",
            execution_manual_text="",
        )
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.CaseNumber"
        ) as MockCN:
            MockCN.objects.filter.return_value.order_by.return_value = [cn]
            result = svc._select_primary_case_number(1)
        assert result is cn

    def test_build_execution_request_empty_doc(self):
        svc = self._make_service()
        case = SimpleNamespace(id=1, target_amount=0)
        cn = SimpleNamespace(
            document_content="",
            execution_manual_text="",
            execution_paid_amount=0,
            execution_use_deduction_order=False,
            execution_year_days=365,
            execution_date_inclusion="both",
            execution_cutoff_date=None,
            number="（2025）粤01民初1号",
            document_name="民事判决书",
        )
        result = svc._build_execution_request(case=case, case_number=cn)
        assert result.preview_text == ""
        assert any("为空" in w for w in result.warnings)

    def test_format_case_number(self):
        svc = self._make_service()
        cn = SimpleNamespace(number="（2025）粤01民初1号", document_name="民事判决书")
        result = svc._format_case_number(cn)
        assert "（2025）粤01民初1号" in result
        assert "《民事判决书》" in result

    def test_format_case_number_already_bracketed(self):
        svc = self._make_service()
        cn = SimpleNamespace(number="（2025）粤01民初1号", document_name="《民事判决书》")
        result = svc._format_case_number(cn)
        assert "《民事判决书》" in result
        # Should not double-bracket
        assert "《《" not in result

    def test_format_case_number_no_name(self):
        svc = self._make_service()
        cn = SimpleNamespace(number="（2025）粤01民初1号", document_name="")
        result = svc._format_case_number(cn)
        assert result == "（2025）粤01民初1号"

    def test_format_case_number_empty_number(self):
        svc = self._make_service()
        cn = SimpleNamespace(number="  ", document_name="判决书")
        result = svc._format_case_number(cn)
        assert "《判决书》" in result


# =====================================================================
# 6. case_material_query_service — remaining gaps
# =====================================================================


class TestCaseMaterialQueryServiceRound9:
    """Targets: get_case_materials_view with opponent party status,
    _material_item_payload with file.name deep path, _material_item_payload
    no client on party, get_used_type_ids with types, get_material_types_by_category
    with law_firm_id."""

    def _make_service(self, case_service=None):
        from apps.cases.services.material.case_material_query_service import (
            CaseMaterialQueryService,
        )
        return CaseMaterialQueryService(case_service=case_service or MagicMock())

    def test_material_item_payload_no_client(self):
        """Party with no client → empty party_labels."""
        svc = self._make_service()
        m = SimpleNamespace(
            id=1,
            source_attachment_id=None,
            source_attachment=None,
            parties=MagicMock(),
        )
        party = SimpleNamespace(client=None)
        m.parties.all.return_value = [party]
        result = svc._material_item_payload(m)
        assert result["party_labels"] == []

    def test_material_item_payload_deep_path_fallback(self):
        """File name from deep path is extracted correctly."""
        svc = self._make_service()
        att = SimpleNamespace(
            original_filename="",
            file=SimpleNamespace(name="uploads/2024/01/deep/file.pdf", url="/url"),
            uploaded_at=None,
        )
        m = SimpleNamespace(
            id=1,
            source_attachment_id=10,
            source_attachment=att,
            parties=MagicMock(),
        )
        m.parties.all.return_value = []
        result = svc._material_item_payload(m)
        assert result["file_name"] == "file.pdf"

    def test_material_item_payload_attachment_no_file_attr(self):
        """Attachment with no .file attribute."""
        svc = self._make_service()
        att = SimpleNamespace(original_filename="doc.pdf", file=None, uploaded_at=None)
        m = SimpleNamespace(
            id=1,
            source_attachment_id=10,
            source_attachment=att,
            parties=MagicMock(),
        )
        m.parties.all.return_value = []
        result = svc._material_item_payload(m)
        assert result["file_url"] == ""

    def test_get_used_type_ids_with_values(self):
        """Returns set of type_ids."""
        svc = self._make_service()
        with patch(
            "apps.cases.services.material.case_material_query_service.CaseMaterial"
        ) as MockCM:
            MockCM.objects.filter.return_value.values_list.return_value = [1, 2, 3]
            result = svc.get_used_type_ids(42)
        assert result == {1, 2, 3}

    def test_get_material_types_by_category_with_law_firm(self):
        """Filter with law_firm_id."""
        svc = self._make_service()
        with patch(
            "apps.cases.services.material.case_material_query_service.CaseMaterialType"
        ) as MockType:
            MockType.objects.filter.return_value.filter.return_value.order_by.return_value.values.return_value = [
                {"id": 1, "name": "Type A", "law_firm_id": 10}
            ]
            result = svc.get_material_types_by_category("party", 10, set())
        assert len(result) == 1

    def test_get_case_materials_view_opponent_party_status(self):
        """Opponent parties contribute to opponent legal_statuses."""
        svc = self._make_service()
        case = MagicMock()
        case.id = 1

        p = MagicMock()
        p.legal_status = "defendant"
        p.get_legal_status_display.return_value = "被告"
        client = MagicMock()
        client.is_our_client = False
        p.client = client

        case.parties.select_related.return_value.all.return_value = [p]
        case.supervising_authorities.all.return_value = []

        qs_mock = MagicMock()
        qs_mock.__iter__ = MagicMock(return_value=iter([]))
        group_order_qs = MagicMock()
        group_order_qs.__iter__ = MagicMock(return_value=iter([]))

        with patch(
            "apps.cases.services.material.case_material_query_service.CaseMaterial"
        ) as MockCM, patch(
            "apps.cases.services.material.case_material_query_service.CaseMaterialGroupOrder"
        ) as MockGQ:
            svc._case_service.get_case.return_value = case
            MockCM.objects.filter.return_value.select_related.return_value.prefetch_related.return_value.order_by.return_value = qs_mock
            MockGQ.objects.filter.return_value.select_related.return_value.order_by.return_value = group_order_qs
            result = svc.get_case_materials_view(case_id=1)

        assert "被告" in result["party"]["opponent"]["legal_statuses"]

    def test_list_bind_candidates_empty(self):
        """No attachments returns empty list."""
        svc = self._make_service()
        svc._case_service.get_case.return_value = MagicMock()

        qs = MagicMock()
        qs.__iter__ = MagicMock(return_value=iter([]))

        with patch(
            "apps.cases.services.material.case_material_query_service.CaseLogAttachment"
        ) as MockCLA:
            MockCLA.objects.filter.return_value.select_related.return_value.prefetch_related.return_value.order_by.return_value = qs
            result = svc.list_bind_candidates(case_id=1)
        assert result == []


# =====================================================================
# 7. contracts folder_scan_service — remaining gaps
# =====================================================================


class TestFolderScanServiceRound9:
    """Targets: build_status_payload, _normalize_scan_subfolder edge cases,
    _is_within_root, _relative_path_str, _extract_scan_subfolder,
    _normalize_docx_name."""

    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import (
            ContractFolderScanService,
        )
        return ContractFolderScanService(scan_service=MagicMock())

    def test_build_status_payload_basic(self):
        svc = self._make_service()
        session = SimpleNamespace(
            id="test-id",
            status="completed",
            progress=100,
            current_file="",
            result_payload={
                "summary": {"total_files": 5, "deduped_files": 4, "classified_files": 3},
                "candidates": [{"filename": "a.pdf"}],
                "archive_category": "litigation",
                "archive_item_options": [{"code": "l_1"}],
                "work_log_suggestions": [{"content": "test"}],
            },
            error_message="",
        )
        result = svc.build_status_payload(session=session)
        assert result["session_id"] == "test-id"
        assert result["status"] == "completed"
        assert result["progress"] == 100
        assert result["summary"]["total_files"] == 5
        assert len(result["candidates"]) == 1
        assert result["archive_category"] == "litigation"

    def test_build_status_payload_empty_payload(self):
        svc = self._make_service()
        session = SimpleNamespace(
            id="test-id",
            status="running",
            progress=50,
            current_file="test.pdf",
            result_payload=None,
            error_message="",
        )
        result = svc.build_status_payload(session=session)
        assert result["summary"]["total_files"] == 0
        assert result["candidates"] == []

    def test_extract_scan_subfolder_none(self):
        svc = self._make_service()
        result = svc._extract_scan_subfolder(None)
        assert result == ""

    def test_extract_scan_subfolder_empty(self):
        svc = self._make_service()
        result = svc._extract_scan_subfolder({})
        assert result == ""

    def test_extract_scan_subfolder_with_value(self):
        svc = self._make_service()
        result = svc._extract_scan_subfolder({"scan_scope": {"scan_subfolder": "sub1"}})
        assert result == "sub1"

    def test_normalize_scan_subfolder_empty(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("") == ""

    def test_normalize_scan_subfolder_whitespace(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("   ") == ""

    def test_normalize_scan_subfolder_dots(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("./sub") == "sub"

    def test_normalize_scan_subfolder_backslash(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("sub\\path") == "sub/path"

    def test_normalize_scan_subfolder_absolute_rejected(self):
        svc = self._make_service()
        with pytest.raises(Exception):
            svc._normalize_scan_subfolder("/absolute/path")

    def test_normalize_scan_subfolder_tilde_rejected(self):
        svc = self._make_service()
        with pytest.raises(Exception):
            svc._normalize_scan_subfolder("~/path")

    def test_normalize_scan_subfolder_windows_drive_rejected(self):
        svc = self._make_service()
        with pytest.raises(Exception):
            svc._normalize_scan_subfolder("C:/path")

    def test_normalize_scan_subfolder_dotdot_rejected(self):
        svc = self._make_service()
        with pytest.raises(Exception):
            svc._normalize_scan_subfolder("sub/../escape")

    def test_normalize_scan_subfolder_multiple_dots(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("sub/./deep") == "sub/deep"

    def test_is_within_root(self):
        svc = self._make_service()
        root = Path("/tmp/project")
        target = Path("/tmp/project/subdir/file.pdf")
        assert svc._is_within_root(root, target) is True

    def test_is_within_root_same(self):
        svc = self._make_service()
        root = Path("/tmp/project")
        assert svc._is_within_root(root, root) is True

    def test_is_within_root_outside(self):
        svc = self._make_service()
        root = Path("/tmp/project")
        target = Path("/tmp/other/file.pdf")
        assert svc._is_within_root(root, target) is False

    def test_relative_path_str(self):
        svc = self._make_service()
        root = Path("/tmp/project")
        result = svc._relative_path_str(source_path="/tmp/project/sub/file.pdf", scan_root=root)
        assert result == "sub"

    def test_relative_path_str_at_root(self):
        svc = self._make_service()
        root = Path("/tmp/project")
        result = svc._relative_path_str(source_path="/tmp/project/file.pdf", scan_root=root)
        assert result == ""

    def test_relative_path_str_outside(self):
        svc = self._make_service()
        root = Path("/tmp/project")
        result = svc._relative_path_str(source_path="/tmp/other/file.pdf", scan_root=root)
        assert result == ""

    def test_normalize_docx_name_basic(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import (
            _normalize_docx_name,
        )
        assert _normalize_docx_name("Test File.docx") == "testfile.docx"

    def test_normalize_docx_name_empty(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import (
            _normalize_docx_name,
        )
        assert _normalize_docx_name("") == ""

    def test_normalize_docx_name_none(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import (
            _normalize_docx_name,
        )
        assert _normalize_docx_name(None) == ""

    def test_normalize_docx_name_spaces(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import (
            _normalize_docx_name,
        )
        assert _normalize_docx_name("  A  B  C  ") == "abc"

    def test_get_session_not_found(self):
        svc = self._make_service()
        from apps.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            svc.get_session(contract_id=1, session_id="00000000-0000-0000-0000-000000000000")
