"""Tests for documents.services.placeholders.contract.enhanced_opposing_party_service.

Covers: generate (empty contract, no cases, with cases, exception),
_format_without_cases, _format_with_cases, _get_contract_party_ids,
_format_single_case, _extract_opposing_parties_from_case,
_extract_cause_of_action, _format_case_count.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestEnhancedOpposingPartyServiceGenerate:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )
        return EnhancedOpposingPartyService()

    def test_generate_empty_contract(self):
        svc = self._make_service()
        result = svc.generate({})
        assert result == {"对方当事人名称案由与案件数量": ""}

    def test_generate_none_contract(self):
        svc = self._make_service()
        result = svc.generate({"contract": None})
        assert result == {"对方当事人名称案由与案件数量": ""}

    def test_generate_no_cases(self):
        svc = self._make_service()
        contract = MagicMock()
        contract.cases.select_related.return_value.prefetch_related.return_value.all.side_effect = AttributeError
        # _get_contract_cases catches AttributeError and returns []
        # So it falls to _format_without_cases
        contract.contract_parties.all.return_value = []
        result = svc.generate({"contract": contract})
        assert result["对方当事人名称案由与案件数量"] == "合同纠纷一案"

    def test_generate_exception_returns_empty(self):
        svc = self._make_service()
        contract = MagicMock()
        contract.cases.select_related.side_effect = Exception("boom")
        # _get_contract_cases catches general Exception
        contract.contract_parties.all.return_value = []
        result = svc.generate({"contract": contract})
        assert "合同纠纷一案" in result["对方当事人名称案由与案件数量"]


class TestFormatWithoutCases:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )
        return EnhancedOpposingPartyService()

    def test_no_parties(self):
        svc = self._make_service()
        contract = MagicMock()
        contract.contract_parties.all.return_value = []
        assert svc._format_without_cases(contract) == "合同纠纷一案"

    def test_with_opposing_parties(self):
        svc = self._make_service()
        client = SimpleNamespace(name="张三")
        cp = SimpleNamespace(role="OPPOSING", client=client)
        contract = MagicMock()
        contract.contract_parties.all.return_value = [cp]
        result = svc._format_without_cases(contract)
        assert "张三" in result
        assert "合同纠纷一案" in result

    def test_opposing_party_no_name(self):
        svc = self._make_service()
        client = SimpleNamespace(name="")
        cp = SimpleNamespace(role="OPPOSING", client=client)
        contract = MagicMock()
        contract.contract_parties.all.return_value = [cp]
        result = svc._format_without_cases(contract)
        assert result == "合同纠纷一案"

    def test_opposing_party_client_without_name_attr(self):
        svc = self._make_service()
        client = SimpleNamespace()
        # Don't set name attribute at all
        cp = SimpleNamespace(role="OPPOSING", client=client)
        contract = MagicMock()
        contract.contract_parties.all.return_value = [cp]
        result = svc._format_without_cases(contract)
        assert result == "合同纠纷一案"


class TestFormatWithCases:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )
        return EnhancedOpposingPartyService()

    def test_empty_cases(self):
        svc = self._make_service()
        assert svc._format_with_cases(MagicMock(), []) == ""

    def test_single_case_with_names(self):
        svc = self._make_service()
        contract = MagicMock()
        cp = SimpleNamespace(role="OUR", client_id=1)
        contract.contract_parties.all.return_value = [cp]

        party = SimpleNamespace(client_id=2, client=SimpleNamespace(name="李四", is_our_client=False))
        case = MagicMock()
        case.parties.all.return_value = [party]
        case.cause_of_action = "合同纠纷-123"

        result = svc._format_with_cases(contract, [case])
        assert "李四" in result
        assert "合同纠纷" in result
        assert "一案" in result


class TestGetContractPartyIds:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )
        return EnhancedOpposingPartyService()

    def test_basic(self):
        svc = self._make_service()
        cp1 = SimpleNamespace(role="OPPOSING", client_id=1)
        cp2 = SimpleNamespace(role="OUR", client_id=2)
        contract = MagicMock()
        contract.contract_parties.all.return_value = [cp1, cp2]
        opposing, our = svc._get_contract_party_ids(contract)
        assert 1 in opposing
        assert 2 in our

    def test_exception(self):
        svc = self._make_service()
        contract = MagicMock()
        contract.contract_parties.all.side_effect = Exception("fail")
        opposing, our = svc._get_contract_party_ids(contract)
        assert opposing == set()
        assert our == set()


class TestExtractOpposingPartiesFromCase:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )
        return EnhancedOpposingPartyService()

    def test_with_opposing_in_set(self):
        svc = self._make_service()
        party = SimpleNamespace(client_id=1, client=SimpleNamespace(name="王五", is_our_client=False))
        case = MagicMock()
        case.parties.all.return_value = [party]
        result = svc._extract_opposing_parties_from_case(
            case, opposing_client_ids={1}, our_client_ids=set()
        )
        assert "王五" in result

    def test_our_client_excluded(self):
        svc = self._make_service()
        party = SimpleNamespace(client_id=2, client=SimpleNamespace(name="赵六", is_our_client=True))
        case = MagicMock()
        case.parties.all.return_value = [party]
        result = svc._extract_opposing_parties_from_case(
            case, opposing_client_ids=set(), our_client_ids={2}
        )
        assert result == []

    def test_no_client(self):
        svc = self._make_service()
        party = SimpleNamespace(client_id=1, client=None)
        case = MagicMock()
        case.parties.all.return_value = [party]
        result = svc._extract_opposing_parties_from_case(
            case, opposing_client_ids=set(), our_client_ids=set()
        )
        assert result == []

    def test_exception_propagates(self):
        svc = self._make_service()
        case = MagicMock()
        case.parties.all.side_effect = Exception("db fail")
        with pytest.raises(Exception):
            svc._extract_opposing_parties_from_case(
                case, opposing_client_ids=set(), our_client_ids=set()
            )


class TestExtractCauseOfAction:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )
        return EnhancedOpposingPartyService()

    def test_with_dash(self):
        svc = self._make_service()
        case = SimpleNamespace(cause_of_action="合同纠纷-123")
        assert svc._extract_cause_of_action(case) == "合同纠纷"

    def test_without_dash(self):
        svc = self._make_service()
        case = SimpleNamespace(cause_of_action="合同纠纷")
        assert svc._extract_cause_of_action(case) == "合同纠纷"

    def test_none(self):
        svc = self._make_service()
        case = SimpleNamespace(cause_of_action=None)
        assert svc._extract_cause_of_action(case) == ""

    def test_no_attribute(self):
        svc = self._make_service()
        case = SimpleNamespace()
        # SimpleNamespace without cause_of_action attr — getattr returns None
        assert svc._extract_cause_of_action(case) == ""


class TestFormatCaseCount:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )
        return EnhancedOpposingPartyService()

    def test_two(self):
        svc = self._make_service()
        assert svc._format_case_count(2) == "两案"

    def test_three(self):
        svc = self._make_service()
        assert svc._format_case_count(3) == "三案"

    def test_large_number(self):
        svc = self._make_service()
        assert svc._format_case_count(100) == "100案"


class TestFormatSingleCase:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )
        return EnhancedOpposingPartyService()

    def test_both_names_and_cause(self):
        svc = self._make_service()
        party = SimpleNamespace(client_id=1, client=SimpleNamespace(name="张三", is_our_client=False))
        case = MagicMock()
        case.parties.all.return_value = [party]
        case.cause_of_action = "合同纠纷"
        result = svc._format_single_case(case, opposing_client_ids={1}, our_client_ids=set())
        assert "张三" in result
        assert "合同纠纷" in result

    def test_only_cause(self):
        svc = self._make_service()
        case = MagicMock()
        case.parties.all.return_value = []
        case.cause_of_action = "侵权纠纷"
        result = svc._format_single_case(case, opposing_client_ids=set(), our_client_ids=set())
        assert result == "侵权纠纷"
