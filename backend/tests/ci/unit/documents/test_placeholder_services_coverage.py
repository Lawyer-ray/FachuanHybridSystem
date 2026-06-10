"""Comprehensive tests for placeholder services: defense_party, principal, enhanced_opposing_party."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.models.enums import LegalStatus


# ---------------------------------------------------------------------------
# DefensePartyService tests
# ---------------------------------------------------------------------------
class TestDefensePartyService:
    def _get_service(self):
        from apps.documents.services.placeholders.litigation.defense_party_service import DefensePartyService
        svc = DefensePartyService.__new__(DefensePartyService)
        svc.formatter = MagicMock()
        svc.case_details_accessor = MagicMock()
        return svc

    def _make_party_dict(self, legal_status, is_our_client=True, **kwargs):
        return {
            "legal_status": legal_status,
            "is_our_client": is_our_client,
            "client_name": kwargs.get("client_name", "测试"),
            "id_number": kwargs.get("id_number", "110101199003071234"),
            "address": kwargs.get("address", "北京市"),
            "phone": kwargs.get("phone", "13800138000"),
            "legal_representative": kwargs.get("legal_representative", ""),
            "client_type": kwargs.get("client_type", "natural"),
        }

    # _determine_scenario_from_dict
    def test_defendant_only(self):
        svc = self._get_service()
        parties = [self._make_party_dict(LegalStatus.DEFENDANT, True)]
        assert svc._determine_scenario_from_dict(parties) == "defendant_only"

    def test_third_party_only(self):
        svc = self._get_service()
        parties = [self._make_party_dict(LegalStatus.THIRD, True)]
        assert svc._determine_scenario_from_dict(parties) == "third_party_only"

    def test_both(self):
        svc = self._get_service()
        parties = [
            self._make_party_dict(LegalStatus.DEFENDANT, True),
            self._make_party_dict(LegalStatus.THIRD, True),
        ]
        assert svc._determine_scenario_from_dict(parties) == "both"

    def test_default_defendant_only(self):
        svc = self._get_service()
        parties = [self._make_party_dict(LegalStatus.DEFENDANT, False)]
        assert svc._determine_scenario_from_dict(parties) == "defendant_only"

    # _map_roles_from_dict
    def test_map_defendant_only(self):
        svc = self._get_service()
        parties = [
            self._make_party_dict(LegalStatus.DEFENDANT, True),
            self._make_party_dict(LegalStatus.PLAINTIFF, False),
            self._make_party_dict(LegalStatus.THIRD, False),
        ]
        role_map = svc._map_roles_from_dict(parties, "defendant_only")
        assert len(role_map["答辩人"]) == 1
        assert len(role_map["被答辩人"]) == 1
        assert len(role_map["第三人"]) == 1

    def test_map_third_party_only(self):
        svc = self._get_service()
        parties = [
            self._make_party_dict(LegalStatus.THIRD, True),
            self._make_party_dict(LegalStatus.PLAINTIFF, False),
            self._make_party_dict(LegalStatus.DEFENDANT, False),
        ]
        role_map = svc._map_roles_from_dict(parties, "third_party_only")
        assert len(role_map["答辩人"]) == 1
        assert len(role_map["被答辩人"]) == 1
        assert len(role_map["被告"]) == 1

    def test_map_both(self):
        svc = self._get_service()
        parties = [
            self._make_party_dict(LegalStatus.DEFENDANT, True),
            self._make_party_dict(LegalStatus.THIRD, True),
            self._make_party_dict(LegalStatus.PLAINTIFF, False),
        ]
        role_map = svc._map_roles_from_dict(parties, "both")
        assert len(role_map["答辩人"]) == 2
        assert len(role_map["被答辩人"]) == 1

    # _format_party_block
    def test_format_natural_respondent(self):
        svc = self._get_service()
        svc.formatter.is_natural_person_from_dict.return_value = True
        party_dict = self._make_party_dict(LegalStatus.DEFENDANT, client_name="张三")
        result = svc._format_party_block("答辩人", party_dict)
        assert "答辩人" in result
        assert "张三" in result
        assert "身份证号码" in result

    def test_format_legal_respondent(self):
        svc = self._get_service()
        svc.formatter.is_natural_person_from_dict.return_value = False
        party_dict = self._make_party_dict(
            LegalStatus.DEFENDANT,
            client_name="某公司",
            client_type="legal",
            legal_representative="李四",
        )
        result = svc._format_party_block("答辩人", party_dict)
        assert "某公司" in result
        assert "统一社会信用代码" in result

    def test_format_legal_plaintiff(self):
        svc = self._get_service()
        svc.formatter.is_natural_person_from_dict.return_value = False
        party_dict = self._make_party_dict(
            LegalStatus.PLAINTIFF,
            client_name="某公司",
            client_type="legal",
        )
        result = svc._format_party_block("被答辩人", party_dict)
        assert "某公司" in result
        assert "电话" in result

    def test_format_legal_other_role(self):
        svc = self._get_service()
        svc.formatter.is_natural_person_from_dict.return_value = False
        party_dict = self._make_party_dict(
            LegalStatus.THIRD,
            client_name="其他公司",
            client_type="legal",
        )
        result = svc._format_party_block("第三人", party_dict)
        assert "联系电话" in result

    # _numbered_label
    def test_numbered_label_single(self):
        svc = self._get_service()
        assert svc._numbered_label("答辩人", 0, 1) == "答辩人"

    def test_numbered_label_multiple(self):
        svc = self._get_service()
        assert svc._numbered_label("答辩人", 0, 2) == "答辩人一"
        assert svc._numbered_label("答辩人", 1, 2) == "答辩人二"

    def test_numbered_label_overflow(self):
        svc = self._get_service()
        assert svc._numbered_label("答辩人", 10, 11) == "答辩人11"

    # _format_plaintiffs
    def test_format_plaintiffs_single(self):
        svc = self._get_service()
        svc.formatter.is_natural_person_from_dict.return_value = True
        result_parts: list[str] = []
        plaintiffs = [self._make_party_dict(LegalStatus.PLAINTIFF, client_name="原告A")]
        svc._format_plaintiffs(result_parts, plaintiffs)
        assert len(result_parts) == 1
        assert "被答辩人" in result_parts[0]
        assert "（原告）" in result_parts[0]

    def test_format_plaintiffs_multiple(self):
        svc = self._get_service()
        svc.formatter.is_natural_person_from_dict.return_value = True
        result_parts: list[str] = []
        plaintiffs = [
            self._make_party_dict(LegalStatus.PLAINTIFF, client_name="原告A"),
            self._make_party_dict(LegalStatus.PLAINTIFF, client_name="原告B"),
        ]
        svc._format_plaintiffs(result_parts, plaintiffs)
        assert len(result_parts) == 2
        assert "（原告一）" in result_parts[0]
        assert "（原告二）" in result_parts[1]

    # _format_other_roles
    def test_format_other_roles(self):
        svc = self._get_service()
        svc.formatter.is_natural_person_from_dict.return_value = True
        result_parts: list[str] = []
        role_map = {
            "答辩人": [],
            "被答辩人": [],
            "第三人": [self._make_party_dict(LegalStatus.THIRD, client_name="第三人A")],
            "被告": [self._make_party_dict(LegalStatus.DEFENDANT, client_name="被告A", is_our_client=False)],
        }
        svc._format_other_roles(result_parts, role_map)
        assert len(result_parts) == 2

    # generate (no case_id)
    def test_generate_no_case_id(self):
        svc = self._get_service()
        result = svc.generate({"case_id": None})
        assert result == {}


# ---------------------------------------------------------------------------
# SupplementaryAgreementPrincipalService tests
# ---------------------------------------------------------------------------
class TestSupplementaryAgreementPrincipalService:
    def _get_service(self):
        from apps.documents.services.placeholders.supplementary.principal_service import SupplementaryAgreementPrincipalService
        return SupplementaryAgreementPrincipalService.__new__(SupplementaryAgreementPrincipalService)

    def _make_client(self, name="委托人A", client_type="natural", **kwargs):
        return SimpleNamespace(
            id=kwargs.get("id", 1),
            name=name,
            client_type=client_type,
            id_number=kwargs.get("id_number", "110101199003071234"),
            address=kwargs.get("address", "北京市"),
            phone=kwargs.get("phone", "13800138000"),
            legal_representative=kwargs.get("legal_representative", ""),
        )

    # format_principal_info
    def test_format_single(self):
        svc = self._get_service()
        client = self._make_client()
        result = svc.format_principal_info([client])
        assert "甲方：委托人A" in result
        assert "身份证号码" in result

    def test_format_multiple(self):
        svc = self._get_service()
        clients = [self._make_client(f"委托人{i}") for i in range(3)]
        result = svc.format_principal_info(clients)
        assert "甲方一" in result
        assert "甲方二" in result
        assert "甲方三" in result

    def test_format_empty(self):
        svc = self._get_service()
        assert svc.format_principal_info([]) == ""

    def test_format_legal_entity(self):
        svc = self._get_service()
        client = self._make_client(client_type="legal", id_number="91440101MA59TEST", legal_representative="李四")
        result = svc.format_principal_info([client])
        assert "统一社会信用代码" in result
        assert "法定代表人：李四" in result

    # format_principal_clause
    def test_no_new_principals(self):
        svc = self._get_service()
        assert svc.format_principal_clause([], []) == ""

    def test_new_principals_with_existing(self):
        svc = self._get_service()
        existing = [self._make_client("委托人A")]
        new = [self._make_client("委托人B", id=2)]
        result = svc.format_principal_clause(existing, new)
        assert "新增甲方二" in result
        assert "甲方一" in result

    def test_new_principals_no_existing(self):
        svc = self._get_service()
        new = [self._make_client("委托人A")]
        result = svc.format_principal_clause([], new)
        assert "新增甲方一" in result
        # No "新增甲方与" prefix because no existing principals
        assert "共同甲方" in result

    def test_many_new_principals_overflow(self):
        svc = self._get_service()
        existing = [self._make_client(f"委托人{i}", id=i) for i in range(10)]
        new = [self._make_client("新增委托人", id=11)]
        result = svc.format_principal_clause(existing, new)
        # Index 10 overflows: uses str(index + 1) = "11"
        assert "甲方11" in result

    # _find_new_principals
    def test_find_new_principals(self):
        svc = self._get_service()
        client_a = self._make_client("A", id=1)
        client_b = self._make_client("B", id=2)
        client_c = self._make_client("C", id=3)
        existing, new = svc._find_new_principals([client_a, client_b, client_c], [client_a])
        assert len(existing) == 1
        assert len(new) == 2

    def test_find_new_principals_all_new(self):
        svc = self._get_service()
        client_a = self._make_client("A", id=1)
        existing, new = svc._find_new_principals([client_a], [])
        assert len(existing) == 0
        assert len(new) == 1

    # generate
    def test_generate_no_contract(self):
        svc = self._get_service()
        result = svc.generate({})
        assert result == {}

    def test_generate_with_contract_and_agreement(self):
        svc = self._get_service()
        mock_agreement = MagicMock()
        mock_agreement.parties.all.return_value = []
        mock_contract = MagicMock()
        mock_contract.contract_parties.all.return_value = []
        result = svc.generate({
            "contract": mock_contract,
            "supplementary_agreement": mock_agreement,
        })
        assert "补充协议委托人信息" in result
        assert "补充协议委托人数量" in result


# ---------------------------------------------------------------------------
# EnhancedOpposingPartyService tests
# ---------------------------------------------------------------------------
class TestEnhancedOpposingPartyService:
    def _get_service(self):
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import EnhancedOpposingPartyService
        return EnhancedOpposingPartyService.__new__(EnhancedOpposingPartyService)

    # _extract_cause_of_action
    def test_extract_cause_with_dash(self):
        svc = self._get_service()
        case = SimpleNamespace(cause_of_action="借款合同纠纷-2023")
        assert svc._extract_cause_of_action(case) == "借款合同纠纷"

    def test_extract_cause_no_dash(self):
        svc = self._get_service()
        case = SimpleNamespace(cause_of_action="借款合同纠纷")
        assert svc._extract_cause_of_action(case) == "借款合同纠纷"

    def test_extract_cause_empty(self):
        svc = self._get_service()
        case = SimpleNamespace(cause_of_action="")
        assert svc._extract_cause_of_action(case) == ""

    def test_extract_cause_none(self):
        svc = self._get_service()
        case = SimpleNamespace(cause_of_action=None)
        assert svc._extract_cause_of_action(case) == ""

    # _format_case_count
    def test_format_case_count(self):
        svc = self._get_service()
        assert svc._format_case_count(1) == "一案"
        assert svc._format_case_count(2) == "两案"
        assert svc._format_case_count(3) == "三案"
        assert svc._format_case_count(10) == "十案"

    def test_format_case_count_overflow(self):
        svc = self._get_service()
        assert svc._format_case_count(11) == "11案"

    # _format_without_cases
    def test_format_without_cases_no_opposing(self):
        svc = self._get_service()
        contract = MagicMock()
        contract.contract_parties.all.return_value = []
        result = svc._format_without_cases(contract)
        assert result == "合同纠纷一案"

    def test_format_without_cases_with_opposing(self):
        svc = self._get_service()
        mock_client = MagicMock()
        mock_client.name = "某公司"
        mock_cp = MagicMock()
        mock_cp.role = "OPPOSING"
        mock_cp.client = mock_client
        contract = MagicMock()
        contract.contract_parties.all.return_value = [mock_cp]
        result = svc._format_without_cases(contract)
        assert "某公司" in result

    def test_format_without_cases_no_name(self):
        svc = self._get_service()
        mock_client = MagicMock()
        mock_client.name = ""
        mock_cp = MagicMock()
        mock_cp.role = "OPPOSING"
        mock_cp.client = mock_client
        contract = MagicMock()
        contract.contract_parties.all.return_value = [mock_cp]
        result = svc._format_without_cases(contract)
        assert "合同纠纷一案" in result

    # _format_with_cases
    def test_format_with_cases_empty(self):
        svc = self._get_service()
        contract = MagicMock()
        result = svc._format_with_cases(contract, [])
        assert result == ""

    def test_format_with_cases_has_cases(self):
        svc = self._get_service()
        contract = MagicMock()
        contract.contract_parties.all.return_value = []
        mock_case = MagicMock()
        mock_case.cause_of_action = "借款合同纠纷"
        mock_case.parties.all.return_value = []
        result = svc._format_with_cases(contract, [mock_case])
        # Should produce some output
        assert isinstance(result, str)

    # generate
    def test_generate_no_contract(self):
        svc = self._get_service()
        result = svc.generate({})
        assert result == {"对方当事人名称案由与案件数量": ""}

    def test_generate_with_contract_no_cases(self):
        svc = self._get_service()
        contract = MagicMock()
        contract.contract_parties.all.return_value = []
        # Mock _get_contract_cases
        svc._get_contract_cases = MagicMock(return_value=[])
        svc._format_without_cases = MagicMock(return_value="合同纠纷一案")
        result = svc.generate({"contract": contract})
        assert result == {"对方当事人名称案由与案件数量": "合同纠纷一案"}

    # _get_contract_party_ids
    def test_get_contract_party_ids(self):
        svc = self._get_service()
        mock_cp_opp = MagicMock()
        mock_cp_opp.role = "OPPOSING"
        mock_cp_opp.client_id = 10
        mock_cp_our = MagicMock()
        mock_cp_our.role = "PRINCIPAL"
        mock_cp_our.client_id = 20
        contract = MagicMock()
        contract.contract_parties.all.return_value = [mock_cp_opp, mock_cp_our]
        opposing, our = svc._get_contract_party_ids(contract)
        assert 10 in opposing
        assert 20 in our
