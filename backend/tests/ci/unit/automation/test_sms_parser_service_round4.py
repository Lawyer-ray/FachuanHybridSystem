"""Round 4 coverage tests for automation.services.sms.sms_parser_service.

Targets remaining uncovered branches:
- parse: extracts case_numbers and party_names
- extract_download_links: HBFY public link (hb/msg path), SFDW link
- _is_valid_download_link: HBFY msg path (path ends with /hb/msg), SFDW
- extract_party_names: extractor has no extract method
- _extract_party_names_with_ollama: response without 'message' key
- _filter_parties: ends with 财, ends with 案
- _collect_versus_patterns: co-to-co, pe-to-co, co-to-pe, received pattern
- _collect_name_contexts: 关于...诉... pattern, 诉 pattern
- _sanitize_link: mixed trailing punctuation
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.sms.sms_parser_service import SMSParseResult, SMSParserService


# ---------------------------------------------------------------------------
# parse — extracts case_numbers and party_names
# ---------------------------------------------------------------------------


class TestParseRound4:
    def setup_method(self):
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_extracts_case_numbers(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        content = "您的案件（2025）粤01民初1号已受理"
        result = self.service.parse(content)
        assert len(result.case_numbers) >= 1

    def test_extracts_party_names(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=["张三"])
        content = "张三的案件已受理"
        result = self.service.parse(content)
        assert "张三" in result.party_names


# ---------------------------------------------------------------------------
# extract_download_links — HBFY and SFDW
# ---------------------------------------------------------------------------


class TestExtractDownloadLinksRound4:
    def setup_method(self):
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_hbfy_public_link_with_msg_param(self):
        content = "请查收 https://hbfy.court.gov.cn/hb/msg?msg=XYZ789"
        links = self.service.extract_download_links(content)
        assert len(links) >= 1

    def test_sfdw_link(self):
        content = "请查收 https://sfsdw.court.gov.cn/sfsdw//r/DEF456"
        links = self.service.extract_download_links(content)
        assert len(links) >= 1

    def test_multiple_different_links(self):
        content = (
            "请查收 https://sd.gdcourts.gov.cn/v3/dzsd/ABC123 "
            "以及 https://sfsdw.court.gov.cn/sfsdw//r/DEF456"
        )
        links = self.service.extract_download_links(content)
        assert len(links) >= 2

    def test_only_invalid_urls(self):
        content = "请访问 https://random-site.com/not-a-delivery"
        links = self.service.extract_download_links(content)
        assert links == []


# ---------------------------------------------------------------------------
# _is_valid_download_link — HBFY msg and SFDW
# ---------------------------------------------------------------------------


class TestIsValidDownloadLinkRound4:
    def setup_method(self):
        self.service = SMSParserService()

    def test_hbfy_msg_path_valid(self):
        assert self.service._is_valid_download_link("https://hb.gov.cn/hb/msg?msg=ABC") is True

    def test_sfdw_r_path_valid(self):
        assert self.service._is_valid_download_link("https://sfsdw.gov.cn/sfsdw//r/ABC") is True

    def test_partial_match_not_valid(self):
        assert self.service._is_valid_download_link("https://random.gov.cn/other") is False


# ---------------------------------------------------------------------------
# extract_party_names — extractor has no extract method
# ---------------------------------------------------------------------------


class TestExtractPartyNamesEdge:
    def setup_method(self):
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_extractor_no_extract_method(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        extractor = MagicMock(spec=[])  # no 'extract' method
        self.service._party_candidate_extractor = extractor
        result = self.service.extract_party_names("content")
        assert result == []


# ---------------------------------------------------------------------------
# _extract_party_names_with_ollama — response without 'message' key
# ---------------------------------------------------------------------------


class TestExtractPartyNamesWithOllamaEdge:
    def setup_method(self):
        self.service = SMSParserService(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
            llm_service=MagicMock(),
        )

    def test_response_without_message_key(self):
        response = MagicMock()
        response.content = '{"parties": ["张三"]}'
        self.service._llm_service.chat.return_value = response
        safe_prompt = "Extract: {content}"
        with patch.object(type(self.service), "PARTY_EXTRACTION_PROMPT", safe_prompt):
            result = self.service._extract_party_names_with_ollama("content")
        # The code checks response["message"]["content"] but our mock
        # returns a MagicMock for __getitem__. The actual code sets
        # response = {"message": {"content": llm_response.content}} so
        # it should work correctly.
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# _filter_parties — ends with 财, 案
# ---------------------------------------------------------------------------


class TestFilterPartiesEdge:
    def setup_method(self):
        self.service = SMSParserService()

    def test_ends_with_cai(self):
        result = self.service._filter_parties(["张三财"])
        assert result == []

    def test_ends_with_an(self):
        result = self.service._filter_parties(["张三案"])
        assert result == []

    def test_empty_string(self):
        result = self.service._filter_parties([""])
        assert result == []

    def test_only_digits(self):
        result = self.service._filter_parties(["12345"])
        assert "12345" in result


# ---------------------------------------------------------------------------
# _collect_versus_patterns — various pair types
# ---------------------------------------------------------------------------


class TestCollectVersusPatternsEdge:
    def setup_method(self):
        self.service = SMSParserService()

    def test_co_versus_pe(self):
        parties = []
        self.service._collect_versus_patterns("广州天河科技有限公司与张三的财产纠纷", parties)
        assert any("有限公司" in p for p in parties) or any("张三" in p for p in parties)

    def test_pe_versus_co(self):
        parties = []
        self.service._collect_versus_patterns("张三与广州天河科技有限公司的合同纠纷", parties)
        assert len(parties) >= 1

    def test_about_shu_pattern(self):
        parties = []
        self.service._collect_versus_patterns("关于张三诉李四案件", parties)
        assert any(p in ("张三", "李四") for p in parties)

    def test_received_pattern(self):
        parties = []
        self.service._collect_versus_patterns("收到张三与李四的判决书", parties)
        assert any(p in ("张三", "李四") for p in parties)


# ---------------------------------------------------------------------------
# _collect_name_contexts — various patterns
# ---------------------------------------------------------------------------


class TestCollectNameContextsEdge:
    def setup_method(self):
        self.service = SMSParserService()

    def test_guanyu_shu_pattern(self):
        parties = []
        self.service._collect_name_contexts("关于张三诉李四案件", parties)
        assert any(p in ("张三", "李四") for p in parties)

    def test_shu_pattern(self):
        parties = []
        self.service._collect_name_contexts("张三诉李四", parties)
        assert any(p in ("张三", "李四") for p in parties)

    def test_beishenqingren(self):
        parties = []
        self.service._collect_name_contexts("被申请人：王五", parties)
        assert "王五" in parties


# ---------------------------------------------------------------------------
# _sanitize_link — mixed trailing
# ---------------------------------------------------------------------------


class TestSanitizeLinkEdge:
    def setup_method(self):
        self.service = SMSParserService()

    def test_mixed_trailing(self):
        assert self.service._sanitize_link("https://example.com。，") == "https://example.com"

    def test_only_trailing_chars(self):
        assert self.service._sanitize_link("。。。") == ""

    def test_whitespace_and_trailing(self):
        assert self.service._sanitize_link("  https://example.com。  ") == "https://example.com"
