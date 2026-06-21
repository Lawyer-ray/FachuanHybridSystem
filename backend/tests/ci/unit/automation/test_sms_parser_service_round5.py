"""sms_parser_service.py — round5 tests for uncovered branches.

Covers:
- parse: filing_notification and info_notification paths
- extract_party_names: candidate extraction success and matching success paths
- _find_existing_clients_in_sms: exception handling, short name skipping
- _extract_party_names_with_ollama: LLM error, invalid JSON response
- _is_valid_download_link: zxfw hash-fragment with params
- _collect_company_names: various company patterns
- _filter_parties: starts with '的', too short, too long, invalid chars, exclude keywords
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.automation.models import CourtSMSType
from apps.automation.services.sms.sms_parser_service import SMSParserService


# ── parse — SMS type detection ────────────────────────────────────────────────


class TestParseSmsTypeDetection:
    def setup_method(self):
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])

    def test_filing_notification(self):
        content = "您的案件已立案，案号为（2025）粤01民初1号"
        result = self.service.parse(content)
        assert result.sms_type == CourtSMSType.FILING_NOTIFICATION

    def test_info_notification(self):
        content = "您的案件已分配法官"
        result = self.service.parse(content)
        assert result.sms_type == CourtSMSType.INFO_NOTIFICATION

# ── extract_party_names — candidate extraction ────────────────────────────────


class TestExtractPartyNamesCandidatePath:
    def setup_method(self):
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_extractor_returns_candidates_then_matches(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        extractor = MagicMock()
        extractor.extract.return_value = ["张三", "李四"]
        self.service._party_candidate_extractor = extractor

        mock_client = MagicMock()
        mock_client.name = "张三"
        self.service._party_matching_service.extract_and_match_parties_from_sms.return_value = [mock_client]

        result = self.service.extract_party_names("张三与李四的纠纷")
        assert "张三" in result

    def test_extractor_exception_returns_empty(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        extractor = MagicMock()
        extractor.extract.side_effect = Exception("fail")
        self.service._party_candidate_extractor = extractor

        result = self.service.extract_party_names("content")
        assert result == []

    def test_candidates_empty_returns_empty(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        extractor = MagicMock()
        extractor.extract.return_value = []
        self.service._party_candidate_extractor = extractor

        result = self.service.extract_party_names("content")
        assert result == []

    def test_matching_service_exception_returns_empty(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        extractor = MagicMock()
        extractor.extract.return_value = ["张三"]
        self.service._party_candidate_extractor = extractor
        self.service._party_matching_service.extract_and_match_parties_from_sms.side_effect = Exception("fail")

        result = self.service.extract_party_names("张三的纠纷")
        assert result == []

    def test_matching_service_no_method(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        extractor = MagicMock()
        extractor.extract.return_value = ["张三"]
        self.service._party_candidate_extractor = extractor
        # No extract_and_match_parties_from_sms method
        self.service._party_matching_service = MagicMock(spec=[])
        result = self.service.extract_party_names("张三的纠纷")
        assert result == []

    def test_matched_client_empty_name_skipped(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        extractor = MagicMock()
        extractor.extract.return_value = ["张三"]
        self.service._party_candidate_extractor = extractor
        mock_client = MagicMock()
        mock_client.name = ""  # Empty name
        self.service._party_matching_service.extract_and_match_parties_from_sms.return_value = [mock_client]
        result = self.service.extract_party_names("张三的纠纷")
        assert result == []

    def test_matched_client_duplicate_name_skipped(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        extractor = MagicMock()
        extractor.extract.return_value = ["张三"]
        self.service._party_candidate_extractor = extractor
        c1 = MagicMock()
        c1.name = "张三"
        c2 = MagicMock()
        c2.name = "张三"
        self.service._party_matching_service.extract_and_match_parties_from_sms.return_value = [c1, c2]
        result = self.service.extract_party_names("张三的纠纷")
        assert result.count("张三") == 1


# ── _find_existing_clients_in_sms ────────────────────────────────────────────


class TestFindExistingClientsInSms:
    def setup_method(self):
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
        )

    def test_short_name_skipped(self):
        c1 = MagicMock()
        c1.name = "张"
        self.service._client_service.get_all_clients_internal.return_value = [c1]
        result = self.service._find_existing_clients_in_sms("张三的纠纷")
        assert "张" not in result

    def test_exception_returns_empty(self):
        self.service._client_service.get_all_clients_internal.side_effect = Exception("db error")
        result = self.service._find_existing_clients_in_sms("content")
        assert result == []


# ── _extract_party_names_with_ollama ─────────────────────────────────────────


class TestExtractPartyNamesOllamaEdge:
    def setup_method(self):
        self.service = SMSParserService(
            ollama_model="test",
            ollama_base_url="http://localhost",
            llm_service=MagicMock(),
        )

    def test_llm_error(self):
        from apps.core.llm.exceptions import LLMError
        self.service._llm_service = MagicMock()
        self.service._llm_service.chat.side_effect = LLMError("fail")
        with patch.object(type(self.service), "PARTY_EXTRACTION_PROMPT", "{content}"):
            result = self.service._extract_party_names_with_ollama("content")
            assert result == []

    def test_invalid_json_response(self):
        self.service._llm_service = MagicMock()
        response = MagicMock()
        response.content = "not json"
        self.service._llm_service.chat.return_value = response
        with patch.object(type(self.service), "PARTY_EXTRACTION_PROMPT", "{content}"):
            result = self.service._extract_party_names_with_ollama("content")
            assert result == []

    def test_json_no_parties_key(self):
        self.service._llm_service = MagicMock()
        response = MagicMock()
        response.content = '{"something": "else"}'
        self.service._llm_service.chat.return_value = response
        with patch.object(type(self.service), "PARTY_EXTRACTION_PROMPT", "{content}"):
            result = self.service._extract_party_names_with_ollama("content")
            assert result == []


# ── _filter_parties ──────────────────────────────────────────────────────────


class TestFilterPartiesEdge:
    def setup_method(self):
        self.service = SMSParserService()

    def test_starts_with_de(self):
        result = self.service._filter_parties(["的张三"])
        assert result == []

    def test_too_short(self):
        result = self.service._filter_parties(["张"])
        assert result == []

    def test_too_long(self):
        result = self.service._filter_parties(["a" * 31])
        assert result == []

    def test_invalid_chars(self):
        result = self.service._filter_parties(["abc张三"])
        assert result == []

    def test_exclude_keyword(self):
        result = self.service._filter_parties(["人民法院"])
        assert result == []

    def test_invalid_fragment(self):
        result = self.service._filter_parties(["有限公司"])
        assert result == []


# ── _is_valid_download_link — zxfw hash fragment ─────────────────────────────


class TestIsValidDownloadLinkZxfw:
    def setup_method(self):
        self.service = SMSParserService()

    def test_zxfw_with_all_params(self):
        link = "https://court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=1&sdbh=2&sdsin=3"
        assert self.service._is_valid_download_link(link) is True

    def test_zxfw_missing_param(self):
        link = "https://court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=1&sdbh=2"
        assert self.service._is_valid_download_link(link) is False

    def test_gdems_link(self):
        link = "https://sd.gdcourts.gov.cn/v3/dzsd/ABC123"
        assert self.service._is_valid_download_link(link) is True

    def test_jysd_link(self):
        link = "https://example.com/sd?key=ABC123"
        assert self.service._is_valid_download_link(link) is True

    def test_hbfy_account_link(self):
        link = "https://hb.court.gov.cn/sfsddz"
        assert self.service._is_valid_download_link(link) is True

    def test_hbfy_msg_link(self):
        link = "https://hb.court.gov.cn/hb/msg?msg=XYZ"
        assert self.service._is_valid_download_link(link) is True


# ── _collect_company_names ────────────────────────────────────────────────────


class TestCollectCompanyNames:
    def setup_method(self):
        self.service = SMSParserService()

    def test_limited_company(self):
        parties = []
        self.service._collect_company_names("广州天河科技有限责任公司与张三", parties)
        assert any("有限责任公司" in p for p in parties)

    def test_stock_company(self):
        parties = []
        self.service._collect_company_names("深圳华为技术有限公司", parties)
        assert any("有限公司" in p for p in parties)

    def test_group_company(self):
        parties = []
        self.service._collect_company_names("腾讯集团有限公司与李四", parties)
        assert any("集团" in p or "有限公司" in p for p in parties)
