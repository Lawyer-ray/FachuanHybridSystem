"""party / contract / supplementary / authorization_materials 占位符服务批量补覆盖。

覆盖：principal_signature、opposing_party、beneficiary_id、representation_stage、
contract_copies、archive_contract_type、advisor_fee_terms、authority_letter、
supplementary basic/opposing/principal。全部使用 SimpleNamespace/MagicMock 替身。
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

WIRING = "apps.documents.services.infrastructure.wiring"


def _client(name="张三", client_type="natural", **kwargs) -> SimpleNamespace:
    base = {
        "id": 1,
        "name": name,
        "client_type": client_type,
        "id_number": "110101199001011234",
        "address": "北京市朝阳区",
        "phone": "13800000000",
        "legal_representative": "李四",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _contract(parties: list, **kwargs) -> SimpleNamespace:
    base = {"id": 1, "specified_date": date(2026, 3, 5), "contract_parties": SimpleNamespace(all=lambda: parties)}
    base.update(kwargs)
    return SimpleNamespace(**base)


def _party(role: str, client) -> SimpleNamespace:
    return SimpleNamespace(role=role, client=client)


# ── party/principal_signature_service ───────────────────────────────


class TestPrincipalSignatureService:
    def _svc(self):
        from apps.documents.services.placeholders.party.principal_signature_service import PrincipalSignatureService

        return PrincipalSignatureService()

    def test_generate_without_contract_returns_empty(self):
        assert self._svc().generate({}) == {}

    def test_generate_natural_person(self):
        contract = _contract([_party("PRINCIPAL", _client("张三"))])
        svc = self._svc()
        service = MagicMock()
        service.is_natural_person_internal.return_value = True
        with patch(f"{WIRING}.get_client_service", return_value=service):
            result = svc.generate({"contract": contract})
        assert "委托人签名盖章信息" in result
        assert "甲方（签名+指模）：张三" in result["委托人签名盖章信息"]
        assert "2026年03月05日" in result["委托人签名盖章信息"]

    def test_generate_legal_entity_without_date(self):
        contract = _contract([_party("PRINCIPAL", _client("某某公司", "enterprise"))], specified_date=None)
        svc = self._svc()
        service = MagicMock()
        service.is_natural_person_internal.return_value = False
        with patch(f"{WIRING}.get_client_service", return_value=service):
            result = svc.generate({"contract": contract})
        assert "甲方（盖章）：某某公司" in result["委托人签名盖章信息"]
        assert "代表：" in result["委托人签名盖章信息"]
        assert result["委托人签名盖章信息"].endswith("\n")  # 无日期时日期行为空串

    def test_no_principals_returns_empty(self):
        contract = _contract([_party("OPPOSING", _client("对方"))])
        assert self._svc().format_principal_signature_info(contract) == ""

    def test_multiple_principals_double_newline_separated(self):
        contract = _contract(
            [
                _party("PRINCIPAL", _client("张三")),
                _party("PRINCIPAL", _client("某某公司", "enterprise", id=2)),
            ]
        )
        svc = self._svc()
        service = MagicMock()
        service.is_natural_person_internal.side_effect = lambda cid: cid == 1
        with patch(f"{WIRING}.get_client_service", return_value=service):
            result = svc.format_principal_signature_info(contract)
        blocks = result.split("\n\n")
        assert blocks[0].startswith("甲方一（签名+指模）：张三")
        assert blocks[1].startswith("甲方二（盖章）：某某公司")

    def test_wiring_error_defaults_to_natural(self):
        svc = self._svc()
        with patch(f"{WIRING}.get_client_service", side_effect=RuntimeError("down")):
            assert svc._is_natural_person(_client("甲")) is True

    def test_signature_format_branches(self):
        svc = self._svc()
        service = MagicMock()
        service.is_natural_person_internal.side_effect = lambda cid: cid == 1
        with patch(f"{WIRING}.get_client_service", return_value=service):
            assert svc._get_signature_format(_client("甲")) == "（签名+指模）"
            assert svc._get_signature_format(SimpleNamespace(name="乙", id=2)) == "（盖章）"

    def test_format_error_returns_empty(self):
        contract = SimpleNamespace(contract_parties=None, id=1)  # .all() 将抛 AttributeError
        with patch(f"{WIRING}.get_client_service", side_effect=RuntimeError("down")):
            assert self._svc().format_principal_signature_info(contract) == ""


# ── party/opposing_party_service ────────────────────────────────────


class TestOpposingPartyService:
    def _svc(self):
        from apps.documents.services.placeholders.party.opposing_party_service import OpposingPartyService

        return OpposingPartyService()

    def test_generate_without_contract(self):
        assert self._svc().generate({}) == {}

    def test_generate_joins_names(self):
        contract = _contract(
            [
                _party("OPPOSING", _client("对方甲")),
                _party("OPPOSING", _client("对方乙")),
                _party("PRINCIPAL", _client("我方")),
            ]
        )
        result = self._svc().generate({"contract": contract})
        assert result["对方当事人名称"] == "对方甲、对方乙"

    def test_format_empty_returns_empty(self):
        assert self._svc().format_opposing_party_names([]) == ""

    def test_format_skips_unnamed_clients(self):
        svc = self._svc()
        result = svc.format_opposing_party_names([_client(""), _client("有名")])
        assert result == "有名"


# ── contract/beneficiary_id_service ─────────────────────────────────


class TestBeneficiaryIdService:
    def _svc(self):
        from apps.documents.services.placeholders.contract.beneficiary_id_service import BeneficiaryIdService

        return BeneficiaryIdService()

    def test_no_contract_returns_blank(self):
        assert self._svc().generate({}) == {"受益人_证件号码": ""}

    def _parties_manager(self, parties: list) -> MagicMock:
        mgr = MagicMock()
        mgr.select_related.return_value.all.return_value = parties
        return mgr

    def test_formats_beneficiaries(self):
        contract = _contract([])
        contract.contract_parties = self._parties_manager(
            [
                _party("BENEFICIARY", _client("王受益", "natural")),
                _party("PRINCIPAL", _client("张三", "natural")),
            ]
        )
        result = self._svc().generate({"contract": contract})
        assert result["受益人_证件号码"] == "王受益（身份证号码：110101199001011234）"

    def test_no_beneficiary_falls_back_to_principal(self):
        contract = _contract([])
        contract.contract_parties = self._parties_manager(
            [
                _party("PRINCIPAL", _client("张三")),
                _party("PRINCIPAL", _client("李四")),
            ]
        )
        result = self._svc().generate({"contract": contract})
        assert result["受益人_证件号码"].count("（身份证号码：") == 2

    def test_format_single_client_without_id_number(self):
        assert self._svc()._format_single_client(_client("无名氏", id_number="")) == "无名氏"

    def test_format_single_client_without_name(self):
        assert self._svc()._format_single_client(_client("", id_number="X")) == ""

    def test_generate_error_returns_blank(self):
        broken = SimpleNamespace(contract_parties=None, id=1)
        assert self._svc().generate({"contract": broken}) == {"受益人_证件号码": ""}


# ── contract/representation_stage_service ───────────────────────────


class TestRepresentationStageService:
    def _svc(self):
        from apps.documents.services.placeholders.contract.representation_stage_service import (
            RepresentationStageService,
        )

        return RepresentationStageService()

    def test_no_contract_returns_empty(self):
        assert self._svc().generate({}) == {}

    def test_empty_stages_returns_empty(self):
        contract = _contract([], representation_stages=[])
        assert self._svc().format_stages(contract) == ""

    def test_missing_stages_attr_returns_empty(self):
        contract = SimpleNamespace(id=1)
        assert self._svc().format_stages(contract) == ""

    def test_single_stage_no_suffix(self):
        contract = _contract([], representation_stages=["first_trial"])
        assert self._svc().format_stages(contract) == "一审"

    def test_multiple_stages_append_if_any(self):
        contract = _contract([], representation_stages=["first_trial", "second_trial"])
        assert self._svc().format_stages(contract) == "一审、二审（如有）"

    def test_unknown_stage_kept_as_is(self):
        contract = _contract([], representation_stages=["custom_stage"])
        assert self._svc().format_stages(contract) == "custom_stage"


# ── contract/contract_copies_service ────────────────────────────────


class TestContractCopiesService:
    def _svc(self):
        from apps.documents.services.placeholders.contract.contract_copies_service import ContractCopiesService

        return ContractCopiesService()

    def test_no_contract_returns_empty(self):
        assert self._svc().generate({}) == {}

    def test_copies_equals_principals_plus_two(self):
        contract = _contract([_party("PRINCIPAL", _client("甲")), _party("PRINCIPAL", _client("乙"))])
        assert self._svc().calculate_contract_copies(contract) == 4

    def test_zero_principals_returns_two(self):
        assert self._svc().calculate_contract_copies(_contract([])) == 2

    def test_broken_parties_returns_two(self):
        contract = SimpleNamespace(id=1, contract_parties=None)
        assert self._svc().calculate_contract_copies(contract) == 2


# ── contract/archive_contract_type_service ──────────────────────────


class TestArchiveContractTypeService:
    def _svc(self):
        from apps.documents.services.placeholders.contract.archive_contract_type_service import (
            ArchiveContractTypeService,
        )

        return ArchiveContractTypeService()

    @pytest.mark.parametrize(
        "case_type,expected",
        [
            ("civil", "诉讼仲裁"),
            ("administrative", "诉讼仲裁"),
            ("labor", "诉讼仲裁"),
            ("intl", "诉讼仲裁"),
            ("criminal", "刑事诉讼"),
            ("special", "非诉"),
            ("advisor", "常年法律顾问"),
            ("unknown", ""),
        ],
    )
    def test_mapping(self, case_type, expected):
        assert self._svc()._map_archive_type(case_type) == expected

    def test_generate_uses_contract_case_type(self):
        contract = _contract([], case_type="advisor")
        result = self._svc().generate({"contract": contract})
        assert result["归档合同类型"] == "常年法律顾问"

    def test_generate_without_contract(self):
        assert self._svc().generate({}) == {}


# ── contract/advisor_fee_terms_service ──────────────────────────────


class TestAdvisorFeeTermsService:
    def _svc(self):
        from apps.documents.services.placeholders.contract.advisor_fee_terms_service import AdvisorFeeTermsService

        return AdvisorFeeTermsService()

    def test_no_contract_returns_empty(self):
        assert self._svc().generate({}) == {}

    def test_fixed_fee_terms(self):
        contract = _contract([], fee_mode="FIXED", fixed_amount=30000)
        terms = self._svc().generate_advisor_fee_terms(contract)
        assert "¥30000.00元" in terms
        assert "大写：人民币" in terms

    def test_fixed_fee_without_amount(self):
        contract = _contract([], fee_mode="fixed", fixed_amount=None)
        terms = self._svc().generate_advisor_fee_terms(contract)
        assert "[金额待定]" in terms

    def test_custom_fee_terms(self):
        contract = _contract([], fee_mode="CUSTOM", custom_terms="按季度收费")
        assert self._svc().generate_advisor_fee_terms(contract) == "按季度收费"

    def test_custom_fee_without_terms(self):
        contract = _contract([], fee_mode="custom", custom_terms=None)
        assert self._svc().generate_advisor_fee_terms(contract) == "收费条款详见自定义条款."

    def test_unsupported_fee_mode(self):
        contract = _contract([], fee_mode="RISK")
        assert self._svc().generate_advisor_fee_terms(contract) == "收费条款待定。"

    def test_number_to_chinese_delegates(self):
        contract = _contract([], fee_mode="FIXED", fixed_amount=100)
        terms = self._svc().generate_advisor_fee_terms(contract)
        assert "壹佰元整" in terms

    def test_number_to_chinese_zero(self):
        assert self._svc()._number_to_chinese(None) == "零元整"
        assert self._svc()._number_to_chinese(0) == "零元整"


# ── authorization_materials/authority_letter_service ────────────────


class TestAuthorityLetterService:
    def _svc(self):
        from apps.documents.services.placeholders.authorization_materials.authority_letter_service import (
            AuthorityLetterPlaceholderService,
        )

        return AuthorityLetterPlaceholderService()

    def _case(self, lawyers: list, current_stage="first_trial") -> SimpleNamespace:
        stage_display = {"first_trial": "一审"}.get(current_stage, current_stage)
        assignments = [
            SimpleNamespace(lawyer=SimpleNamespace(real_name=name, username=f"u{i}", phone=phone, id=i))
            for i, (name, phone) in enumerate(lawyers, start=1)
        ]
        ordered = MagicMock()
        ordered.order_by.return_value = assignments
        assignments_mgr = MagicMock()
        assignments_mgr.select_related.return_value = ordered
        return SimpleNamespace(
            id=1,
            current_stage=current_stage,
            get_current_stage_display=lambda: stage_display,
            assignments=assignments_mgr,
        )

    def test_no_case_returns_blank_values(self):
        assert self._svc().generate({}) == {"当前阶段": "", "律师姓名及联系方式": ""}

    def test_stage_and_contacts(self):
        case = self._case([("张三", "13611112222"), ("李四", "12333334444")])
        result = self._svc().generate({"case": case})
        assert result["当前阶段"] == "一审"
        assert result["律师姓名及联系方式"] == "张三律师：13611112222;李四律师：12333334444."

    def test_no_current_stage(self):
        case = self._case([("张三", "13611112222")], current_stage="")
        result = self._svc().generate({"case": case})
        assert result["当前阶段"] == ""

    def test_lawyer_without_phone(self):
        case = self._case([("张三", None)])
        result = self._svc().generate({"case": case})
        assert result["律师姓名及联系方式"] == "张三律师."

    def test_fully_blank_name_skipped(self):
        assignments = [SimpleNamespace(lawyer=SimpleNamespace(real_name="", username="", phone="13600000000", id=1))]
        ordered = MagicMock()
        ordered.order_by.return_value = assignments
        assignments_mgr = MagicMock()
        assignments_mgr.select_related.return_value = ordered
        case = SimpleNamespace(
            id=1, current_stage="first_trial", get_current_stage_display=lambda: "一审", assignments=assignments_mgr
        )
        assert self._svc().generate({"case": case})["律师姓名及联系方式"] == ""

    def test_lawyer_missing_skipped(self):
        assignments = [SimpleNamespace(lawyer=None)]
        ordered = MagicMock()
        ordered.order_by.return_value = assignments
        assignments_mgr = MagicMock()
        assignments_mgr.select_related.return_value = ordered
        case = SimpleNamespace(
            id=1, current_stage="first_trial", get_current_stage_display=lambda: "一审", assignments=assignments_mgr
        )
        assert self._svc().generate({"case": case})["律师姓名及联系方式"] == ""

    def test_assignments_query_error_returns_empty_contacts(self):
        assignments_mgr = MagicMock()
        assignments_mgr.select_related.side_effect = RuntimeError("db down")
        case = SimpleNamespace(
            id=1,
            current_stage="first_trial",
            get_current_stage_display=lambda: "一审",
            assignments=assignments_mgr,
        )
        result = self._svc().generate({"case": case})
        assert result["律师姓名及联系方式"] == ""
        assert result["当前阶段"] == "一审"

    def test_name_already_ends_with_lawyer_suffix(self):
        case = self._case([("王五律师", "13000000000")])
        result = self._svc().generate({"case": case})
        assert result["律师姓名及联系方式"] == "王五律师：13000000000."

    def test_username_fallback_when_real_name_missing(self):
        assignments = [
            SimpleNamespace(lawyer=SimpleNamespace(real_name=None, username="wangwu", phone="13000000000", id=1))
        ]
        ordered = MagicMock()
        ordered.order_by.return_value = assignments
        assignments_mgr = MagicMock()
        assignments_mgr.select_related.return_value = ordered
        case = SimpleNamespace(
            id=1, current_stage="first_trial", get_current_stage_display=lambda: "一审", assignments=assignments_mgr
        )
        assert self._svc().generate({"case": case})["律师姓名及联系方式"] == "wangwu律师：13000000000."


# ── supplementary/basic_service ─────────────────────────────────────


class TestSupplementaryAgreementBasicService:
    def _svc(self):
        from apps.documents.services.placeholders.supplementary.basic_service import SupplementaryAgreementBasicService

        return SupplementaryAgreementBasicService()

    def test_no_agreement_defaults(self):
        result = self._svc().generate({})
        assert result["补充协议名称"] == ""
        assert result["补充协议份数"] == 2

    def test_agreement_without_name(self):
        agreement = SimpleNamespace(name=None, parties=SimpleNamespace(all=lambda: []))
        result = self._svc().generate({"supplementary_agreement": agreement})
        assert result["补充协议名称"] == ""

    def test_copies_principals_plus_two(self):
        parties = [_party("PRINCIPAL", _client()), _party("PRINCIPAL", _client()), _party("OPPOSING", _client())]
        agreement = SimpleNamespace(name="补充协议一", parties=SimpleNamespace(all=lambda: parties))
        result = self._svc().generate({"supplementary_agreement": agreement})
        assert result["补充协议名称"] == "补充协议一"
        assert result["补充协议份数"] == 4

    def test_calculate_copies_error_returns_two(self):
        broken = SimpleNamespace(parties=None)
        assert self._svc().calculate_copies(broken) == 2


# ── supplementary/opposing_service ──────────────────────────────────


class TestSupplementaryOpposingService:
    def _svc(self):
        from apps.documents.services.placeholders.supplementary.opposing_service import (
            SupplementaryAgreementOpposingService,
        )

        return SupplementaryAgreementOpposingService()

    def test_no_agreement_returns_blank(self):
        assert self._svc().generate({})["补充协议对方当事人主体信息条款"] == ""

    def test_no_opposing_returns_blank_clause(self):
        agreement = SimpleNamespace(parties=SimpleNamespace(all=lambda: [_party("PRINCIPAL", _client())]))
        result = self._svc().generate({"supplementary_agreement": agreement})
        assert result["补充协议对方当事人主体信息条款"] == ""

    def test_natural_and_legal_clause(self):
        agreement = SimpleNamespace(
            parties=SimpleNamespace(
                all=lambda: [
                    _party("OPPOSING", _client("王五", "natural", id_number="110101199001011234")),
                    _party("OPPOSING", _client("某公司", "enterprise", id_number="91110000MA01A1B2C3")),
                ]
            )
        )
        result = self._svc().generate({"supplementary_agreement": agreement})
        clause = result["补充协议对方当事人主体信息条款"]
        assert clause.startswith("补充对方当事人信息：")
        assert "姓名：王五，身份证号码：110101199001011234（签名+指模）" in clause
        assert "名称：某公司，统一社会信用代码91110000MA01A1B2C3" in clause
        assert clause.endswith("。")

    def test_strip_whitespace_removes_all_kinds(self):
        svc = self._svc()
        assert svc._strip_whitespace(" 张 三 ") == "张三"
        assert svc._strip_whitespace("A\u200bB\u200cC") == "ABC"
        assert svc._strip_whitespace("") == ""
        assert svc._strip_whitespace(None) == ""

    def test_format_client_error_falls_back_basic(self):
        class Boom:
            name = "炸了"

            @property
            def id_number(self):
                raise RuntimeError("broken")

        result = self._svc().format_opposing_party_clause([Boom()])
        assert result == "补充对方当事人信息：名称：炸了。"


# ── supplementary/principal_service ─────────────────────────────────


class TestSupplementaryPrincipalService:
    def _svc(self):
        from apps.documents.services.placeholders.supplementary.principal_service import (
            SupplementaryAgreementPrincipalService,
        )

        return SupplementaryAgreementPrincipalService()

    def _agreement(self, principals):
        parties = [_party("PRINCIPAL", c) for c in principals]
        return SimpleNamespace(id=1, name="补充协议一", parties=SimpleNamespace(all=lambda: parties))

    def _contract(self, principals):
        parties = [_party("PRINCIPAL", c) for c in principals]
        return SimpleNamespace(id=1, contract_parties=SimpleNamespace(all=lambda: parties))

    def test_generate_requires_both_contract_and_agreement(self):
        svc = self._svc()
        assert svc.generate({}) == {}
        assert svc.generate({"contract": self._contract([])}) == {}
        assert svc.generate({"supplementary_agreement": self._agreement([])}) == {}

    def test_generate_full_flow(self):
        old_client = _client("张三", id=1)
        new_client = _client("李四", id=2)
        result = self._svc().generate(
            {
                "contract": self._contract([old_client]),
                "supplementary_agreement": self._agreement([old_client, new_client]),
            }
        )
        assert result["补充协议委托人数量"] == 2
        assert "甲方一：张三" in result["补充协议委托人信息"]
        assert "甲方二：李四" in result["补充协议委托人信息"]
        clause = result["补充协议委托人主体信息条款"]
        assert "现新增甲方二作为本补充协议及原合同项下的共同甲方" in clause
        assert "新增甲方与甲方一共同享有" in clause

    def test_find_new_principals(self):
        svc = self._svc()
        existing, new = svc._find_new_principals([_client("甲", id=1), _client("乙", id=2)], [_client("甲", id=1)])
        assert [c.name for c in existing] == ["甲"]
        assert [c.name for c in new] == ["乙"]

    def test_clause_empty_when_no_new_principals(self):
        assert self._svc().format_principal_clause([_client("甲")], []) == ""

    def test_clause_without_existing_principals(self):
        clause = self._svc().format_principal_clause([], [_client("新甲")])
        assert "新增甲方享有原合同及本补充协议约定的全部权利" in clause

    def test_clause_numbers_beyond_ten(self):
        existing = [_client(f"旧{i}", id=i) for i in range(10)]
        new = [_client("新11", id=11)]
        clause = self._svc().format_principal_clause(existing, new)
        assert "现新增甲方11作为" in clause
        assert "与甲方一、甲方二" in clause

    def test_format_principal_info_empty(self):
        assert self._svc().format_principal_info([]) == ""

    def test_format_client_details_natural_with_id(self):
        lines = self._svc()._format_client_details(_client("甲", "natural", id_number="ID123"))
        assert "身份证号码：ID123" in lines
        assert "地址：北京市朝阳区" in lines

    def test_format_client_details_legal_without_optional_fields(self):
        lines = self._svc()._format_client_details(_client("乙", "enterprise", id_number="", legal_representative=""))
        assert lines == ["地址：北京市朝阳区", "电话：13800000000"]

    def test_format_client_details_without_client_type(self):
        lines = self._svc()._format_client_details(SimpleNamespace(address="地址X", phone="电话Y"))
        assert lines == ["地址：地址X", "电话：电话Y"]

    def test_format_client_details_error_falls_back(self):
        class Boom:
            client_type = "natural"

            @property
            def id_number(self):
                raise RuntimeError("broken")

        assert self._svc()._format_client_details(Boom()) == []
