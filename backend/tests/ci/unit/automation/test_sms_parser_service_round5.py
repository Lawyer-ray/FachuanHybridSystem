"""sms_parser_service.py — round5 tests for uncovered branches.

Covers:
- parse: filing_notification and info_notification paths
- extract_party_names: candidate extraction success and matching success paths
- _find_existing_clients_in_sms: exception handling, short name skipping
- _is_valid_download_link: zxfw hash-fragment with params
"""
from __future__ import annotations

from unittest.mock import MagicMock

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


