"""
Tests for apps.automation.services.sms — SMS 解析、匹配、通知、去重、案号提取
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# SMSParserService 测试
# ============================================================


class TestSMSParserService:
    """SMSParserService 测试"""

    def _make_service(self, **kwargs):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        return SMSParserService(**kwargs)

    def test_extract_download_links_wssd_valid(self) -> None:
        svc = self._make_service()
        content = "请查收文书 https://example.com/zxfw/#/pagesajkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=abc"
        links = svc.extract_download_links(content)
        assert len(links) >= 1

    def test_extract_download_links_gdems(self) -> None:
        svc = self._make_service()
        content = "请查收 https://courts.example.com/v3/dzsd/abc123"
        links = svc.extract_download_links(content)
        assert len(links) >= 1
        assert "dzsd" in links[0]

    def test_extract_download_links_jysd(self) -> None:
        svc = self._make_service()
        content = "请查收 https://example.com/sd?key=abc123"
        links = svc.extract_download_links(content)
        assert len(links) >= 1

    def test_extract_download_links_sfdw(self) -> None:
        svc = self._make_service()
        content = "请查收 https://example.com/sfsdw//r/abc123"
        links = svc.extract_download_links(content)
        assert len(links) >= 1

    def test_extract_download_links_empty(self) -> None:
        svc = self._make_service()
        assert svc.extract_download_links("") == []
        assert svc.extract_download_links("普通短信没有链接") == []

    def test_extract_download_links_dedup(self) -> None:
        svc = self._make_service()
        link = "https://example.com/sd?key=abc123"
        content = f"{link} {link}"
        links = svc.extract_download_links(content)
        assert len(links) == 1

    def test_extract_case_numbers(self) -> None:
        svc = self._make_service()
        content = "关于（2025）粤0604民初41257号一案"
        numbers = svc.extract_case_numbers(content)
        assert any("41257" in n for n in numbers)

    def test_extract_case_numbers_empty(self) -> None:
        svc = self._make_service()
        assert svc.extract_case_numbers("普通短信") == []

    def test_extract_verification_code_found(self) -> None:
        svc = self._make_service()
        code = svc.extract_verification_code("请查收验证码：ABCD")
        assert code == "ABCD"

    def test_extract_verification_code_not_found(self) -> None:
        svc = self._make_service()
        assert svc.extract_verification_code("没有验证码") == ""

    def test_sanitize_link(self) -> None:
        svc = self._make_service()
        assert svc._sanitize_link("https://example.com.") == "https://example.com"
        assert svc._sanitize_link("https://example.com，") == "https://example.com"
        assert svc._sanitize_link("") == ""

    def test_is_valid_download_link_gdems(self) -> None:
        svc = self._make_service()
        assert svc._is_valid_download_link("https://example.com/v3/dzsd/abc123") is True

    def test_is_valid_download_link_sfdw(self) -> None:
        svc = self._make_service()
        assert svc._is_valid_download_link("https://example.com/sfsdw//r/abc") is True

    def test_is_valid_download_link_invalid(self) -> None:
        svc = self._make_service()
        assert svc._is_valid_download_link("https://example.com/random") is False

    def test_parse_info_notification(self) -> None:
        svc = self._make_service()
        content = "您好，您的案件正在审理中"
        result = svc.parse(content)
        assert result.sms_type == "info_notification"
        assert result.has_valid_download_link is False

    def test_parse_filing_notification(self) -> None:
        svc = self._make_service()
        content = "您的立案申请已通过"
        result = svc.parse(content)
        assert result.sms_type == "filing_notification"

    def test_find_existing_clients_in_sms(self) -> None:
        svc = self._make_service(client_service=MagicMock())
        client1 = MagicMock()
        client1.name = "张三"
        client2 = MagicMock()
        client2.name = "李四"
        client3 = MagicMock()
        client3.name = "短"  # too short
        svc._client_service.get_all_clients_internal.return_value = [client1, client2, client3]
        result = svc._find_existing_clients_in_sms("张三与李四的纠纷")
        assert "张三" in result
        assert "李四" in result
        assert "短" not in result

    def test_find_existing_clients_in_sms_error(self) -> None:
        svc = self._make_service(client_service=MagicMock())
        svc._client_service.get_all_clients_internal.side_effect = Exception("db error")
        result = svc._find_existing_clients_in_sms("test")
        assert result == []


# ============================================================
# CourtSMSDedupService 测试
# ============================================================


class TestCourtSMSDedupService:
    """CourtSMSDedupService 测试"""

    def test_build_existing_sms_result_with_notification(self) -> None:
        from apps.automation.services.sms.court_sms_dedup_service import CourtSMSDedupService

        svc = CourtSMSDedupService()
        sms = MagicMock()
        sms.case_id = 1
        sms.case_log_id = 10
        sms.feishu_sent_at = None
        sms.notification_results = {"feishu": {"success": True}}
        result = svc.build_existing_sms_result(sms, "/path/to/file.pdf")
        assert result["success"] is True
        assert result["notification_sent"] is True
        assert result["deduplicated"] is True

    def test_build_existing_sms_result_no_notification(self) -> None:
        from apps.automation.services.sms.court_sms_dedup_service import CourtSMSDedupService

        svc = CourtSMSDedupService()
        sms = MagicMock()
        sms.case_id = 1
        sms.case_log_id = None
        sms.feishu_sent_at = None
        sms.notification_results = None
        result = svc.build_existing_sms_result(sms, "/path")
        assert result["notification_sent"] is False

    def test_normalize_text(self) -> None:
        from apps.automation.services.sms.court_sms_dedup_service import CourtSMSDedupService

        svc = CourtSMSDedupService()
        assert svc._normalize_text("  hello   world  ") == "hello world"
        assert svc._normalize_text(None) == ""

    def test_hash_payload_deterministic(self) -> None:
        from apps.automation.services.sms.court_sms_dedup_service import CourtSMSDedupService

        svc = CourtSMSDedupService()
        h1 = svc._hash_payload("test")
        h2 = svc._hash_payload("test")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256


# ============================================================
# CaseNumberExtractorService 测试
# ============================================================


class TestCaseNumberExtractorService:
    """CaseNumberExtractorService 测试"""

    def _make_service(self, **kwargs):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService

        return CaseNumberExtractorService(**kwargs)

    def test_extract_from_document_empty_path(self) -> None:
        svc = self._make_service()
        assert svc.extract_from_document("") == []

    def test_extract_from_content_empty(self) -> None:
        svc = self._make_service()
        assert svc.extract_from_content("") == []
        assert svc.extract_from_content("   ") == []

    def test_extract_from_content_with_provider(self) -> None:
        provider = MagicMock()
        provider.extract.return_value = '{"case_numbers": ["（2025）粤0604民初123号"]}'
        svc = self._make_service(extraction_provider=provider, case_number_service=MagicMock())
        svc._case_number_service.normalize_case_number.return_value = "（2025）粤0604民初123号"
        result = svc.extract_from_content("some content")
        assert "（2025）粤0604民初123号" in result

    def test_extract_from_content_provider_error(self) -> None:
        provider = MagicMock()
        provider.extract.side_effect = Exception("provider error")
        svc = self._make_service(extraction_provider=provider)
        result = svc.extract_from_content("some content")
        assert result == []

    def test_parse_ollama_response_valid_json(self) -> None:
        svc = self._make_service(case_number_service=MagicMock())
        svc._case_number_service.normalize_case_number.side_effect = lambda x: x
        response = '{"case_numbers": ["（2025）粤0604民初123号"]}'
        # Mock validate_and_normalize to avoid full logic
        with patch.object(svc, 'validate_and_normalize', return_value=["（2025）粤0604民初123号"]):
            result = svc._parse_ollama_response(response)
            assert "（2025）粤0604民初123号" in result

    def test_parse_ollama_response_invalid_json(self) -> None:
        svc = self._make_service()
        with patch.object(svc, '_extract_fallback', return_value=[]):
            result = svc._parse_ollama_response("not json")
            assert result == []

    def test_build_extract_prompt(self) -> None:
        svc = self._make_service()
        prompt = svc._build_extract_prompt("文书内容")
        assert "文书内容" in prompt
        assert "案号" in prompt

    def test_validate_and_normalize_empty(self) -> None:
        svc = self._make_service()
        assert svc.validate_and_normalize([]) == []

    def test_deduplicate(self) -> None:
        svc = self._make_service(case_number_service=MagicMock())
        svc._case_number_service.normalize_case_number.side_effect = lambda x: x
        result = svc._deduplicate(["（2025）粤0604民初123号", "（2025）粤0604民初123号"])
        assert len(result) == 1

    def test_deduplicate_empty(self) -> None:
        svc = self._make_service()
        assert svc._deduplicate([]) == []

    def test_regex_extract_numbers(self) -> None:
        svc = self._make_service()
        result = svc._regex_extract_numbers("案号：（2025）粤0604民初12345号")
        assert len(result) > 0

    def test_sync_to_case_empty_case_id(self) -> None:
        svc = self._make_service()
        assert svc.sync_to_case(0, ["test"], 1) == 0

    def test_sync_to_case_empty_numbers(self) -> None:
        svc = self._make_service()
        assert svc.sync_to_case(1, [], 1) == 0


# ============================================================
# SMSNotificationService 测试
# ============================================================


class TestSMSNotificationService:
    """SMSNotificationService 测试"""

    def test_send_notification_no_case(self) -> None:
        from apps.automation.services.sms.sms_notification_service import SMSNotificationService

        svc = SMSNotificationService(case_chat_service=MagicMock())
        sms = MagicMock()
        sms.case = None
        sms.id = 1
        result = svc.send_case_chat_notification(sms)
        assert result.any_success is False

    def test_send_notification_no_platforms(self) -> None:
        from apps.automation.services.sms.sms_notification_service import SMSNotificationService

        svc = SMSNotificationService(case_chat_service=MagicMock())
        sms = MagicMock()
        sms.case = MagicMock()
        sms.case.id = 1
        sms.id = 1
        with patch.object(svc, '_get_available_platforms', return_value=[]):
            result = svc.send_case_chat_notification(sms)
            assert result.any_success is False

    def test_send_notification_success(self) -> None:
        from apps.automation.services.sms.sms_notification_service import SMSNotificationService
        from apps.core.models.enums import ChatPlatform

        mock_chat_service = MagicMock()
        svc = SMSNotificationService(case_chat_service=mock_chat_service)
        sms = MagicMock()
        sms.case = MagicMock()
        sms.case.id = 1
        sms.id = 1
        sms.content = "test"

        mock_chat = MagicMock()
        mock_chat.chat_id = "chat123"
        mock_chat_service.get_or_create_chat.return_value = mock_chat
        send_result = MagicMock()
        send_result.success = True
        mock_chat_service.send_document_notification.return_value = send_result

        with patch.object(svc, '_get_available_platforms', return_value=[ChatPlatform.FEISHU]):
            result = svc.send_case_chat_notification(sms, ["/path/doc.pdf"])
            assert result.any_success is True

    def test_send_notification_chat_creation_failure(self) -> None:
        from apps.automation.services.sms.sms_notification_service import SMSNotificationService
        from apps.core.models.enums import ChatPlatform

        mock_chat_service = MagicMock()
        svc = SMSNotificationService(case_chat_service=mock_chat_service)
        sms = MagicMock()
        sms.case = MagicMock()
        sms.case.id = 1
        sms.id = 1

        mock_chat_service.get_or_create_chat.side_effect = Exception("creation failed")

        with patch.object(svc, '_get_available_platforms', return_value=[ChatPlatform.FEISHU]):
            result = svc.send_case_chat_notification(sms)
            assert result.any_success is False


# ============================================================
# TaskRecoveryService 测试
# ============================================================


class TestTaskRecoveryService:
    """TaskRecoveryService 测试"""

    def test_defaults(self) -> None:
        from apps.automation.services.sms.task_recovery_service import TaskRecoveryService

        svc = TaskRecoveryService()
        assert svc.stuck_timeout_minutes == 30
        assert svc.max_retry_count == 3
        assert svc.recovery_max_age_hours == 24


# ============================================================
# CourtSMSRecommendationService 测试
# ============================================================


class TestCourtSMSRecommendationService:
    """CourtSMSRecommendationService 测试"""

    def test_collect_year_court_prefixes(self) -> None:
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        prefixes = CourtSMSRecommendationService._collect_year_court_prefixes(
            ["（2025）粤0605民初123号"]
        )
        assert len(prefixes) == 1
        assert "2025" in prefixes[0]
        assert "粤0605" in prefixes[0]

    def test_collect_year_court_prefixes_empty(self) -> None:
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        assert CourtSMSRecommendationService._collect_year_court_prefixes([]) == []

    def test_build_query_with_numbers(self) -> None:
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        q = CourtSMSRecommendationService._build_query(
            normalized_numbers=["（2025）粤0605民初123号"],
            year_court_prefixes=[],
            court_name=None,
            party_names=[],
        )
        assert q is not None

    def test_build_query_empty(self) -> None:
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        q = CourtSMSRecommendationService._build_query([], [], None, [])
        assert q is None

    def test_build_query_with_court_name(self) -> None:
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        q = CourtSMSRecommendationService._build_query(
            [], [], "佛山市禅城区人民法院", []
        )
        assert q is not None

    def test_build_query_with_parties(self) -> None:
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        q = CourtSMSRecommendationService._build_query([], [], None, ["张三"])
        assert q is not None

    def test_build_query_short_party_name_skipped(self) -> None:
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        q = CourtSMSRecommendationService._build_query([], [], None, ["张"])  # too short
        assert q is None

    def test_extract_court_name_from_content(self) -> None:
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        svc = CourtSMSRecommendationService()
        name = svc._extract_court_name_from_content("佛山市禅城区人民法院通知你")
        assert name == "佛山市禅城区人民法院"

    def test_extract_court_name_from_content_none(self) -> None:
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        svc = CourtSMSRecommendationService()
        assert svc._extract_court_name_from_content("没有法院名") is None
