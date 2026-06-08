"""Tests for CaseCommonPlaceholderService."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service() -> Any:
    from apps.documents.services.placeholders.case.case_common_service import (
        CaseCommonPlaceholderService,
    )
    return CaseCommonPlaceholderService()


def _make_client(
    *,
    client_id: int = 10,
    name: str = "张三",
    is_our: bool = True,
    client_type: str = "natural",
    id_number: str = "000000000000000000",
    phone: str = "00000000000",
    address: str = "北京市朝阳区",
    legal_representative: str = "",
) -> MagicMock:
    client = MagicMock()
    client.id = client_id
    client.name = name
    client.is_our_client = is_our
    client.client_type = client_type
    client.id_number = id_number
    client.phone = phone
    client.address = address
    client.legal_representative = legal_representative
    return client


def _make_party(
    *,
    client: MagicMock | None = None,
    legal_status: Any = None,
    party_id: int = 1,
) -> MagicMock:
    party = MagicMock()
    party.client = client or _make_client()
    party.id = party_id
    party.legal_status = legal_status
    return party


def _make_case(**overrides: Any) -> MagicMock:
    case = MagicMock()
    case.id = 1
    case.name = "张三诉李四案"
    case.cause_of_action = "买卖合同纠纷"
    case.current_stage = "first_trial"
    case.specified_date = None
    for k, v in overrides.items():
        setattr(case, k, v)
    return case


# ---------------------------------------------------------------------------
# generate() - no case
# ---------------------------------------------------------------------------

class TestGenerateNoCase:
    def test_returns_empty_values_when_no_case(self):
        svc = _make_service()
        result = svc.generate({})
        assert result == dict.fromkeys(svc.placeholder_keys, "")

    def test_returns_empty_values_when_case_is_none(self):
        svc = _make_service()
        result = svc.generate({"case": None})
        assert result == dict.fromkeys(svc.placeholder_keys, "")


# ---------------------------------------------------------------------------
# _get_trial_authorities
# ---------------------------------------------------------------------------

class TestGetTrialAuthorities:
    def test_filters_trial_authorities(self):
        from apps.core.models.enums import AuthorityType
        a1 = MagicMock()
        a1.authority_type = AuthorityType.TRIAL
        a1.name = "北京市朝阳区人民法院"
        a2 = MagicMock()
        a2.authority_type = AuthorityType.INVESTIGATION
        a2.name = "公安局"
        case = _make_case()
        case.supervising_authorities.all.return_value.order_by.return_value = [a1, a2]
        svc = _make_service()
        result = svc._get_trial_authorities(case)
        assert result == "北京市朝阳区人民法院"

    def test_deduplicates_names(self):
        from apps.core.models.enums import AuthorityType
        a1 = MagicMock(spec=[])
        a1.authority_type = AuthorityType.TRIAL
        a1.name = "法院A"
        a2 = MagicMock(spec=[])
        a2.authority_type = AuthorityType.TRIAL
        a2.name = "法院A"
        case = _make_case()
        case.supervising_authorities.all.return_value.order_by.return_value = [a1, a2]
        svc = _make_service()
        result = svc._get_trial_authorities(case)
        assert result == "法院A"

    def test_returns_empty_on_exception(self):
        case = _make_case()
        case.supervising_authorities.all.return_value.order_by.return_value.__iter__ = MagicMock(side_effect=Exception("db error"))
        svc = _make_service()
        result = svc._get_trial_authorities(case)
        assert result == ""

    def test_multiple_trial_authorities(self):
        from apps.core.models.enums import AuthorityType
        a1 = MagicMock(spec=[])
        a1.authority_type = AuthorityType.TRIAL
        a1.name = "法院A"
        a2 = MagicMock(spec=[])
        a2.authority_type = AuthorityType.TRIAL
        a2.name = "法院B"
        case = _make_case()
        case.supervising_authorities.all.return_value.order_by.return_value = [a1, a2]
        svc = _make_service()
        result = svc._get_trial_authorities(case)
        assert "法院A" in result
        assert "法院B" in result


# ---------------------------------------------------------------------------
# _get_party_names
# ---------------------------------------------------------------------------

class TestGetPartyNames:
    def test_our_party_names(self):
        p1 = _make_party(client=_make_client(name="张三", is_our=True), party_id=1)
        p2 = _make_party(client=_make_client(name="李四", is_our=False, client_id=20), party_id=2)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value = [p1, p2]
        svc = _make_service()
        result = svc._get_party_names(case, is_our_client=True)
        assert result == "张三"

    def test_opposing_party_names(self):
        p1 = _make_party(client=_make_client(name="张三", is_our=True), party_id=1)
        p2 = _make_party(client=_make_client(name="李四", is_our=False, client_id=20), party_id=2)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value = [p1, p2]
        svc = _make_service()
        result = svc._get_party_names(case, is_our_client=False)
        assert result == "李四"

    def test_deduplicates_names(self):
        p1 = _make_party(client=_make_client(name="张三", is_our=True), party_id=1)
        p2 = _make_party(client=_make_client(name="张三", is_our=True, client_id=20), party_id=2)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value = [p1, p2]
        svc = _make_service()
        result = svc._get_party_names(case, is_our_client=True)
        assert result == "张三"

    def test_returns_empty_on_exception(self):
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value.__iter__ = MagicMock(side_effect=Exception("db error"))
        svc = _make_service()
        assert svc._get_party_names(case, is_our_client=True) == ""


# ---------------------------------------------------------------------------
# _get_party_values
# ---------------------------------------------------------------------------

class TestGetPartyValues:
    def test_returns_id_numbers(self):
        c1 = _make_client(id_number="000000000000000000", is_our=True)
        c2 = _make_client(id_number="000000000000000001", is_our=True, client_id=20)
        p1 = _make_party(client=c1, party_id=1)
        p2 = _make_party(client=c2, party_id=2)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value = [p1, p2]
        svc = _make_service()
        result = svc._get_party_values(case, is_our_client=True, field_name="id_number")
        assert "000000000000000000" in result
        assert "000000000000000001" in result

    def test_returns_empty_on_exception(self):
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value.__iter__ = MagicMock(side_effect=Exception)
        svc = _make_service()
        assert svc._get_party_values(case, is_our_client=True, field_name="phone") == ""


# ---------------------------------------------------------------------------
# _get_our_party_addresses
# ---------------------------------------------------------------------------

class TestGetOurPartyAddresses:
    def test_returns_formatted_addresses(self):
        c1 = _make_client(name="张三", address="北京市朝阳区", is_our=True)
        p1 = _make_party(client=c1, party_id=1)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value = [p1]
        svc = _make_service()
        result = svc._get_our_party_addresses(case)
        assert "张三：北京市朝阳区" in result
        assert result.endswith("。")

    def test_returns_empty_string_when_no_parties(self):
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value = []
        svc = _make_service()
        assert svc._get_our_party_addresses(case) == ""

    def test_deduplicates_by_name(self):
        c1 = _make_client(name="张三", address="地址A", is_our=True)
        c2 = _make_client(name="张三", address="地址B", is_our=True, client_id=20)
        p1 = _make_party(client=c1, party_id=1)
        p2 = _make_party(client=c2, party_id=2)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value = [p1, p2]
        svc = _make_service()
        result = svc._get_our_party_addresses(case)
        assert result.count("张三") == 1

    def test_returns_empty_on_exception(self):
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value.__iter__ = MagicMock(side_effect=Exception)
        svc = _make_service()
        assert svc._get_our_party_addresses(case) == ""


# ---------------------------------------------------------------------------
# _format_cause_of_action
# ---------------------------------------------------------------------------

class TestFormatCauseOfAction:
    def test_strips_dash_suffix(self):
        svc = _make_service()
        assert svc._format_cause_of_action("买卖合同纠纷-一审") == "买卖合同纠纷"

    def test_returns_empty_when_none(self):
        svc = _make_service()
        assert svc._format_cause_of_action(None) == ""

    def test_returns_stripped_text(self):
        svc = _make_service()
        assert svc._format_cause_of_action("  合同纠纷  ") == "合同纠纷"

    def test_handles_full_width_dash(self):
        svc = _make_service()
        assert svc._format_cause_of_action("合同纠纷—二审") == "合同纠纷"


# ---------------------------------------------------------------------------
# _get_case_stage
# ---------------------------------------------------------------------------

class TestGetCaseStage:
    def test_returns_display_value(self):
        case = _make_case()
        case.get_current_stage_display.return_value = "一审"
        svc = _make_service()
        assert svc._get_case_stage(case) == "一审"

    def test_returns_empty_when_no_stage(self):
        case = _make_case(current_stage=None)
        svc = _make_service()
        assert svc._get_case_stage(case) == ""

    def test_returns_raw_value_on_exception(self):
        case = _make_case(current_stage="first_trial")
        case.get_current_stage_display.side_effect = Exception("error")
        svc = _make_service()
        assert svc._get_case_stage(case) == "first_trial"


# ---------------------------------------------------------------------------
# _get_lawyer_names / _get_ordered_lawyer_names
# ---------------------------------------------------------------------------

class TestLawyerNames:
    def test_returns_comma_separated_names(self):
        a1 = MagicMock()
        a1.is_primary = True
        a1.id = 1
        l1 = MagicMock()
        l1.real_name = "张律师"
        a1.lawyer = l1
        a2 = MagicMock()
        a2.is_primary = False
        a2.id = 2
        l2 = MagicMock()
        l2.real_name = "王律师"
        a2.lawyer = l2
        case = _make_case()
        case.assignments.select_related.return_value.all.return_value.order_by.return_value = [a1, a2]
        svc = _make_service()
        result = svc._get_lawyer_names(case)
        assert "张律师" in result
        assert "王律师" in result

    def test_primary_first(self):
        a1 = MagicMock()
        a1.is_primary = False
        a1.id = 1
        l1 = MagicMock()
        l1.real_name = "副律师"
        a1.lawyer = l1
        a2 = MagicMock()
        a2.is_primary = True
        a2.id = 2
        l2 = MagicMock()
        l2.real_name = "主律师"
        a2.lawyer = l2
        case = _make_case()
        case.assignments.select_related.return_value.all.return_value.order_by.return_value = [a1, a2]
        svc = _make_service()
        result = svc._get_ordered_lawyer_names(case)
        assert result[0] == "主律师"

    def test_deduplicates(self):
        a1 = MagicMock(is_primary=True, id=1, lawyer=MagicMock(real_name="张律师"))
        a2 = MagicMock(is_primary=False, id=2, lawyer=MagicMock(real_name="张律师"))
        case = _make_case()
        case.assignments.select_related.return_value.all.return_value.order_by.return_value = [a1, a2]
        svc = _make_service()
        result = svc._get_ordered_lawyer_names(case)
        assert len(result) == 1

    def test_empty_on_exception(self):
        case = _make_case()
        case.assignments.select_related.return_value.all.return_value.order_by.return_value.__iter__ = MagicMock(side_effect=Exception)
        svc = _make_service()
        assert svc._get_ordered_lawyer_names(case) == []


# ---------------------------------------------------------------------------
# _get_lawyer_signature_info
# ---------------------------------------------------------------------------

class TestLawyerSignatureInfo:
    def test_single_lawyer(self):
        svc = _make_service()
        with patch.object(svc, "_get_ordered_lawyer_names", return_value=["张律师"]):
            result = svc._get_lawyer_signature_info(_make_case())
            assert "张律师" in result
            assert "代理律师" in result
            assert "日期" in result

    def test_multiple_lawyers(self):
        svc = _make_service()
        with patch.object(svc, "_get_ordered_lawyer_names", return_value=["张律师", "王律师"]):
            result = svc._get_lawyer_signature_info(_make_case())
            assert "代理律师一（签名）：张律师" in result
            assert "代理律师二（签名）：王律师" in result

    def test_empty_when_no_lawyers(self):
        svc = _make_service()
        with patch.object(svc, "_get_ordered_lawyer_names", return_value=[]):
            assert svc._get_lawyer_signature_info(_make_case()) == ""


# ---------------------------------------------------------------------------
# _get_signature_date
# ---------------------------------------------------------------------------

class TestSignatureDate:
    def test_uses_specified_date(self):
        case = _make_case(specified_date=date(2026, 6, 7))
        svc = _make_service()
        result = svc._get_signature_date(case)
        assert result == "2026年6月7日"

    def test_uses_current_date_when_none(self):
        case = _make_case(specified_date=None)
        svc = _make_service()
        result = svc._get_signature_date(case)
        assert "年" in result
        assert "月" in result


# ---------------------------------------------------------------------------
# _coerce_to_date
# ---------------------------------------------------------------------------

class TestCoerceToDate:
    def test_none_returns_none(self):
        svc = _make_service()
        assert svc._coerce_to_date(None) is None

    def test_date_passthrough(self):
        d = date(2026, 1, 1)
        svc = _make_service()
        assert svc._coerce_to_date(d) == d

    def test_datetime_extracts_date(self):
        dt = datetime(2026, 1, 1, 12, 0)
        svc = _make_service()
        assert svc._coerce_to_date(dt) == date(2026, 1, 1)

    def test_valid_iso_string(self):
        svc = _make_service()
        assert svc._coerce_to_date("2026-01-15") == date(2026, 1, 15)

    def test_invalid_string_returns_none(self):
        svc = _make_service()
        assert svc._coerce_to_date("not-a-date") is None

    def test_other_type_returns_none(self):
        svc = _make_service()
        assert svc._coerce_to_date(123) is None


# ---------------------------------------------------------------------------
# _format_signature_block
# ---------------------------------------------------------------------------

class TestFormatSignatureBlock:
    def test_natural_person(self):
        svc = _make_service()
        client = _make_client(client_type="natural", name="张三")
        result = svc._format_signature_block("原告", client, date_str="2026年6月7日")
        assert "签名+指模" in result
        assert "张三" in result

    def test_legal_entity(self):
        svc = _make_service()
        client = _make_client(client_type="legal", name="甲公司", legal_representative="张某")
        result = svc._format_signature_block("被告", client, date_str="2026年6月7日")
        assert "盖章" in result
        assert "法定代表人（签名）：张某" in result
        assert "甲公司" in result


# ---------------------------------------------------------------------------
# _format_role_label
# ---------------------------------------------------------------------------

class TestFormatRoleLabel:
    def test_single_party(self):
        svc = _make_service()
        assert svc._format_role_label("原告", 1, 1) == "原告"

    def test_multiple_parties(self):
        svc = _make_service()
        result = svc._format_role_label("被告", 2, 3)
        assert result == "被告二"


# ---------------------------------------------------------------------------
# _format_index_suffix
# ---------------------------------------------------------------------------

class TestFormatIndexSuffix:
    def test_first_ten_chinese(self):
        svc = _make_service()
        assert svc._format_index_suffix(1) == "一"
        assert svc._format_index_suffix(10) == "十"

    def test_eleven_numeric(self):
        svc = _make_service()
        assert svc._format_index_suffix(11) == "11"


# ---------------------------------------------------------------------------
# _resolve_party_role
# ---------------------------------------------------------------------------

class TestResolvePartyRole:
    def test_plaintiff(self):
        from apps.core.models.enums import LegalStatus
        svc = _make_service()
        party = _make_party(legal_status=LegalStatus.PLAINTIFF)
        assert svc._resolve_party_role(party) == "原告"

    def test_defendant(self):
        from apps.core.models.enums import LegalStatus
        svc = _make_service()
        party = _make_party(legal_status=LegalStatus.DEFENDANT)
        assert svc._resolve_party_role(party) == "被告"

    def test_third(self):
        from apps.core.models.enums import LegalStatus
        svc = _make_service()
        party = _make_party(legal_status=LegalStatus.THIRD)
        assert svc._resolve_party_role(party) == "第三人"

    def test_appellant(self):
        from apps.core.models.enums import LegalStatus
        svc = _make_service()
        party = _make_party(legal_status=LegalStatus.APPELLANT)
        assert svc._resolve_party_role(party) == "上诉人"

    def test_fallback_to_display(self):
        svc = _make_service()
        party = _make_party(legal_status="unknown")
        party.get_legal_status_display.return_value = "自定义角色"
        assert svc._resolve_party_role(party) == "自定义角色"

    def test_fallback_to_default(self):
        svc = _make_service()
        party = _make_party(legal_status=None)
        party.get_legal_status_display.return_value = ""
        assert svc._resolve_party_role(party) == "当事人"


# ---------------------------------------------------------------------------
# _get_our_party_signature_info
# ---------------------------------------------------------------------------

class TestGetOurPartySignatureInfo:
    def test_natural_person_signature(self):
        from apps.core.models.enums import LegalStatus
        client = _make_client(name="张三", client_type="natural")
        party = _make_party(client=client, legal_status=LegalStatus.DEFENDANT, party_id=1)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value = [party]
        svc = _make_service()
        result = svc._get_our_party_signature_info(case)
        assert "张三" in result
        assert "签名+指模" in result

    def test_legal_entity_signature(self):
        from apps.core.models.enums import LegalStatus
        client = _make_client(name="甲公司", client_type="legal", legal_representative="张某")
        party = _make_party(client=client, legal_status=LegalStatus.PLAINTIFF, party_id=1)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value = [party]
        svc = _make_service()
        result = svc._get_our_party_signature_info(case)
        assert "盖章" in result
        assert "张某" in result

    def test_empty_when_no_our_parties(self):
        p = _make_party(client=_make_client(name="李四", is_our=False, client_id=20), party_id=1)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value = [p]
        svc = _make_service()
        assert svc._get_our_party_signature_info(case) == ""

    def test_multiple_parties_roles(self):
        from apps.core.models.enums import LegalStatus
        c1 = _make_client(name="张三", client_type="natural", is_our=True)
        c2 = _make_client(name="李四", client_type="legal", is_our=True, client_id=20, legal_representative="李某")
        c2.legal_representative = "李某"
        p1 = _make_party(client=c1, legal_status=LegalStatus.DEFENDANT, party_id=1)
        p2 = _make_party(client=c2, legal_status=LegalStatus.DEFENDANT, party_id=2)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value = [p1, p2]
        svc = _make_service()
        result = svc._get_our_party_signature_info(case)
        assert "被告一" in result
        assert "被告二" in result


# ---------------------------------------------------------------------------
# _get_opposing_party_info
# ---------------------------------------------------------------------------

class TestGetOpposingPartyInfo:
    def test_natural_opponent(self):
        client = _make_client(name="赵某", is_our=False, client_id=20, client_type="natural",
                             id_number="000000000000000000", phone="00000000001", address="深圳市")
        party = _make_party(client=client, party_id=1)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value = [party]
        svc = _make_service()
        result = svc._get_opposing_party_info(case)
        assert "赵某" in result
        assert "身份证号码：000000000000000000" in result
        assert "地址：深圳市" in result
        assert "联系电话：00000000001" in result

    def test_legal_opponent(self):
        client = _make_client(name="乙公司", is_our=False, client_id=20, client_type="legal",
                             id_number="91110000MA12345678", legal_representative="王某", phone="01012345678")
        party = _make_party(client=client, party_id=1)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value = [party]
        svc = _make_service()
        result = svc._get_opposing_party_info(case)
        assert "统一社会信用代码：91110000MA12345678" in result
        assert "法定代表人：王某" in result

    def test_multiple_opponents(self):
        from apps.core.models.enums import LegalStatus
        c1 = _make_client(name="赵某", is_our=False, client_id=20)
        c2 = _make_client(name="钱某", is_our=False, client_id=30)
        p1 = _make_party(client=c1, legal_status=LegalStatus.DEFENDANT, party_id=1)
        p2 = _make_party(client=c2, legal_status=LegalStatus.DEFENDANT, party_id=2)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value = [p1, p2]
        svc = _make_service()
        result = svc._get_opposing_party_info(case)
        assert "赵某" in result
        assert "钱某" in result

    def test_empty_when_no_opponents(self):
        p = _make_party(client=_make_client(is_our=True), party_id=1)
        case = _make_case()
        case.parties.select_related.return_value.all.return_value.order_by.return_value = [p]
        svc = _make_service()
        assert svc._get_opposing_party_info(case) == ""


# ---------------------------------------------------------------------------
# _format_client_info
# ---------------------------------------------------------------------------

class TestFormatClientInfo:
    def test_none_client(self):
        svc = _make_service()
        result = svc._format_client_info("被告", None)
        assert result == "被告："

    def test_natural_client(self):
        client = _make_client(name="赵某", client_type="natural", id_number="000000000000000000",
                             address="深圳", phone="00000000001")
        svc = _make_service()
        result = svc._format_client_info("原告", client)
        assert "原告：赵某" in result
        assert "身份证号码：000000000000000000" in result

    def test_legal_client(self):
        client = _make_client(name="乙公司", client_type="legal", id_number="91110000MA12345678",
                             legal_representative="王某", address="北京", phone="01012345678")
        svc = _make_service()
        result = svc._format_client_info("被告", client)
        assert "统一社会信用代码" in result
        assert "法定代表人：王某" in result


# ---------------------------------------------------------------------------
# placeholder_keys and metadata
# ---------------------------------------------------------------------------

class TestPlaceholderKeysMetadata:
    def test_keys_count(self):
        svc = _make_service()
        assert len(svc.placeholder_keys) == 13

    def test_metadata_has_all_keys(self):
        svc = _make_service()
        for key in svc.placeholder_keys:
            assert key in svc.placeholder_metadata, f"Missing metadata for: {key}"
            assert "display_name" in svc.placeholder_metadata[key]
            assert "description" in svc.placeholder_metadata[key]


# ---------------------------------------------------------------------------
# generate() full integration (with mocked parties)
# ---------------------------------------------------------------------------

class TestGenerateFull:
    def test_full_output_keys(self):
        from apps.core.models.enums import LegalStatus
        c_our = _make_client(name="张三", is_our=True, client_type="natural")
        c_opp = _make_client(name="李四", is_our=False, client_id=20)
        p1 = _make_party(client=c_our, legal_status=LegalStatus.DEFENDANT, party_id=1)
        p2 = _make_party(client=c_opp, legal_status=LegalStatus.PLAINTIFF, party_id=2)
        a1 = MagicMock()
        a1.is_primary = True
        a1.id = 1
        a1.lawyer = MagicMock(real_name="王律师")
        from apps.core.models.enums import AuthorityType
        auth = MagicMock(spec=[])
        auth.authority_type = AuthorityType.TRIAL
        auth.name = "朝阳法院"
        case = _make_case(cause_of_action="合同纠纷-一审")
        case.parties.select_related.return_value.all.return_value.order_by.return_value = [p1, p2]
        case.supervising_authorities.all.return_value.order_by.return_value = [auth]
        case.assignments.select_related.return_value.all.return_value.order_by.return_value = [a1]
        case.get_current_stage_display.return_value = "一审"
        svc = _make_service()
        result = svc.generate({"case": case})
        assert result["案件审理机构"] == "朝阳法院"
        assert result["案件我方当事人名称"] == "张三"
        assert result["案件对方当事人名称"] == "李四"
        assert result["案件律师姓名"] == "王律师"
        assert result["案件案由"] == "合同纠纷"
        assert result["案件当前阶段"] == "一审"
        assert len(result) == 13
