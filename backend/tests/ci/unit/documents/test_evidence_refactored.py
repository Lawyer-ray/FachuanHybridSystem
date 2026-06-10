"""Tests for refactored pure functions from documents/services/evidence/."""

from __future__ import annotations

import pytest

from apps.documents.services.evidence.evidence_list_placeholder_service import (
    LEGAL_STATUS_DISPLAY,
    LEGAL_STATUS_ORDER,
    EvidenceListPlaceholderService,
)


class TestLegalStatusDisplay:
    """Tests for LEGAL_STATUS_DISPLAY mapping."""

    def test_plaintiff_display(self):
        assert LEGAL_STATUS_DISPLAY["plaintiff"] == "原告"

    def test_defendant_display(self):
        assert LEGAL_STATUS_DISPLAY["defendant"] == "被告"

    def test_third_display(self):
        assert LEGAL_STATUS_DISPLAY["third"] == "第三人"

    def test_applicant_display(self):
        assert LEGAL_STATUS_DISPLAY["applicant"] == "申请人"

    def test_respondent_display(self):
        assert LEGAL_STATUS_DISPLAY["respondent"] == "被申请人"

    def test_all_statuses_have_display(self):
        for status in LEGAL_STATUS_ORDER:
            assert status in LEGAL_STATUS_DISPLAY


class TestFormatChineseDate:
    """Tests for _format_chinese_date pure function."""

    def setup_method(self):
        self.service = EvidenceListPlaceholderService()

    def test_valid_date(self):
        assert self.service._format_chinese_date("2026-01-15") == "2026年01月15日"

    def test_empty_string(self):
        assert self.service._format_chinese_date("") == ""

    def test_invalid_format(self):
        assert self.service._format_chinese_date("invalid") == "invalid"

    def test_date_with_spaces(self):
        assert self.service._format_chinese_date("  ") == "  "


class TestGroupPartiesByStatus:
    """Tests for _group_parties_by_status pure function."""

    def setup_method(self):
        self.service = EvidenceListPlaceholderService()

    def test_empty_parties(self):
        assert self.service._group_parties_by_status([]) == {}

    def test_single_party(self):
        parties = [{"legal_status": "plaintiff", "client_name": "Alice"}]
        result = self.service._group_parties_by_status(parties)
        assert result == {"plaintiff": ["Alice"]}

    def test_multiple_parties_same_status(self):
        parties = [
            {"legal_status": "plaintiff", "client_name": "Alice"},
            {"legal_status": "plaintiff", "client_name": "Bob"},
        ]
        result = self.service._group_parties_by_status(parties)
        assert result == {"plaintiff": ["Alice", "Bob"]}

    def test_multiple_statuses(self):
        parties = [
            {"legal_status": "plaintiff", "client_name": "Alice"},
            {"legal_status": "defendant", "client_name": "Charlie"},
        ]
        result = self.service._group_parties_by_status(parties)
        assert "plaintiff" in result
        assert "defendant" in result

    def test_party_without_status(self):
        parties = [{"client_name": "Alice"}]
        result = self.service._group_parties_by_status(parties)
        assert result == {}

    def test_party_without_name(self):
        parties = [{"legal_status": "plaintiff"}]
        result = self.service._group_parties_by_status(parties)
        assert result == {}

    def test_name_field_fallback(self):
        parties = [{"legal_status": "plaintiff", "name": "Alice"}]
        result = self.service._group_parties_by_status(parties)
        assert result == {"plaintiff": ["Alice"]}


class TestFormatOrderedGroups:
    """Tests for _format_ordered_groups pure function."""

    def setup_method(self):
        self.service = EvidenceListPlaceholderService()

    def test_empty_groups(self):
        assert self.service._format_ordered_groups({}) == []

    def test_single_group(self):
        groups = {"plaintiff": ["Alice"]}
        result = self.service._format_ordered_groups(groups)
        assert result == ["原告:Alice"]

    def test_multiple_parties_in_group(self):
        groups = {"plaintiff": ["Alice", "Bob"]}
        result = self.service._format_ordered_groups(groups)
        assert result == ["原告:Alice、Bob"]

    def test_ordering_follows_legal_status_order(self):
        groups = {"defendant": ["Charlie"], "plaintiff": ["Alice"]}
        result = self.service._format_ordered_groups(groups)
        assert result[0].startswith("原告")
        assert result[1].startswith("被告")

    def test_unknown_status_included(self):
        groups = {"unknown_status": ["Unknown"]}
        result = self.service._format_ordered_groups(groups)
        assert len(result) == 1
        assert "Unknown" in result[0]


class TestGetEvidenceListName:
    """Tests for get_evidence_list_name pure function."""

    def setup_method(self):
        self.service = EvidenceListPlaceholderService()

    def test_no_our_parties(self):
        class MockEvidenceList:
            title = "证据清单一"

        case_data = {"case_parties": []}
        assert self.service.get_evidence_list_name(MockEvidenceList(), case_data) == "证据清单一"

    def test_with_our_parties(self):
        class MockEvidenceList:
            title = "证据清单一"

        case_data = {
            "case_parties": [
                {"legal_status": "plaintiff", "is_our_client": True, "client_name": "Alice"},
            ]
        }
        result = self.service.get_evidence_list_name(MockEvidenceList(), case_data)
        assert result == "证据清单一(原告)"

    def test_multiple_statuses(self):
        class MockEvidenceList:
            title = "证据清单一"

        case_data = {
            "case_parties": [
                {"legal_status": "plaintiff", "is_our_client": True, "client_name": "Alice"},
                {"legal_status": "applicant", "is_our_client": True, "client_name": "Bob"},
            ]
        }
        result = self.service.get_evidence_list_name(MockEvidenceList(), case_data)
        assert "原告" in result
        assert "申请人" in result


class TestGetSignatureInfo:
    """Tests for get_signature_info pure function."""

    def setup_method(self):
        self.service = EvidenceListPlaceholderService()

    def test_no_our_parties(self):
        case_data = {"case_parties": []}
        assert self.service.get_signature_info(case_data) == ""

    def test_legal_person(self):
        case_data = {
            "case_parties": [
                {
                    "legal_status": "plaintiff",
                    "is_our_client": True,
                    "client_name": "公司A",
                    "client_type": "legal",
                    "legal_representative": "张三",
                },
            ],
            "specified_date": "2026-01-15",
        }
        result = self.service.get_signature_info(case_data)
        assert "原告(盖章):公司A" in result
        assert "法定代表人(签名):张三" in result
        assert "日期:2026年01月15日" in result

    def test_natural_person(self):
        case_data = {
            "case_parties": [
                {
                    "legal_status": "plaintiff",
                    "is_our_client": True,
                    "client_name": "张三",
                    "client_type": "individual",
                },
            ],
            "specified_date": "2026-01-15",
        }
        result = self.service.get_signature_info(case_data)
        assert "原告(签名+指模):张三" in result
        assert "日期:2026年01月15日" in result
