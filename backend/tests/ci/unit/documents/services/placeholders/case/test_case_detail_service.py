"""Tests for documents.services.placeholders.contract.case_detail_service.

Covers: generate, _format_without_cases, _format_with_cases,
_format_single_case_detail, _format_case_number, _extract_opposing_parties_from_case,
_extract_cause_of_action, _extract_supervising_authority, _format_target_amount.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestCaseDetailService:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService
        return CaseDetailService()

    def test_generate_empty_contract(self):
        svc = self._make_service()
        result = svc.generate({})
        assert result == {"案件详情": ""}

    def test_generate_none_contract(self):
        svc = self._make_service()
        result = svc.generate({"contract": None})
        assert result == {"案件详情": ""}

    def test_generate_no_cases(self):
        svc = self._make_service()
        contract = MagicMock()
        contract.cases.select_related.return_value.prefetch_related.return_value.all.side_effect = AttributeError
        result = svc.generate({"contract": contract})
        assert result == {"案件详情": ""}

    def test_generate_with_cases(self):
        svc = self._make_service()
        case = SimpleNamespace(
            id=1,
            parties=MagicMock(all=lambda: []),
            cause_of_action="合同纠纷",
            supervising_authorities=MagicMock(all=lambda: []),
            target_amount=100000,
        )
        contract = MagicMock()
        contract.cases.select_related.return_value.prefetch_related.return_value.all.return_value = [case]
        result = svc.generate({"contract": contract})
        assert "案件详情" in result
        assert "合同纠纷" in result["案件详情"]


class TestFormatWithoutCases:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService
        return CaseDetailService()

    def test_basic(self):
        svc = self._make_service()
        client = SimpleNamespace(name="张三")
        cp = SimpleNamespace(role="OPPOSING", client=client)
        contract = MagicMock()
        contract.contract_parties.all.return_value = [cp]
        result = svc._format_without_cases(contract)
        assert "对方当事人名称：张三" in result
        assert "案由：" in result
        assert "审理机关：" in result
        assert "案件金额：" in result

    def test_no_parties(self):
        svc = self._make_service()
        contract = MagicMock()
        contract.contract_parties.all.return_value = []
        result = svc._format_without_cases(contract)
        assert "对方当事人名称：" in result

    def test_exception(self):
        svc = self._make_service()
        contract = MagicMock()
        contract.contract_parties.all.side_effect = Exception("fail")
        result = svc._format_without_cases(contract)
        assert result == "对方当事人名称：\n案由：\n审理机关：\n案件金额："


class TestFormatWithCases:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService
        return CaseDetailService()

    def test_empty_cases(self):
        svc = self._make_service()
        assert svc._format_with_cases([]) == ""

    def test_single_case(self):
        svc = self._make_service()
        case = SimpleNamespace(
            id=1,
            parties=MagicMock(all=lambda: []),
            cause_of_action=None,
            supervising_authorities=MagicMock(all=lambda: []),
            target_amount=None,
        )
        result = svc._format_with_cases([case])
        assert "案件一：" in result


class TestFormatCaseNumber:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService
        return CaseDetailService()

    def test_one(self):
        svc = self._make_service()
        assert svc._format_case_number(1) == "案件一："

    def test_five(self):
        svc = self._make_service()
        assert svc._format_case_number(5) == "案件五："

    def test_large(self):
        svc = self._make_service()
        assert svc._format_case_number(99) == "案件99："


class TestExtractOpposingParties:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService
        return CaseDetailService()

    def test_our_client_excluded(self):
        svc = self._make_service()
        party = SimpleNamespace(
            client=SimpleNamespace(is_our_client=True, name="张三")
        )
        case = MagicMock()
        case.parties.all.return_value = [party]
        assert svc._extract_opposing_parties_from_case(case) == []

    def test_opposing_client_included(self):
        svc = self._make_service()
        party = SimpleNamespace(
            client=SimpleNamespace(is_our_client=False, name="李四")
        )
        case = MagicMock()
        case.parties.all.return_value = [party]
        assert "李四" in svc._extract_opposing_parties_from_case(case)

    def test_exception_propagates(self):
        svc = self._make_service()
        case = MagicMock()
        case.parties.all.side_effect = Exception("db")
        with pytest.raises(Exception):
            svc._extract_opposing_parties_from_case(case)


class TestExtractCauseOfAction:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService
        return CaseDetailService()

    def test_with_dash(self):
        svc = self._make_service()
        case = SimpleNamespace(cause_of_action="合同纠纷-123")
        assert svc._extract_cause_of_action(case) == "合同纠纷"

    def test_none(self):
        svc = self._make_service()
        case = SimpleNamespace(cause_of_action=None)
        assert svc._extract_cause_of_action(case) == ""

    def test_no_attr(self):
        svc = self._make_service()
        case = SimpleNamespace()
        # SimpleNamespace without cause_of_action — getattr returns None
        assert svc._extract_cause_of_action(case) == ""


class TestExtractSupervisingAuthority:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService
        return CaseDetailService()

    def test_trial_authority(self):
        svc = self._make_service()
        from apps.core.models.enums import AuthorityType
        auth = SimpleNamespace(authority_type=AuthorityType.TRIAL, name="北京仲裁委")
        case = MagicMock()
        case.supervising_authorities.all.return_value = [auth]
        assert svc._extract_supervising_authority(case) == "北京仲裁委"

    def test_no_trial_authority(self):
        svc = self._make_service()
        from apps.core.models.enums import AuthorityType
        auth = SimpleNamespace(authority_type=AuthorityType.INVESTIGATION, name="公安局")
        case = MagicMock()
        case.supervising_authorities.all.return_value = [auth]
        assert svc._extract_supervising_authority(case) == ""

    def test_empty_name(self):
        svc = self._make_service()
        from apps.core.models.enums import AuthorityType
        auth = SimpleNamespace(authority_type=AuthorityType.TRIAL, name="")
        case = MagicMock()
        case.supervising_authorities.all.return_value = [auth]
        assert svc._extract_supervising_authority(case) == ""

    def test_exception(self):
        svc = self._make_service()
        case = MagicMock()
        case.supervising_authorities.all.side_effect = Exception("fail")
        assert svc._extract_supervising_authority(case) == ""


class TestFormatTargetAmount:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService
        return CaseDetailService()

    def test_with_amount(self):
        svc = self._make_service()
        case = SimpleNamespace(target_amount=100000)
        assert svc._format_target_amount(case) == "100000.00元"

    def test_none_amount(self):
        svc = self._make_service()
        case = SimpleNamespace(target_amount=None)
        assert svc._format_target_amount(case) == ""

    def test_no_attr(self):
        svc = self._make_service()
        case = SimpleNamespace()
        # SimpleNamespace without target_amount — getattr returns None
        assert svc._format_target_amount(case) == ""


class TestFormatSingleCaseDetail:
    def _make_service(self):
        from apps.documents.services.placeholders.contract.case_detail_service import CaseDetailService
        return CaseDetailService()

    def test_basic(self):
        svc = self._make_service()
        case = SimpleNamespace(
            id=1,
            parties=MagicMock(all=lambda: []),
            cause_of_action="合同纠纷",
            supervising_authorities=MagicMock(all=lambda: []),
            target_amount=50000,
        )
        result = svc._format_single_case_detail(1, case)
        assert "案件一：" in result
        assert "合同纠纷" in result
        assert "50000.00元" in result
