"""Tests for archive placeholder service.

Covers all static methods, the RichText helper class, and the main generate()
entry point of ArchivePlaceholderService.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _ArchiveMaterialsRichText
# ---------------------------------------------------------------------------
class TestArchiveMaterialsRichText:
    """Tests for the _ArchiveMaterialsRichText helper class."""

    def test_empty(self) -> None:
        from apps.documents.services.placeholders.archive import _ArchiveMaterialsRichText

        rt = _ArchiveMaterialsRichText()
        assert rt.plain_text == ""
        assert str(rt) == ""

    def test_add_single_line(self) -> None:
        from apps.documents.services.placeholders.archive import _ArchiveMaterialsRichText

        rt = _ArchiveMaterialsRichText()
        rt.add("hello")
        assert rt.plain_text == "hello"

    def test_add_multiple_lines(self) -> None:
        from apps.documents.services.placeholders.archive import _ArchiveMaterialsRichText

        rt = _ArchiveMaterialsRichText()
        rt.add("line1")
        rt.add("line2")
        assert rt.plain_text == "line1line2"

    def test_add_break(self) -> None:
        from apps.documents.services.placeholders.archive import _ArchiveMaterialsRichText

        rt = _ArchiveMaterialsRichText()
        rt.add("line1")
        rt.add_break()
        rt.add("line2")
        assert rt.plain_text == "line1\nline2"

    def test_to_listing(self) -> None:
        from apps.documents.services.placeholders.archive import _ArchiveMaterialsRichText

        rt = _ArchiveMaterialsRichText()
        rt.add("line1")
        rt.add_break()
        rt.add("line2")
        listing = rt.to_listing()
        # Listing receives plain_text
        assert listing is not None

    def test_str_returns_plain_text(self) -> None:
        from apps.documents.services.placeholders.archive import _ArchiveMaterialsRichText

        rt = _ArchiveMaterialsRichText()
        rt.add("abc")
        assert str(rt) == "abc"


# ---------------------------------------------------------------------------
# unwrap_archive_rich_text
# ---------------------------------------------------------------------------
class TestUnwrapArchiveRichText:
    """Tests for the unwrap_archive_rich_text helper."""

    def test_no_rich_text(self) -> None:
        from apps.documents.services.placeholders.archive import unwrap_archive_rich_text

        ctx = {"a": "plain", "b": 123}
        result = unwrap_archive_rich_text(ctx)
        assert result == {"a": "plain", "b": 123}

    def test_replaces_rich_text_with_listing(self) -> None:
        from apps.documents.services.placeholders.archive import (
            _ArchiveMaterialsRichText,
            unwrap_archive_rich_text,
        )

        rt = _ArchiveMaterialsRichText()
        rt.add("item1")
        ctx = {"materials": rt, "other": "keep"}
        result = unwrap_archive_rich_text(ctx)
        # materials should now be a Listing instance
        assert result["other"] == "keep"
        assert result["materials"] is not rt
        assert hasattr(result["materials"], "plain_text") is False  # Listing has no plain_text


# ---------------------------------------------------------------------------
# _format_chinese_date
# ---------------------------------------------------------------------------
class TestFormatChineseDate:
    def test_standard_date(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        result = ArchivePlaceholderService._format_chinese_date(date(2026, 4, 9))
        assert result == "2026年04月09日"

    def test_jan_first(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        result = ArchivePlaceholderService._format_chinese_date(date(2025, 1, 1))
        assert result == "2025年01月01日"

    def test_dec_31(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        result = ArchivePlaceholderService._format_chinese_date(date(2024, 12, 31))
        assert result == "2024年12月31日"


# ---------------------------------------------------------------------------
# _get_contract_name
# ---------------------------------------------------------------------------
class TestGetContractName:
    def test_with_name(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.name = "Test Contract"
        assert ArchivePlaceholderService._get_contract_name(contract) == "Test Contract"

    def test_with_none_name(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.name = None
        assert ArchivePlaceholderService._get_contract_name(contract) == ""

    def test_with_empty_name(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.name = ""
        assert ArchivePlaceholderService._get_contract_name(contract) == ""

    def test_no_name_attr(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock(spec=[])
        assert ArchivePlaceholderService._get_contract_name(contract) == ""


# ---------------------------------------------------------------------------
# _get_contract_type
# ---------------------------------------------------------------------------
class TestGetContractType:
    def test_display_name_success(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.get_case_type_display.return_value = "民商事"
        assert ArchivePlaceholderService._get_contract_type(contract) == "民商事"

    def test_display_name_returns_none(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.get_case_type_display.return_value = None
        contract.case_type = ""
        assert ArchivePlaceholderService._get_contract_type(contract) == ""

    def test_display_name_raises_exception(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.get_case_type_display.side_effect = AttributeError("no such method")
        contract.case_type = "CRIMINAL"
        assert ArchivePlaceholderService._get_contract_type(contract) == "CRIMINAL"

    def test_display_name_raises_exception_case_type_none(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.get_case_type_display.side_effect = AttributeError("no such method")
        contract.case_type = None
        assert ArchivePlaceholderService._get_contract_type(contract) == ""


# ---------------------------------------------------------------------------
# _get_our_party_names
# ---------------------------------------------------------------------------
class TestGetOurPartyNames:
    def test_success_with_principal_parties(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        party1 = MagicMock(role="PRINCIPAL")
        party1.client.name = "Client A"
        party2 = MagicMock(role="OPPOSING")
        party2.client.name = "Opposing"
        party3 = MagicMock(role="PRINCIPAL")
        party3.client.name = "Client B"

        contract = MagicMock()
        contract.contract_parties.select_related.return_value.all.return_value = [party1, party2, party3]

        result = ArchivePlaceholderService._get_our_party_names(contract)
        assert "Client A" in result
        assert "Client B" in result
        assert "Opposing" not in result

    def test_no_principal_parties(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        party1 = MagicMock(role="OPPOSING")
        party1.client.name = "Opposing"
        contract = MagicMock()
        contract.contract_parties.select_related.return_value.all.return_value = [party1]

        result = ArchivePlaceholderService._get_our_party_names(contract)
        assert result == ""

    def test_exception_fetching_parties(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.id = 42
        contract.contract_parties.select_related.side_effect = Exception("db error")
        result = ArchivePlaceholderService._get_our_party_names(contract)
        assert result == ""

    def test_deduplication(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        party1 = MagicMock(role="PRINCIPAL")
        party1.client.name = "Same"
        party2 = MagicMock(role="PRINCIPAL")
        party2.client.name = "Same"

        contract = MagicMock()
        contract.contract_parties.select_related.return_value.all.return_value = [party1, party2]

        result = ArchivePlaceholderService._get_our_party_names(contract)
        assert result == "Same"

    def test_party_with_no_client(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        party = MagicMock(role="PRINCIPAL")
        party.client = None

        contract = MagicMock()
        contract.contract_parties.select_related.return_value.all.return_value = [party]

        result = ArchivePlaceholderService._get_our_party_names(contract)
        assert result == ""

    def test_empty_name_filtered(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        party = MagicMock(role="PRINCIPAL")
        party.client.name = "   "  # whitespace only

        contract = MagicMock()
        contract.contract_parties.select_related.return_value.all.return_value = [party]

        result = ArchivePlaceholderService._get_our_party_names(contract)
        assert result == ""


# ---------------------------------------------------------------------------
# _get_opposing_party_names
# ---------------------------------------------------------------------------
class TestGetOpposingPartyNames:
    def test_success_with_opposing_parties(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        party1 = MagicMock(role="OPPOSING")
        party1.client.name = "Opposing A"
        party2 = MagicMock(role="PRINCIPAL")
        party2.client.name = "Principal"

        contract = MagicMock()
        contract.contract_parties.select_related.return_value.all.return_value = [party1, party2]

        result = ArchivePlaceholderService._get_opposing_party_names(contract)
        assert "Opposing A" in result
        assert "Principal" not in result

    def test_no_opposing_parties(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.contract_parties.select_related.return_value.all.return_value = []

        result = ArchivePlaceholderService._get_opposing_party_names(contract)
        assert result == ""

    def test_exception_fetching_parties(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.id = 10
        contract.contract_parties.select_related.side_effect = RuntimeError("timeout")

        result = ArchivePlaceholderService._get_opposing_party_names(contract)
        assert result == ""

    def test_deduplication(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        party1 = MagicMock(role="OPPOSING")
        party1.client.name = "Dup"
        party2 = MagicMock(role="OPPOSING")
        party2.client.name = "Dup"

        contract = MagicMock()
        contract.contract_parties.select_related.return_value.all.return_value = [party1, party2]

        result = ArchivePlaceholderService._get_opposing_party_names(contract)
        assert result == "Dup"

    def test_opposing_with_no_client(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        party = MagicMock(role="OPPOSING")
        party.client = None

        contract = MagicMock()
        contract.contract_parties.select_related.return_value.all.return_value = [party]

        result = ArchivePlaceholderService._get_opposing_party_names(contract)
        assert result == ""


# ---------------------------------------------------------------------------
# _get_oa_case_number
# ---------------------------------------------------------------------------
class TestGetOaCaseNumber:
    def test_with_number(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.law_firm_oa_case_number = "2026GZM0001"
        assert ArchivePlaceholderService._get_oa_case_number(contract) == "2026GZM0001"

    def test_with_none(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.law_firm_oa_case_number = None
        assert ArchivePlaceholderService._get_oa_case_number(contract) == ""

    def test_no_attr(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock(spec=[])
        assert ArchivePlaceholderService._get_oa_case_number(contract) == ""


# ---------------------------------------------------------------------------
# _get_lead_lawyer_name_from_contract
# ---------------------------------------------------------------------------
class TestGetLeadLawyerNameFromContract:
    def test_primary_assignment_found(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        lawyer = MagicMock()
        lawyer.real_name = "张律师"
        assignment = MagicMock()
        assignment.lawyer = lawyer

        contract = MagicMock()
        contract.id = 1
        chain = contract.assignments.select_related.return_value
        chain.filter.return_value.first.return_value = assignment

        result = ArchivePlaceholderService._get_lead_lawyer_name_from_contract(contract)
        assert result == "张律师"

    def test_no_primary_fallback_to_first(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        lawyer = MagicMock()
        lawyer.real_name = "李律师"
        assignment = MagicMock()
        assignment.lawyer = lawyer

        contract = MagicMock()
        contract.id = 2
        chain = contract.assignments.select_related.return_value
        chain.filter.return_value.first.return_value = None  # no primary
        chain.first.return_value = assignment  # fallback first

        result = ArchivePlaceholderService._get_lead_lawyer_name_from_contract(contract)
        assert result == "李律师"

    def test_no_assignments_at_all(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.id = 3
        chain = contract.assignments.select_related.return_value
        chain.filter.return_value.first.return_value = None
        chain.first.return_value = None

        result = ArchivePlaceholderService._get_lead_lawyer_name_from_contract(contract)
        assert result == ""

    def test_filter_raises_exception(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.id = 4
        chain = contract.assignments.select_related.return_value
        chain.filter.side_effect = Exception("db error")
        chain.first.return_value = None

        result = ArchivePlaceholderService._get_lead_lawyer_name_from_contract(contract)
        assert result == ""

    def test_fallback_also_raises(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.id = 5
        chain = contract.assignments.select_related.return_value
        chain.filter.side_effect = Exception("db error")
        chain.first.side_effect = Exception("db error")

        result = ArchivePlaceholderService._get_lead_lawyer_name_from_contract(contract)
        assert result == ""

    def test_assignment_with_no_lawyer(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        assignment = MagicMock()
        assignment.lawyer = None

        contract = MagicMock()
        contract.id = 6
        chain = contract.assignments.select_related.return_value
        chain.filter.return_value.first.return_value = assignment

        result = ArchivePlaceholderService._get_lead_lawyer_name_from_contract(contract)
        assert result == ""

    def test_lawyer_with_no_real_name_uses_username(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        lawyer = MagicMock()
        lawyer.real_name = None
        lawyer.username = "zhang"
        assignment = MagicMock()
        assignment.lawyer = lawyer

        contract = MagicMock()
        contract.id = 7
        chain = contract.assignments.select_related.return_value
        chain.filter.return_value.first.return_value = assignment

        result = ArchivePlaceholderService._get_lead_lawyer_name_from_contract(contract)
        assert result == "zhang"


# ---------------------------------------------------------------------------
# _get_lead_lawyer_name (from case)
# ---------------------------------------------------------------------------
class TestGetLeadLawyerName:
    def test_primary_assignment_found(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        lawyer = MagicMock()
        lawyer.real_name = "王律师"
        assignment = MagicMock()
        assignment.lawyer = lawyer

        case = MagicMock()
        case.id = 1
        chain = case.assignments.select_related.return_value
        chain.filter.return_value.first.return_value = assignment

        result = ArchivePlaceholderService._get_lead_lawyer_name(case)
        assert result == "王律师"

    def test_no_primary_fallback_role_lead(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        lawyer = MagicMock()
        lawyer.real_name = "赵律师"
        assignment = MagicMock()
        assignment.lawyer = lawyer

        case = MagicMock()
        case.id = 2

        # The role="lead" fallback only runs if filter(is_primary=True) RAISES.
        # We make the first filter call raise, so the code tries filter(role="lead").
        select_related_obj = case.assignments.select_related.return_value

        def mock_filter(**kwargs):
            if "is_primary" in kwargs:
                raise AttributeError("is_primary not supported")
            mock_result = MagicMock()
            mock_result.first.return_value = assignment
            return mock_result

        select_related_obj.filter.side_effect = mock_filter

        result = ArchivePlaceholderService._get_lead_lawyer_name(case)
        assert result == "赵律师"

    def test_no_primary_no_role_lead_fallback_first(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        lawyer = MagicMock()
        lawyer.real_name = "孙律师"
        assignment = MagicMock()
        assignment.lawyer = lawyer

        case = MagicMock()
        case.id = 3

        # First filter(is_primary=True) returns None normally.
        # Then code goes to if not assignment -> .first() returns assignment.
        def mock_filter(**kwargs):
            mock_result = MagicMock()
            mock_result.first.return_value = None
            return mock_result

        case.assignments.select_related.return_value.filter.side_effect = mock_filter
        case.assignments.select_related.return_value.first.return_value = assignment

        result = ArchivePlaceholderService._get_lead_lawyer_name(case)
        assert result == "孙律师"

    def test_no_assignments_at_all(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        case = MagicMock()
        case.id = 4

        def mock_filter(**kwargs):
            mock_result = MagicMock()
            mock_result.first.return_value = None
            return mock_result

        case.assignments.select_related.return_value.filter.side_effect = mock_filter
        case.assignments.select_related.return_value.first.return_value = None

        result = ArchivePlaceholderService._get_lead_lawyer_name(case)
        assert result == ""

    def test_filter_raises_all_fallbacks_fail(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        case = MagicMock()
        case.id = 5
        chain = case.assignments.select_related.return_value
        chain.filter.side_effect = Exception("db error")
        chain.first.side_effect = Exception("db error")

        result = ArchivePlaceholderService._get_lead_lawyer_name(case)
        assert result == ""

    def test_assignment_with_no_lawyer(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        assignment = MagicMock()
        assignment.lawyer = None

        case = MagicMock()
        case.id = 6

        def mock_filter(**kwargs):
            mock_result = MagicMock()
            mock_result.first.return_value = assignment
            return mock_result

        case.assignments.select_related.return_value.filter.side_effect = mock_filter

        result = ArchivePlaceholderService._get_lead_lawyer_name(case)
        assert result == ""

    def test_lawyer_with_no_real_name_uses_username(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        lawyer = MagicMock()
        lawyer.real_name = None
        lawyer.username = "wang"
        assignment = MagicMock()
        assignment.lawyer = lawyer

        case = MagicMock()
        case.id = 7

        def mock_filter(**kwargs):
            mock_result = MagicMock()
            mock_result.first.return_value = assignment
            return mock_result

        case.assignments.select_related.return_value.filter.side_effect = mock_filter

        result = ArchivePlaceholderService._get_lead_lawyer_name(case)
        assert result == "wang"


# ---------------------------------------------------------------------------
# _get_case_number
# ---------------------------------------------------------------------------
class TestGetCaseNumber:
    def test_active_case_numbers(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        cn1 = MagicMock(number="(2026)粤0101民初001号")
        cn2 = MagicMock(number="(2026)粤0101民初002号")
        case = MagicMock()
        case.id = 1
        case.case_numbers.filter.return_value = [cn1, cn2]

        result = ArchivePlaceholderService._get_case_number(case)
        assert "粤0101民初001号" in result
        assert "，" in result

    def test_no_active_fallback_to_all(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        cn1 = MagicMock(number="(2026)粤0202民初003号")
        case = MagicMock()
        case.id = 2
        case.case_numbers.filter.return_value = []
        case.case_numbers.all.return_value = [cn1]

        result = ArchivePlaceholderService._get_case_number(case)
        assert "粤0202民初003号" in result

    def test_empty_case_numbers(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        case = MagicMock()
        case.id = 3
        case.case_numbers.filter.return_value = []
        case.case_numbers.all.return_value = []

        result = ArchivePlaceholderService._get_case_number(case)
        assert result == ""

    def test_exception(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        case = MagicMock()
        case.id = 4
        case.case_numbers.filter.side_effect = Exception("db error")

        result = ArchivePlaceholderService._get_case_number(case)
        assert result == ""

    def test_case_number_with_none_number(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        cn = MagicMock()
        cn.number = None
        case = MagicMock()
        case.id = 5
        case.case_numbers.filter.return_value = [cn]

        result = ArchivePlaceholderService._get_case_number(case)
        assert result == ""


# ---------------------------------------------------------------------------
# _get_court_name
# ---------------------------------------------------------------------------
class TestGetCourtName:
    def test_single_authority(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        auth = MagicMock()
        auth.name = "某某区人民法院"
        case = MagicMock()
        case.id = 1
        case.supervising_authorities.filter.return_value = [auth]

        result = ArchivePlaceholderService._get_court_name(case)
        assert result == "某某区人民法院"

    def test_multiple_authorities_dedup(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        auth1 = MagicMock()
        auth1.name = "法院A"
        auth2 = MagicMock()
        auth2.name = "法院A"  # duplicate
        auth3 = MagicMock()
        auth3.name = "法院B"

        case = MagicMock()
        case.id = 2
        case.supervising_authorities.filter.return_value = [auth1, auth2, auth3]

        result = ArchivePlaceholderService._get_court_name(case)
        assert result == "法院A、法院B"

    def test_no_authorities(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        case = MagicMock()
        case.id = 3
        case.supervising_authorities.filter.return_value = []

        result = ArchivePlaceholderService._get_court_name(case)
        assert result == ""

    def test_empty_name_filtered(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        auth = MagicMock()
        auth.name = "   "
        case = MagicMock()
        case.id = 4
        case.supervising_authorities.filter.return_value = [auth]

        result = ArchivePlaceholderService._get_court_name(case)
        assert result == ""

    def test_exception(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        case = MagicMock()
        case.id = 5
        case.supervising_authorities.filter.side_effect = Exception("db error")

        result = ArchivePlaceholderService._get_court_name(case)
        assert result == ""


# ---------------------------------------------------------------------------
# _get_case_stage
# ---------------------------------------------------------------------------
class TestGetCaseStage:
    def test_with_stage(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        case = MagicMock()
        case.current_stage = "first_trial"
        case.get_current_stage_display.return_value = "一审"
        result = ArchivePlaceholderService._get_case_stage(case)
        assert result == "一审"

    def test_no_stage(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        case = MagicMock()
        case.current_stage = None
        result = ArchivePlaceholderService._get_case_stage(case)
        assert result == ""

    def test_display_raises(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        case = MagicMock()
        case.current_stage = "first_trial"
        case.get_current_stage_display.side_effect = Exception("no display")
        result = ArchivePlaceholderService._get_case_stage(case)
        assert result == "first_trial"

    def test_display_returns_none(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        case = MagicMock()
        case.current_stage = "first_trial"
        case.get_current_stage_display.return_value = None
        result = ArchivePlaceholderService._get_case_stage(case)
        assert result == ""


# ---------------------------------------------------------------------------
# _get_trial_result
# ---------------------------------------------------------------------------
class TestGetTrialResult:
    def test_with_active_results(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        cn1 = MagicMock(document_content="判决主文一")
        cn2 = MagicMock(document_content="判决主文二")
        case = MagicMock()
        case.id = 1
        case.case_numbers.filter.return_value = [cn1, cn2]

        result = ArchivePlaceholderService._get_trial_result(case)
        assert "判决主文一" in result
        assert "判决主文二" in result

    def test_no_active_fallback_to_all(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        cn = MagicMock(document_content="全部案号内容")
        case = MagicMock()
        case.id = 2
        case.case_numbers.filter.return_value = []
        case.case_numbers.all.return_value = [cn]

        result = ArchivePlaceholderService._get_trial_result(case)
        assert "全部案号内容" in result

    def test_empty_results(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        case = MagicMock()
        case.id = 3
        case.case_numbers.filter.return_value = []
        case.case_numbers.all.return_value = []

        result = ArchivePlaceholderService._get_trial_result(case)
        assert result == ""

    def test_exception(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        case = MagicMock()
        case.id = 4
        case.case_numbers.filter.side_effect = Exception("db error")

        result = ArchivePlaceholderService._get_trial_result(case)
        assert result == ""

    def test_empty_content_filtered(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        cn1 = MagicMock(document_content="")
        cn2 = MagicMock(document_content="   ")
        cn3 = MagicMock(document_content="有内容")
        case = MagicMock()
        case.id = 5
        case.case_numbers.filter.return_value = [cn1, cn2, cn3]

        result = ArchivePlaceholderService._get_trial_result(case)
        assert result == "有内容"

    def test_none_content_treated_as_empty(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        cn = MagicMock()
        cn.document_content = None
        case = MagicMock()
        case.id = 6
        case.case_numbers.filter.return_value = [cn]

        result = ArchivePlaceholderService._get_trial_result(case)
        assert result == ""


# ---------------------------------------------------------------------------
# _get_case_summary_content
# ---------------------------------------------------------------------------
class TestGetCaseSummaryContent:
    def test_with_trial_result(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        result = ArchivePlaceholderService._get_case_summary_content(
            case=None,
            contract=None,
            already_generated={"案件审理结果": "判决内容"},
        )
        assert result == "判决内容"

    def test_trial_result_is_slash(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        result = ArchivePlaceholderService._get_case_summary_content(
            case=None,
            contract=None,
            already_generated={"案件审理结果": "/"},
        )
        # "/" is treated as empty, so falls through to contract name logic
        assert result == ""

    def test_no_trial_result_with_contract_name(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        result = ArchivePlaceholderService._get_case_summary_content(
            case=None,
            contract=None,
            already_generated={
                "案件审理结果": "",
                "合同名称": "合同纠纷",
                "合同我方当事人名称": "原告公司",
            },
        )
        assert "合同纠纷" in result
        assert "原告公司" in result

    def test_no_trial_result_contract_name_slash(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        result = ArchivePlaceholderService._get_case_summary_content(
            case=None,
            contract=None,
            already_generated={
                "案件审理结果": "",
                "合同名称": "/",
                "合同我方当事人名称": "",
            },
        )
        assert result == ""

    def test_no_trial_result_party_names_slash(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        result = ArchivePlaceholderService._get_case_summary_content(
            case=None,
            contract=None,
            already_generated={
                "案件审理结果": "",
                "合同名称": "某某合同",
                "合同我方当事人名称": "/",
            },
        )
        assert "某某合同" in result
        assert "委托人" in result

    def test_no_trial_result_no_contract_name(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        result = ArchivePlaceholderService._get_case_summary_content(
            case=None,
            contract=None,
            already_generated={},
        )
        assert result == ""

    def test_trial_result_whitespace_only(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        result = ArchivePlaceholderService._get_case_summary_content(
            case=None,
            contract=None,
            already_generated={"案件审理结果": "   "},
        )
        assert result == ""

    def test_trial_result_no_party_names(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        result = ArchivePlaceholderService._get_case_summary_content(
            case=None,
            contract=None,
            already_generated={
                "合同名称": "合同名称",
                "合同我方当事人名称": "",
            },
        )
        assert "委托人" in result


# ---------------------------------------------------------------------------
# _is_auto_generated_log
# ---------------------------------------------------------------------------
class TestIsAutoGeneratedLog:
    def test_exact_match(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        log = MagicMock()
        log.content = "自动捕获材料"
        assert ArchivePlaceholderService._is_auto_generated_log(log) is True

    def test_prefix_match_cn(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        log = MagicMock()
        log.content = "文书送达自动下载: some file"
        assert ArchivePlaceholderService._is_auto_generated_log(log) is True

    def test_prefix_match_full_width(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        log = MagicMock()
        log.content = "文书送达自动下载：some file"
        assert ArchivePlaceholderService._is_auto_generated_log(log) is True

    def test_not_auto_generated(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        log = MagicMock()
        log.content = "开庭审理"
        assert ArchivePlaceholderService._is_auto_generated_log(log) is False

    def test_empty_content(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        log = MagicMock()
        log.content = ""
        assert ArchivePlaceholderService._is_auto_generated_log(log) is False

    def test_none_content(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        log = MagicMock()
        log.content = None
        assert ArchivePlaceholderService._is_auto_generated_log(log) is False


# ---------------------------------------------------------------------------
# _get_lawyer_work_log_content
# ---------------------------------------------------------------------------
class TestGetLawyerWorkLogContent:
    def test_basic_logs(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        log1 = MagicMock()
        log1.content = "签订委托合同"
        log1.created_at = MagicMock()
        log1.created_at.year = 2026
        log1.created_at.month = 3
        log1.created_at.day = 10

        log2 = MagicMock()
        log2.content = "一审开庭"
        log2.created_at = MagicMock()
        log2.created_at.year = 2026
        log2.created_at.month = 4
        log2.created_at.day = 15

        case = MagicMock()
        case.id = 1
        case.logs.select_related.return_value.order_by.return_value = [log1, log2]

        result = ArchivePlaceholderService._get_lawyer_work_log_content(case)
        assert "2026年3月10日，签订委托合同" in result
        assert "2026年4月15日，一审开庭" in result

    def test_auto_generated_logs_excluded(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        log1 = MagicMock()
        log1.content = "文书送达自动下载: test.pdf"
        log1.created_at = MagicMock()

        log2 = MagicMock()
        log2.content = "开庭"
        log2.created_at = MagicMock()
        log2.created_at.year = 2026
        log2.created_at.month = 1
        log2.created_at.day = 1

        case = MagicMock()
        case.id = 2
        case.logs.select_related.return_value.order_by.return_value = [log1, log2]

        result = ArchivePlaceholderService._get_lawyer_work_log_content(case)
        assert "文书送达" not in result
        assert "开庭" in result

    def test_empty_content_excluded(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        log1 = MagicMock()
        log1.content = ""
        log1.created_at = MagicMock()

        case = MagicMock()
        case.id = 3
        case.logs.select_related.return_value.order_by.return_value = [log1]

        result = ArchivePlaceholderService._get_lawyer_work_log_content(case)
        assert result == ""

    def test_no_created_at(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        log = MagicMock()
        log.content = "内容"
        log.created_at = None

        case = MagicMock()
        case.id = 4
        case.logs.select_related.return_value.order_by.return_value = [log]

        result = ArchivePlaceholderService._get_lawyer_work_log_content(case)
        assert "未知日期" in result

    def test_exception_fetching_logs(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        case = MagicMock()
        case.id = 5
        case.logs.select_related.side_effect = Exception("db error")

        result = ArchivePlaceholderService._get_lawyer_work_log_content(case)
        assert result == ""

    def test_all_auto_generated_returns_empty(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        log1 = MagicMock()
        log1.content = "自动捕获材料"

        case = MagicMock()
        case.id = 6
        case.logs.select_related.return_value.order_by.return_value = [log1]

        result = ArchivePlaceholderService._get_lawyer_work_log_content(case)
        assert result == ""


# ---------------------------------------------------------------------------
# _get_opposing_party_names_from_case
# ---------------------------------------------------------------------------
class TestGetOpposingPartyNamesFromCase:
    def test_basic(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        p1 = MagicMock()
        p1.client.name = "对方A"
        p1.client.is_our_client = False

        p2 = MagicMock()
        p2.client.name = "我方B"
        p2.client.is_our_client = True

        case = MagicMock()
        case.id = 1
        case.parties.select_related.return_value.all.return_value = [p1, p2]

        result = ArchivePlaceholderService._get_opposing_party_names_from_case(case)
        assert "对方A" in result
        assert "我方B" not in result

    def test_no_parties(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        case = MagicMock()
        case.id = 2
        case.parties.select_related.return_value.all.return_value = []

        result = ArchivePlaceholderService._get_opposing_party_names_from_case(case)
        assert result == ""

    def test_exception(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        case = MagicMock()
        case.id = 3
        case.parties.select_related.side_effect = TypeError("bad query")

        result = ArchivePlaceholderService._get_opposing_party_names_from_case(case)
        assert result == ""

    def test_no_client(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        p = MagicMock()
        p.client = None

        case = MagicMock()
        case.id = 4
        case.parties.select_related.return_value.all.return_value = [p]

        result = ArchivePlaceholderService._get_opposing_party_names_from_case(case)
        assert result == ""

    def test_dedup(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        p1 = MagicMock()
        p1.client.name = "对方"
        p1.client.is_our_client = False
        p2 = MagicMock()
        p2.client.name = "对方"
        p2.client.is_our_client = False

        case = MagicMock()
        case.id = 5
        case.parties.select_related.return_value.all.return_value = [p1, p2]

        result = ArchivePlaceholderService._get_opposing_party_names_from_case(case)
        assert result == "对方"


# ---------------------------------------------------------------------------
# _get_archive_materials_list
# ---------------------------------------------------------------------------
class TestGetArchiveMaterialsList:
    def test_basic_items(self) -> None:
        """Test directly by patching the ArchiveChecklistService import inside the method."""
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        with patch(
            "apps.contracts.services.archive.ArchiveChecklistService"
        ) as MockService:
            instance = MockService.return_value
            instance.get_checklist_with_status.return_value = {
                "items": [
                    {"code": "doc_1", "name": "委托代理合同", "completed": True, "material_ids": []},
                    {"code": "doc_2", "name": "风险告知书", "completed": True, "material_ids": []},
                    {"code": "nl_1", "name": "案卷封面", "completed": True, "material_ids": []},
                    {"code": "doc_3", "name": "未完成项", "completed": False, "material_ids": []},
                ]
            }

            contract = MagicMock()
            contract.id = 1

            # Call the real method by importing and calling it directly
            import apps.documents.services.placeholders.archive as archive_mod

            result = archive_mod.ArchivePlaceholderService._get_archive_materials_list(contract)
            assert "1.委托代理合同" in str(result)
            assert "2.风险告知书" in str(result)
            assert "案卷封面" not in str(result)
            assert "未完成项" not in str(result)

    def test_empty_items(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        with patch(
            "apps.contracts.services.archive.ArchiveChecklistService"
        ) as MockService:
            instance = MockService.return_value
            instance.get_checklist_with_status.return_value = {"items": []}

            contract = MagicMock()
            contract.id = 2

            result = ArchivePlaceholderService._get_archive_materials_list(contract)
            assert result == ""

    def test_skip_templates(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        with patch(
            "apps.contracts.services.archive.ArchiveChecklistService"
        ) as MockService:
            instance = MockService.return_value
            instance.get_checklist_with_status.return_value = {
                "items": [
                    {"code": "x_1", "template": "case_cover", "name": "封面", "completed": True, "material_ids": []},
                    {"code": "x_2", "template": "closing_archive_register", "name": "登记", "completed": True, "material_ids": []},
                    {"code": "x_3", "template": "inner_catalog", "name": "目录", "completed": True, "material_ids": []},
                    {"code": "x_4", "template": "other", "name": "材料A", "completed": True, "material_ids": []},
                ]
            }

            contract = MagicMock()
            contract.id = 3

            result = ArchivePlaceholderService._get_archive_materials_list(contract)
            assert "1.材料A" in str(result)


# ---------------------------------------------------------------------------
# _get_inner_catalog_items
# ---------------------------------------------------------------------------
class TestGetInnerCatalogItems:
    def test_basic_catalog(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        with patch(
            "apps.contracts.services.archive.ArchiveChecklistService"
        ) as MockService, patch.object(
            ArchivePlaceholderService, "_calculate_material_page_count", return_value=3
        ):
            instance = MockService.return_value
            instance.get_checklist_with_status.return_value = {
                "items": [
                    {"code": "doc_1", "name": "合同", "completed": True, "material_ids": [1]},
                    {"code": "doc_2", "name": "告知书", "completed": True, "material_ids": [2]},
                ]
            }

            contract = MagicMock()
            contract.id = 1

            result = ArchivePlaceholderService._get_inner_catalog_items(contract)
            assert len(result) == 2
            assert result[0]["序号"] == 1
            assert result[0]["材料名称"] == "合同"
            assert result[0]["页码"] == "1-3"
            assert result[1]["序号"] == 2
            assert result[1]["页码"] == "4-6"

    def test_empty_items(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        with patch(
            "apps.contracts.services.archive.ArchiveChecklistService"
        ) as MockService:
            instance = MockService.return_value
            instance.get_checklist_with_status.return_value = {"items": []}

            contract = MagicMock()
            contract.id = 2

            result = ArchivePlaceholderService._get_inner_catalog_items(contract)
            assert result == []

    def test_skip_items(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        with patch(
            "apps.contracts.services.archive.ArchiveChecklistService"
        ) as MockService, patch.object(
            ArchivePlaceholderService, "_calculate_material_page_count", return_value=1
        ):
            instance = MockService.return_value
            instance.get_checklist_with_status.return_value = {
                "items": [
                    {"code": "nl_1", "name": "封面", "completed": True, "material_ids": []},
                    {"code": "doc_1", "name": "材料A", "completed": True, "material_ids": []},
                    {"code": "doc_2", "name": "未完成", "completed": False, "material_ids": []},
                ]
            }

            contract = MagicMock()
            contract.id = 3

            result = ArchivePlaceholderService._get_inner_catalog_items(contract)
            assert len(result) == 1
            assert result[0]["材料名称"] == "材料A"

    def test_zero_page_count(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        with patch(
            "apps.contracts.services.archive.ArchiveChecklistService"
        ) as MockService, patch.object(
            ArchivePlaceholderService, "_calculate_material_page_count", return_value=0
        ):
            instance = MockService.return_value
            instance.get_checklist_with_status.return_value = {
                "items": [
                    {"code": "doc_1", "name": "材料A", "completed": True, "material_ids": []},
                ]
            }

            contract = MagicMock()
            contract.id = 4

            result = ArchivePlaceholderService._get_inner_catalog_items(contract)
            assert result[0]["页码"] == "-"

    def test_single_page(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        with patch(
            "apps.contracts.services.archive.ArchiveChecklistService"
        ) as MockService, patch.object(
            ArchivePlaceholderService, "_calculate_material_page_count", return_value=1
        ):
            instance = MockService.return_value
            instance.get_checklist_with_status.return_value = {
                "items": [
                    {"code": "doc_1", "name": "材料A", "completed": True, "material_ids": []},
                ]
            }

            contract = MagicMock()
            contract.id = 5

            result = ArchivePlaceholderService._get_inner_catalog_items(contract)
            assert result[0]["页码"] == "1"


# ---------------------------------------------------------------------------
# _calculate_material_page_count
# ---------------------------------------------------------------------------
class TestCalculateMaterialPageCount:
    def test_with_material_ids(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        mat = MagicMock()
        mat.file_path = "/tmp/test.pdf"

        with patch(
            "apps.contracts.models.finalized_material.FinalizedMaterial.objects"
        ) as mock_objects, patch.object(
            ArchivePlaceholderService, "_get_file_page_count", return_value=5
        ):
            mock_objects.filter.return_value = [mat]

            contract = MagicMock()
            result = ArchivePlaceholderService._calculate_material_page_count(contract, "code_1", [1, 2])
            assert result == 5

    def test_without_material_ids_uses_code(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        mat = MagicMock()
        mat.file_path = "/tmp/test.pdf"

        with patch(
            "apps.contracts.models.finalized_material.FinalizedMaterial.objects"
        ) as mock_objects, patch.object(
            ArchivePlaceholderService, "_get_file_page_count", return_value=3
        ):
            mock_objects.filter.return_value = [mat]

            contract = MagicMock()
            result = ArchivePlaceholderService._calculate_material_page_count(contract, "archive_code", [])
            assert result == 3

    def test_no_materials(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        with patch(
            "apps.contracts.models.finalized_material.FinalizedMaterial.objects"
        ) as mock_objects:
            mock_objects.filter.return_value = []

            contract = MagicMock()
            result = ArchivePlaceholderService._calculate_material_page_count(contract, "code", [])
            assert result == 0

    def test_page_count_zero_defaults_to_1(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        mat = MagicMock()

        with patch(
            "apps.contracts.models.finalized_material.FinalizedMaterial.objects"
        ) as mock_objects, patch.object(
            ArchivePlaceholderService, "_get_file_page_count", return_value=0
        ):
            mock_objects.filter.return_value = [mat]

            contract = MagicMock()
            result = ArchivePlaceholderService._calculate_material_page_count(contract, "code", [])
            assert result == 1  # default 1 page when count is 0


# ---------------------------------------------------------------------------
# _get_file_page_count
# ---------------------------------------------------------------------------
class TestGetFilePageCount:
    def test_pdf_file(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        material = MagicMock()
        material.file_path = "/tmp/test.pdf"
        material.original_filename = "test.pdf"

        with patch("pathlib.Path.exists", return_value=True), patch(
            "pathlib.Path.is_absolute", return_value=True
        ), patch(
            "apps.documents.services.infrastructure.pdf_utils.get_pdf_page_count",
            return_value=10,
        ), patch(
            "builtins.open"
        ):
            result = ArchivePlaceholderService._get_file_page_count(material)
            assert result == 10

    def test_docx_file(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        material = MagicMock()
        material.file_path = "/tmp/test.docx"

        with patch("pathlib.Path.exists", return_value=True), patch(
            "pathlib.Path.is_absolute", return_value=True
        ):
            result = ArchivePlaceholderService._get_file_page_count(material)
            assert result == 1

    def test_other_file_type(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        material = MagicMock()
        material.file_path = "/tmp/test.txt"

        with patch("pathlib.Path.exists", return_value=True), patch(
            "pathlib.Path.is_absolute", return_value=True
        ):
            result = ArchivePlaceholderService._get_file_page_count(material)
            assert result == 1

    def test_file_not_found(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        material = MagicMock()
        material.file_path = "/tmp/nonexistent.pdf"

        with patch("pathlib.Path.exists", return_value=False), patch(
            "pathlib.Path.is_absolute", return_value=True
        ):
            result = ArchivePlaceholderService._get_file_page_count(material)
            assert result == 0

    def test_relative_path_resolved(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        material = MagicMock()
        material.file_path = "relative/path.pdf"

        with patch("pathlib.Path.exists", return_value=True), patch(
            "pathlib.Path.is_absolute", return_value=False
        ), patch(
            "apps.documents.services.infrastructure.pdf_utils.get_pdf_page_count",
            return_value=5,
        ), patch(
            "builtins.open"
        ):
            result = ArchivePlaceholderService._get_file_page_count(material)
            assert result == 5

    def test_pdf_exception(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        material = MagicMock()
        material.file_path = "/tmp/test.pdf"
        material.original_filename = "test.pdf"

        with patch("pathlib.Path.exists", return_value=True), patch(
            "pathlib.Path.is_absolute", return_value=True
        ), patch(
            "apps.documents.services.infrastructure.pdf_utils.get_pdf_page_count",
            side_effect=Exception("corrupt pdf"),
        ):
            result = ArchivePlaceholderService._get_file_page_count(material)
            assert result == 0


# ---------------------------------------------------------------------------
# _get_work_log_from_scan_session
# ---------------------------------------------------------------------------
class TestGetWorkLogFromScanSession:
    def test_basic_suggestions(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        session = MagicMock()
        session.result_payload = {
            "confirmed_work_log_suggestions": [
                {"date": "2024-09-11", "content": "签订合同"},
                {"date": "2024-10-05", "content": "开庭审理"},
            ]
        }

        with patch(
            "apps.contracts.models.ContractFolderScanSession.objects"
        ) as mock_objects:
            mock_objects.filter.return_value.order_by.return_value.first.return_value = session

            contract = MagicMock()
            contract.id = 1

            result = ArchivePlaceholderService._get_work_log_from_scan_session(contract)
            assert "2024年9月11日，签订合同" in result
            assert "2024年10月5日，开庭审理" in result

    def test_no_session(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        with patch(
            "apps.contracts.models.ContractFolderScanSession.objects"
        ) as mock_objects:
            mock_objects.filter.return_value.order_by.return_value.first.return_value = None

            contract = MagicMock()
            contract.id = 2

            result = ArchivePlaceholderService._get_work_log_from_scan_session(contract)
            assert result == ""

    def test_no_suggestions(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        session = MagicMock()
        session.result_payload = {"confirmed_work_log_suggestions": []}

        with patch(
            "apps.contracts.models.ContractFolderScanSession.objects"
        ) as mock_objects:
            mock_objects.filter.return_value.order_by.return_value.first.return_value = session

            contract = MagicMock()
            contract.id = 3

            result = ArchivePlaceholderService._get_work_log_from_scan_session(contract)
            assert result == ""

    def test_empty_content_skipped(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        session = MagicMock()
        session.result_payload = {
            "confirmed_work_log_suggestions": [
                {"date": "2024-09-11", "content": ""},
                {"date": "2024-10-05", "content": "开庭"},
            ]
        }

        with patch(
            "apps.contracts.models.ContractFolderScanSession.objects"
        ) as mock_objects:
            mock_objects.filter.return_value.order_by.return_value.first.return_value = session

            contract = MagicMock()
            contract.id = 4

            result = ArchivePlaceholderService._get_work_log_from_scan_session(contract)
            assert "开庭" in result
            # Only one line, no break
            assert "2024年10月5日，开庭" in result

    def test_no_date(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        session = MagicMock()
        session.result_payload = {
            "confirmed_work_log_suggestions": [
                {"date": "", "content": "开庭"},
            ]
        }

        with patch(
            "apps.contracts.models.ContractFolderScanSession.objects"
        ) as mock_objects:
            mock_objects.filter.return_value.order_by.return_value.first.return_value = session

            contract = MagicMock()
            contract.id = 5

            result = ArchivePlaceholderService._get_work_log_from_scan_session(contract)
            assert result == "开庭"

    def test_no_contract_id(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock(spec=[])  # no id attr

        result = ArchivePlaceholderService._get_work_log_from_scan_session(contract)
        assert result == ""

    def test_exception(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        contract = MagicMock()
        contract.id = 6

        with patch(
            "apps.contracts.models.ContractFolderScanSession.objects"
        ) as mock_objects:
            mock_objects.filter.side_effect = Exception("import error")

            result = ArchivePlaceholderService._get_work_log_from_scan_session(contract)
            assert result == ""

    def test_null_payload(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        session = MagicMock()
        session.result_payload = None

        with patch(
            "apps.contracts.models.ContractFolderScanSession.objects"
        ) as mock_objects:
            mock_objects.filter.return_value.order_by.return_value.first.return_value = session

            contract = MagicMock()
            contract.id = 7

            result = ArchivePlaceholderService._get_work_log_from_scan_session(contract)
            assert result == ""

    def test_all_empty_content(self) -> None:
        """All suggestions have empty content -> lines stays empty -> early return."""
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        session = MagicMock()
        session.result_payload = {
            "confirmed_work_log_suggestions": [
                {"date": "2024-09-11", "content": ""},
                {"date": "2024-10-05", "content": "   "},
            ]
        }

        with patch(
            "apps.contracts.models.ContractFolderScanSession.objects"
        ) as mock_objects:
            mock_objects.filter.return_value.order_by.return_value.first.return_value = session

            contract = MagicMock()
            contract.id = 8

            result = ArchivePlaceholderService._get_work_log_from_scan_session(contract)
            assert result == ""


# ---------------------------------------------------------------------------
# generate (main entry point)
# ---------------------------------------------------------------------------
class TestGenerate:
    def test_generate_with_both_case_and_contract(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        service = ArchivePlaceholderService()

        # Mock case
        lawyer = MagicMock()
        lawyer.real_name = "张律师"
        assignment = MagicMock()
        assignment.lawyer = lawyer
        case = MagicMock()
        case.id = 1
        case.assignments.select_related.return_value.filter.return_value.first.return_value = assignment
        case.case_numbers.filter.return_value = [MagicMock(number="(2026)粤01号")]
        case.supervising_authorities.filter.return_value = [MagicMock(name="法院")]
        case.current_stage = "first_trial"
        case.get_current_stage_display.return_value = "一审"
        case.logs.select_related.return_value.order_by.return_value = []

        # Mock contract
        contract = MagicMock()
        contract.id = 1
        contract.name = "合同A"
        contract.get_case_type_display.return_value = "民商事"
        contract.law_firm_oa_case_number = "OA001"
        contract.contract_parties.select_related.return_value.all.return_value = []

        with patch(
            "apps.contracts.services.archive.ArchiveChecklistService"
        ) as MockService, patch.object(
            ArchivePlaceholderService, "_calculate_material_page_count", return_value=1
        ):
            MockService.return_value.get_checklist_with_status.return_value = {"items": []}

            result = service.generate({"case": case, "contract": contract})

        assert "归档日期" in result
        assert "生成日期" in result
        assert "合同名称" in result
        assert "主办律师姓名" in result
        assert "案件案号" in result

    def test_generate_without_case(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        service = ArchivePlaceholderService()

        contract = MagicMock()
        contract.id = 2
        contract.name = "合同B"
        contract.get_case_type_display.return_value = "刑事"
        contract.law_firm_oa_case_number = "OA002"
        contract.contract_parties.select_related.return_value.all.return_value = []
        chain = contract.assignments.select_related.return_value
        chain.filter.return_value.first.return_value = None
        chain.first.return_value = None

        with patch(
            "apps.contracts.services.archive.ArchiveChecklistService"
        ) as MockService, patch(
            "apps.contracts.models.ContractFolderScanSession.objects"
        ) as mock_scan:
            MockService.return_value.get_checklist_with_status.return_value = {"items": []}
            mock_scan.filter.return_value.order_by.return_value.first.return_value = None

            result = service.generate({"contract": contract})

        assert "合同名称" in result
        assert "律师工作日志内容" in result
        assert "案件案号" not in result

    def test_generate_without_contract(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        service = ArchivePlaceholderService()

        lawyer = MagicMock()
        lawyer.real_name = "李律师"
        assignment = MagicMock()
        assignment.lawyer = lawyer
        case = MagicMock()
        case.id = 3
        case.assignments.select_related.return_value.filter.return_value.first.return_value = assignment
        case.case_numbers.filter.return_value = [MagicMock(number="CN001")]
        case.supervising_authorities.filter.return_value = []
        case.current_stage = None
        case.logs.select_related.return_value.order_by.return_value = []

        result = service.generate({"case": case})

        assert "主办律师姓名" in result
        assert "案件案号" in result
        assert "结案归档材料" not in result

    def test_generate_empty_context(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        service = ArchivePlaceholderService()
        result = service.generate({})

        assert "归档日期" in result
        assert "生成日期" in result
        assert "办案小结内容" in result

    def test_generate_opposing_from_case_when_contract_empty(self) -> None:
        from apps.documents.services.placeholders.archive import ArchivePlaceholderService

        service = ArchivePlaceholderService()

        case = MagicMock()
        case.id = 4
        case.assignments.select_related.return_value.filter.return_value.first.return_value = None
        case.assignments.select_related.return_value.first.return_value = None
        case.case_numbers.filter.return_value = []
        case.supervising_authorities.filter.return_value = []
        case.current_stage = None
        case.logs.select_related.return_value.order_by.return_value = []

        p = MagicMock()
        p.client.name = "对方公司"
        p.client.is_our_client = False
        case.parties.select_related.return_value.all.return_value = [p]

        contract = MagicMock()
        contract.id = 2
        contract.name = ""
        contract.get_case_type_display.return_value = ""
        contract.law_firm_oa_case_number = ""
        contract.contract_parties.select_related.return_value.all.return_value = []

        with patch(
            "apps.contracts.services.archive.ArchiveChecklistService"
        ) as MockService:
            MockService.return_value.get_checklist_with_status.return_value = {"items": []}

            result = service.generate({"case": case, "contract": contract})

        assert "对方公司" in result.get("合同对方当事人名称", "")
