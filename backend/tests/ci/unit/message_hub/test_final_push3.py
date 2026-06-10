"""Final push coverage tests for message_hub — court schedule fetcher parsing."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock, patch

import pytest


# ============================================================================
# message_hub/services/court/court_schedule_fetcher.py tests
# ============================================================================


class TestParseDatetime:
    def test_valid_format(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _parse_datetime

        with patch("apps.message_hub.services.court.court_schedule_fetcher.timezone") as mock_tz:
            mock_tz.make_aware.return_value = datetime(2026, 5, 29, 16, 30)
            result = _parse_datetime("2026-05-29 16:30")
            assert result == datetime(2026, 5, 29, 16, 30)

    def test_invalid_format_returns_now(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _parse_datetime

        with patch("apps.message_hub.services.court.court_schedule_fetcher.timezone") as mock_tz:
            mock_tz.now.return_value = datetime(2024, 1, 1)
            result = _parse_datetime("invalid")
            assert result == datetime(2024, 1, 1)

    def test_empty_string_returns_now(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _parse_datetime

        with patch("apps.message_hub.services.court.court_schedule_fetcher.timezone") as mock_tz:
            mock_tz.now.return_value = datetime(2024, 1, 1)
            result = _parse_datetime("")
            assert result == datetime(2024, 1, 1)


class TestExtractPartyNames:
    def test_basic_extraction(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _extract_party_names

        text = "佛山市升平百货有限公司与佛山市仲满金属材料有限公司追偿权纠纷一案"
        names = _extract_party_names(text)
        assert "佛山市升平百货有限公司" in names
        assert "佛山市仲满金属材料有限公司" in names

    def test_with_comma_separated_defendants(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _extract_party_names

        text = "佛山市升平百货有限公司与佛山市仲满金属材料有限公司,郑汝钋,石莹追偿权纠纷一案"
        names = _extract_party_names(text)
        assert "佛山市升平百货有限公司" in names
        assert "郑汝钋" in names
        assert "石莹" in names

    def test_empty_text(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _extract_party_names

        assert _extract_party_names("") == []

    def test_no_wu_separator(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _extract_party_names

        # Without "与" separator, returns empty
        result = _extract_party_names("没有分隔符的文本")
        assert result == []

    def test_strips_yi_an_suffix(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _extract_party_names

        text = "张三与李四买卖合同纠纷一案"
        names = _extract_party_names(text)
        assert "张三" in names
        assert "李四" in names


class TestStripCaseCauseSuffix:
    def test_buy_sell_contract(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _strip_case_cause_suffix

        result = _strip_case_cause_suffix("汪达买卖合同纠纷")
        assert result == "汪达"

    def test_recovery_dispute(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _strip_case_cause_suffix

        result = _strip_case_cause_suffix("石莹追偿权纠纷")
        assert result == "石莹"

    def test_no_suffix(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _strip_case_cause_suffix

        result = _strip_case_cause_suffix("佛山市仲满金属材料有限公司")
        assert result == "佛山市仲满金属材料有限公司"

    def test_simple_dispute(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _strip_case_cause_suffix

        result = _strip_case_cause_suffix("张三纠纷")
        assert result == "张三"

    def test_contract_dispute(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _strip_case_cause_suffix

        result = _strip_case_cause_suffix("李四合同纠纷")
        assert result == "李四"

    def test_empty_after_strip(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _strip_case_cause_suffix

        result = _strip_case_cause_suffix("纠纷")
        assert result == "纠纷"  # doesn't strip if nothing left


class TestIsValidPartyName:
    def test_organization_name(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _is_valid_party_name

        assert _is_valid_party_name("佛山市升平百货有限公司") is True

    def test_person_name(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _is_valid_party_name

        assert _is_valid_party_name("张三") is True

    def test_bank(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _is_valid_party_name

        assert _is_valid_party_name("中国银行") is True

    def test_short_cause_keyword(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _is_valid_party_name

        assert _is_valid_party_name("纠纷") is False

    def test_single_char(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _is_valid_party_name

        assert _is_valid_party_name("张") is False

    def test_empty(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _is_valid_party_name

        assert _is_valid_party_name("") is False

    def test_long_name_without_cause_suffix(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _is_valid_party_name

        assert _is_valid_party_name("国家税务总局海南省税务局某某分局") is True

    def test_long_name_with_cause_suffix(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _is_valid_party_name

        assert _is_valid_party_name("某某纠纷") is False  # short and contains keyword

    def test_hospital(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _is_valid_party_name

        assert _is_valid_party_name("佛山市第一人民医院") is True

    def test_school(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _is_valid_party_name

        assert _is_valid_party_name("北京大学") is True


class TestSplitByComma:
    def test_half_width(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _split_by_comma

        assert _split_by_comma("a,b,c") == ["a", "b", "c"]

    def test_full_width(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _split_by_comma

        assert _split_by_comma("a，b，c") == ["a", "b", "c"]

    def test_mixed(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _split_by_comma

        assert _split_by_comma("a,b，c") == ["a", "b", "c"]

    def test_empty(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _split_by_comma

        assert _split_by_comma("") == [""]


class TestExtractNameFromSegment:
    def test_valid_name_direct(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _extract_name_from_segment

        result = _extract_name_from_segment("佛山市仲满金属材料有限公司")
        assert "佛山市仲满金属材料有限公司" in result

    def test_person_with_cause(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _extract_name_from_segment

        result = _extract_name_from_segment("汪达买卖合同纠纷")
        assert "汪达" in result

    def test_recovery_dispute(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _extract_name_from_segment

        result = _extract_name_from_segment("石莹追偿权纠纷")
        assert "石莹" in result

    def test_empty_segment(self):
        from apps.message_hub.services.court.court_schedule_fetcher import _extract_name_from_segment

        result = _extract_name_from_segment("")
        assert result == []


class TestParsedHearing:
    def test_frozen_dataclass(self):
        from apps.message_hub.services.court.court_schedule_fetcher import ParsedHearing

        hearing = ParsedHearing(
            source_id="123",
            content="开庭",
            due_at=datetime(2024, 6, 15, 10, 0),
            case_id=1,
            match_strategy="exact",
        )
        assert hearing.source_id == "123"
        assert hearing.match_strategy == "exact"
        with pytest.raises(AttributeError):
            hearing.source_id = "456"
