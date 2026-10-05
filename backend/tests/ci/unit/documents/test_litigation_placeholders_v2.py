"""litigation 占位符服务批量补覆盖。

覆盖：case_details_accessor、party_formatter、supervising_authority、complaint_party、
complaint_signature、defense_signature、enforcement_party（申请人/被申请人/名称/基础字段）、
enforcement_signature、enforcement_judgment、enforcement_media_publication、
enforcement_exit_restriction、enforcement_spending_restriction、enforcement_applicant_property_clue、
preservation_party、preservation_signature、preservation_amount、case_lawyer、filename_service。
案件明细访问器与 ORM 查询全部用替身，不触碰数据库。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError
from apps.core.models.enums import LegalStatus
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys as Keys

LITIGATION = "apps.documents.services.placeholders.litigation"
WIRING = "apps.documents.services.infrastructure.wiring"


def _party_dict(
    name="张三",
    legal_status="plaintiff",
    client_type="natural",
    is_our_client=True,
    id_number="110101199001011234",
    address="北京市朝阳区",
    phone="13800000000",
    legal_representative="",
) -> dict:
    return {
        "client_name": name,
        "legal_status": legal_status,
        "client_type": client_type,
        "is_our_client": is_our_client,
        "id_number": id_number,
        "address": address,
        "phone": phone,
        "legal_representative": legal_representative,
    }


def _accessor(parties: list[dict], formatted_date="2026年01月02日", details: dict | None = None) -> MagicMock:
    acc = MagicMock()
    acc.get_case_parties.return_value = parties
    acc.get_formatted_date.return_value = formatted_date
    acc.require_case_details.return_value = details if details is not None else {"case_parties": parties}
    return acc


# ── case_details_accessor ───────────────────────────────────────────


class TestLitigationCaseDetailsAccessor:
    def _accessor(self, case_service=None):
        from apps.documents.services.placeholders.litigation.case_details_accessor import LitigationCaseDetailsAccessor

        return LitigationCaseDetailsAccessor(case_service=case_service)

    def test_case_service_lazy_load(self):
        acc = self._accessor()
        sentinel = MagicMock()
        with patch(f"{WIRING}.get_case_service", return_value=sentinel):
            assert acc.case_service is sentinel

    def test_get_case_details_uses_cache(self):
        case_service = MagicMock()
        case_service.get_case_with_details_internal.return_value = {"id": 1}
        acc = self._accessor(case_service)
        assert acc.get_case_details(case_id=1) == {"id": 1}
        assert acc.get_case_details(case_id=1) == {"id": 1}
        case_service.get_case_with_details_internal.assert_called_once_with(1)

    def test_get_case_details_caches_none(self):
        case_service = MagicMock()
        case_service.get_case_with_details_internal.return_value = None
        acc = self._accessor(case_service)
        assert acc.get_case_details(case_id=2) is None
        case_service.get_case_with_details_internal.assert_called_once_with(2)

    def test_require_case_details_missing_raises(self):
        case_service = MagicMock()
        case_service.get_case_with_details_internal.return_value = None
        acc = self._accessor(case_service)
        with pytest.raises(NotFoundError):
            acc.require_case_details(case_id=3)

    def test_get_case_parties(self):
        case_service = MagicMock()
        case_service.get_case_with_details_internal.return_value = {"case_parties": [_party_dict()]}
        acc = self._accessor(case_service)
        assert acc.get_case_parties(case_id=1) == [_party_dict()]

    def test_get_case_parties_missing_key_returns_empty(self):
        case_service = MagicMock()
        case_service.get_case_with_details_internal.return_value = {"id": 1}
        acc = self._accessor(case_service)
        assert acc.get_case_parties(case_id=1) == []

    def test_get_case_parties_none_returns_empty(self):
        case_service = MagicMock()
        case_service.get_case_with_details_internal.return_value = {"case_parties": None}
        acc = self._accessor(case_service)
        assert acc.get_case_parties(case_id=1) == []

    def test_coerce_date_variants(self):
        acc = self._accessor()
        assert acc._coerce_date(None) is None
        assert acc._coerce_date(date(2026, 1, 2)) == date(2026, 1, 2)
        assert acc._coerce_date("2026-01-02") == date(2026, 1, 2)
        assert acc._coerce_date("not-a-date") is None
        assert acc._coerce_date(12345) is None

    def test_coerce_date_datetime(self):
        from datetime import datetime

        acc = self._accessor()
        assert acc._coerce_date(datetime(2026, 1, 2, 10, 30)) == date(2026, 1, 2)

    def test_get_formatted_date_prefers_specified(self):
        case_service = MagicMock()
        case_service.get_case_with_details_internal.return_value = {"specified_date": date(2026, 3, 5)}
        acc = self._accessor(case_service)
        assert acc.get_formatted_date(case_id=1) == "2026年03月05日"

    def test_get_formatted_date_falls_back_to_today(self):
        case_service = MagicMock()
        case_service.get_case_with_details_internal.return_value = {"id": 1}
        acc = self._accessor(case_service)
        result = acc.get_formatted_date(case_id=1)
        assert result.endswith("日") and "年" in result


# ── party_formatter ─────────────────────────────────────────────────


class TestPartyFormatter:
    def _formatter(self):
        from apps.documents.services.placeholders.litigation.party_formatter import PartyFormatter

        return PartyFormatter()

    def test_is_natural_person(self):
        f = self._formatter()
        assert f.is_natural_person(SimpleNamespace(client=SimpleNamespace(client_type="natural"))) is True
        assert f.is_natural_person(SimpleNamespace(client=SimpleNamespace(client_type="enterprise"))) is False
        assert f.is_natural_person(None) is False
        assert f.is_natural_person(SimpleNamespace(client=None)) is False

    def test_is_natural_person_from_dict(self):
        f = self._formatter()
        assert f.is_natural_person_from_dict({"client_type": "natural"}) is True
        assert f.is_natural_person_from_dict({"client_type": "enterprise"}) is False
        assert f.is_natural_person_from_dict({}) is False
        assert f.is_natural_person_from_dict(None) is False

    def test_get_role_label(self):
        f = self._formatter()
        assert f.get_role_label("原告", 0, 1) == "原告"
        assert f.get_role_label("被告", 0, 2) == "被告一"
        assert f.get_role_label("被告", 10, 11) == "被告11"

    def test_format_natural_person_with_valid_id(self):
        f = self._formatter()
        client = SimpleNamespace(name="张三", id_number="110101199001011234", address="北京市", phone="13800000000")
        result = f.format_natural_person("原告", SimpleNamespace(client=client))
        assert result.startswith("原告：张三，男，")
        assert "身份证号码：110101199001011234" in result
        assert "联系电话：13800000000" in result

    def test_format_natural_person_invalid_id_no_phone(self):
        f = self._formatter()
        client = SimpleNamespace(name="张三", id_number="X", address="北京市", phone="")
        result = f.format_natural_person("原告", SimpleNamespace(client=client))
        assert result == "原告：张三\n地址：北京市\n身份证号码：X"

    def test_format_natural_person_missing_client(self):
        assert self._formatter().format_natural_person("原告", None) == "原告：\n"
        assert self._formatter().format_natural_person("原告", SimpleNamespace(client=None)) == "原告：\n"

    def test_format_legal_entity(self):
        f = self._formatter()
        client = SimpleNamespace(
            name="某公司", id_number="USCC1", address="北京市", legal_representative="李四", phone="010"
        )
        result = f.format_legal_entity("被告", SimpleNamespace(client=client))
        assert "被告：某公司" in result
        assert "统一社会信用代码：USCC1" in result
        assert "法定代表人：李四" in result

    def test_format_legal_entity_missing_client(self):
        assert self._formatter().format_legal_entity("被告", SimpleNamespace(client=None)) == "被告：\n"

    def test_format_from_dict_variants(self):
        f = self._formatter()
        natural = f.format_natural_person_from_dict("原告", _party_dict())
        assert natural.startswith("原告：张三，男，")
        legal = f.format_legal_entity_from_dict(
            "被告", _party_dict(legal_status="defendant", client_type="enterprise", legal_representative="王五")
        )
        assert "法定代表人：王五" in legal
        assert f.format_natural_person_from_dict("原告", None) == "原告：\n"
        assert f.format_legal_entity_from_dict("被告", None) == "被告：\n"


# ── supervising_authority ───────────────────────────────────────────


class TestSupervisingAuthorityService:
    def _svc(self, authorities, parties=None):
        from apps.documents.services.placeholders.litigation.supervising_authority_service import (
            SupervisingAuthorityService,
        )

        svc = SupervisingAuthorityService()
        svc.case_details_accessor = _accessor(parties or [], details={"supervising_authorities": authorities})
        return svc

    def test_no_case_id_returns_empty(self):
        assert self._svc([]).generate({}) == {}

    def test_case_object_id_used(self):
        svc = self._svc([{"authority_type": "trial", "name": "广州市中级人民法院"}])
        assert svc.generate({"case": SimpleNamespace(id=5)})[Keys.COURT] == "广州市中级人民法院"

    def test_returns_trial_authority_name(self):
        svc = self._svc(
            [
                {"authority_type": "other", "name": "无关机构"},
                {"authority_type": "trial", "name": "北京一中院"},
            ]
        )
        assert svc.get_supervising_authority(1) == "北京一中院"

    def test_trial_authority_without_name_skipped(self):
        svc = self._svc([{"authority_type": "trial", "name": ""}, {"authority_type": "trial", "name": "上海高院"}])
        assert svc.get_supervising_authority(1) == "上海高院"

    def test_no_trial_authority_returns_empty(self):
        assert self._svc([{"authority_type": "other", "name": "X"}]).get_supervising_authority(1) == ""

    def test_malformed_authorities_returns_empty(self):
        svc = self._svc(None)
        svc.case_details_accessor.require_case_details.return_value = {"supervising_authorities": None}
        assert svc.get_supervising_authority(1) == ""


# ── complaint_party ─────────────────────────────────────────────────


class TestComplaintPartyService:
    def _svc(self, parties):
        from apps.documents.services.placeholders.litigation.complaint_party_service import ComplaintPartyService

        svc = ComplaintPartyService()
        svc.case_details_accessor = _accessor(parties)
        return svc

    def test_no_case_id_returns_empty(self):
        assert self._svc([]).generate({}) == {}

    def test_groups_by_legal_status_in_order(self):
        parties = [
            _party_dict(name="被告甲", legal_status="defendant", client_type="enterprise", legal_representative="王五"),
            _party_dict(name="原告甲", legal_status="plaintiff"),
            _party_dict(name="第三人甲", legal_status="third"),
        ]
        result = self._svc(parties).generate({"case_id": 1})[Keys.COMPLAINT_PARTY]
        blocks = result.split("\n\n")
        assert blocks[0].startswith("原告：原告甲，男，")
        assert blocks[1].startswith("被告：被告甲")
        assert "法定代表人：王五" in blocks[1]
        assert blocks[2].startswith("第三人：第三人甲，男，")

    def test_multiple_same_role_numbered(self):
        parties = [
            _party_dict(name="原告一", legal_status="plaintiff"),
            _party_dict(name="原告二", legal_status="plaintiff"),
        ]
        result = self._svc(parties).generate({"case_id": 1})[Keys.COMPLAINT_PARTY]
        assert "原告一：原告一" in result
        assert "原告二：原告二" in result

    def test_no_parties_returns_empty_string(self):
        assert self._svc([]).generate({"case_id": 1})[Keys.COMPLAINT_PARTY] == ""

    def test_party_without_legal_status_skipped(self):
        result = self._svc([{"client_name": "无地位", "legal_status": None}]).generate({"case_id": 1})
        assert result[Keys.COMPLAINT_PARTY] == ""


# ── complaint_signature ─────────────────────────────────────────────


class TestComplaintSignatureService:
    def _svc(self, parties):
        from apps.documents.services.placeholders.litigation.complaint_signature_service import (
            ComplaintSignatureService,
        )

        svc = ComplaintSignatureService()
        svc.case_details_accessor = _accessor(parties)
        return svc

    def test_no_case_id_returns_empty(self):
        assert self._svc([]).generate({}) == {}

    def test_natural_and_legal_signature_blocks(self):
        parties = [
            _party_dict(name="张三", legal_status="plaintiff"),
            _party_dict(
                name="原告公司", legal_status="plaintiff", client_type="enterprise", legal_representative="李四"
            ),
        ]
        result = self._svc(parties).generate({"case_id": 1})[Keys.COMPLAINT_SIGNATURE]
        blocks = result.split("\n\n")
        assert blocks[0] == "原告（签名+指模）：张三\n日期：2026年01月02日"
        assert blocks[1] == "原告（盖章）：原告公司\n法定代表人（签名）：李四\n日期：2026年01月02日"

    def test_third_party_role_used_when_no_plaintiff(self):
        parties = [_party_dict(name="第三人甲", legal_status="third")]
        result = self._svc(parties).generate({"case_id": 1})[Keys.COMPLAINT_SIGNATURE]
        assert result.startswith("第三人（签名+指模）：第三人甲")

    def test_only_our_client_parties_included(self):
        parties = [_party_dict(name="对方原告", legal_status="plaintiff", is_our_client=False)]
        assert self._svc(parties).generate({"case_id": 1})[Keys.COMPLAINT_SIGNATURE] == ""

    def test_no_matching_parties_returns_empty(self):
        assert self._svc([]).generate({"case_id": 1})[Keys.COMPLAINT_SIGNATURE] == ""


# ── defense_signature ───────────────────────────────────────────────


class TestDefenseSignatureService:
    def _svc(self, parties):
        from apps.documents.services.placeholders.litigation.defense_signature_service import DefenseSignatureService

        svc = DefenseSignatureService()
        svc.case_details_accessor = _accessor(parties)
        return svc

    def test_no_case_id_returns_empty(self):
        assert self._svc([]).generate({}) == {}

    def test_single_defendant_natural(self):
        parties = [_party_dict(name="被告甲", legal_status="defendant")]
        result = self._svc(parties).generate({"case_id": 1})[Keys.DEFENSE_SIGNATURE]
        assert result == "答辩人（签名+指模）：被告甲\n日期：2026年01月02日"

    def test_multiple_defendants_numbered(self):
        parties = [
            _party_dict(name="被告甲", legal_status="defendant"),
            _party_dict(
                name="被告乙公司", legal_status="defendant", client_type="enterprise", legal_representative="王五"
            ),
        ]
        result = self._svc(parties).generate({"case_id": 1})[Keys.DEFENSE_SIGNATURE]
        blocks = result.split("\n\n")
        assert blocks[0].startswith("答辩人一（签名+指模）：被告甲")
        assert blocks[1].startswith("答辩人二（盖章）：被告乙公司")
        assert "法定代表人（签名）：王五" in blocks[1]

    def test_third_party_included(self):
        parties = [_party_dict(name="第三人甲", legal_status="third")]
        result = self._svc(parties).generate({"case_id": 1})[Keys.DEFENSE_SIGNATURE]
        assert "答辩人（签名+指模）：第三人甲" in result

    def test_no_matching_parties_returns_empty(self):
        parties = [_party_dict(name="原告", legal_status="plaintiff")]
        assert self._svc(parties).generate({"case_id": 1})[Keys.DEFENSE_SIGNATURE] == ""


# ── enforcement party 系列 ──────────────────────────────────────────


class TestEnforcementApplicantPartyService:
    def _svc(self, parties):
        from apps.documents.services.placeholders.litigation.enforcement_party_service import (
            EnforcementApplicantPartyService,
        )

        svc = EnforcementApplicantPartyService()
        svc.case_details_accessor = _accessor(parties)
        return svc

    def test_no_case_id_returns_empty(self):
        assert self._svc([]).generate({}) == {}

    def test_applicants_from_plaintiff_and_applicant(self):
        parties = [
            _party_dict(name="原告甲", legal_status="plaintiff"),
            _party_dict(
                name="申请人乙", legal_status="applicant", client_type="enterprise", legal_representative="李四"
            ),
        ]
        result = self._svc(parties).generate({"case_id": 1})[Keys.ENFORCEMENT_APPLICANT_PARTY]
        blocks = result.split("\n\n")
        assert blocks[0].startswith("申请人一：原告甲")
        assert blocks[1].startswith("申请人二：申请人乙")

    def test_no_applicants_returns_placeholder(self):
        assert self._svc([]).generate({"case_id": 1})[Keys.ENFORCEMENT_APPLICANT_PARTY] == "申请人：\n"


class TestEnforcementApplicantBasicFieldsService:
    def _svc(self, parties):
        from apps.documents.services.placeholders.litigation.enforcement_party_service import (
            EnforcementApplicantBasicFieldsService,
        )

        svc = EnforcementApplicantBasicFieldsService()
        svc.case_details_accessor = _accessor(parties)
        return svc

    def test_no_case_id_returns_empty(self):
        assert self._svc([]).generate({}) == {}

    def test_joins_unique_fields_with_separators(self):
        parties = [
            _party_dict(name="张三", legal_status="applicant"),
            _party_dict(name="张三", legal_status="applicant"),  # 重复字段应去重
        ]
        result = self._svc(parties).generate({"case_id": 1})
        assert result[Keys.ENFORCEMENT_APPLICANT_NAME] == "张三"
        assert result[Keys.ENFORCEMENT_APPLICANT_ADDRESS] == "北京市朝阳区"
        assert result[Keys.ENFORCEMENT_APPLICANT_PHONE] == "13800000000"
        assert result[Keys.ENFORCEMENT_APPLICANT_ID] == "110101199001011234"


class TestEnforcementRespondentPartyService:
    def _svc(self, parties):
        from apps.documents.services.placeholders.litigation.enforcement_party_service import (
            EnforcementRespondentPartyService,
        )

        svc = EnforcementRespondentPartyService()
        svc.case_details_accessor = _accessor(parties)
        return svc

    def test_no_case_id_returns_empty(self):
        assert self._svc([]).generate({}) == {}

    def test_respondents_from_defendant_and_respondent(self):
        parties = [
            _party_dict(name="被告甲", legal_status="defendant"),
            _party_dict(
                name="被申请人乙", legal_status="respondent", client_type="enterprise", legal_representative="王五"
            ),
        ]
        result = self._svc(parties).generate({"case_id": 1})[Keys.ENFORCEMENT_RESPONDENT_PARTY]
        blocks = result.split("\n\n")
        assert blocks[0].startswith("被申请人一：被告甲")
        assert blocks[1].startswith("被申请人二：被申请人乙")

    def test_no_respondents_returns_placeholder(self):
        assert self._svc([]).generate({"case_id": 1})[Keys.ENFORCEMENT_RESPONDENT_PARTY] == "被申请人：\n"


class TestEnforcementRespondentNameService:
    def _svc(self, parties):
        from apps.documents.services.placeholders.litigation.enforcement_party_service import (
            EnforcementRespondentNameService,
        )

        svc = EnforcementRespondentNameService()
        svc.case_details_accessor = _accessor(parties)
        return svc

    def test_no_case_id_returns_empty(self):
        assert self._svc([]).generate({}) == {}

    def test_joins_names_with_dunhao(self):
        parties = [
            _party_dict(name="被告甲", legal_status="defendant"),
            _party_dict(name="被申请人乙", legal_status="respondent"),
        ]
        assert self._svc(parties).generate({"case_id": 1})[Keys.ENFORCEMENT_RESPONDENT_NAME] == "被告甲、被申请人乙"

    def test_no_respondents_returns_empty(self):
        assert self._svc([]).generate({"case_id": 1})[Keys.ENFORCEMENT_RESPONDENT_NAME] == ""


# ── enforcement_signature ───────────────────────────────────────────


class TestEnforcementSignatureService:
    def _svc(self, parties):
        from apps.documents.services.placeholders.litigation.enforcement_signature_service import (
            EnforcementSignatureService,
        )

        svc = EnforcementSignatureService()
        svc.case_details_accessor = _accessor(parties)
        return svc

    def test_no_case_id_returns_empty(self):
        assert self._svc([]).generate({}) == {}

    def test_applicant_natural_and_legal_blocks(self):
        parties = [
            _party_dict(name="申请人甲", legal_status="applicant"),
            _party_dict(
                name="申请人公司", legal_status="applicant", client_type="enterprise", legal_representative="李四"
            ),
        ]
        result = self._svc(parties).generate({"case_id": 1})["强制执行申请书签名盖章信息"]
        blocks = result.split("\n\n")
        assert blocks[0] == "申请人（签名+指模）：申请人甲\n日期：2026年01月02日"
        assert "申请人（盖章）：申请人公司" in blocks[1]

    def test_plaintiff_counts_as_applicant(self):
        parties = [_party_dict(name="原告甲", legal_status="plaintiff")]
        result = self._svc(parties).generate({"case_id": 1})["强制执行申请书签名盖章信息"]
        assert "申请人（签名+指模）：原告甲" in result

    def test_no_applicants_returns_empty(self):
        assert self._svc([]).generate({"case_id": 1})["强制执行申请书签名盖章信息"] == ""


# ── enforcement_judgment ────────────────────────────────────────────


class TestEnforcementJudgmentMainTextService:
    def _svc(self, case_numbers):
        from apps.documents.services.placeholders.litigation.enforcement_judgment_service import (
            EnforcementJudgmentMainTextService,
        )

        svc = EnforcementJudgmentMainTextService()
        svc.case_details_accessor = MagicMock()
        svc.case_details_accessor.require_case_details.return_value = {"case_numbers": case_numbers}
        return svc

    def test_no_case_id_returns_blank(self):
        assert self._svc([]).generate({})[Keys.ENFORCEMENT_JUDGMENT_MAIN_TEXT] == ""

    def test_case_object_id_used(self):
        svc = self._svc([{"is_active": True, "document_content": "生效主文"}])
        assert svc.generate({"case": SimpleNamespace(id=3)})[Keys.ENFORCEMENT_JUDGMENT_MAIN_TEXT] == "生效主文"

    def test_prefers_active_case_number(self):
        svc = self._svc(
            [
                {"is_active": False, "document_content": "一审主文"},
                {"is_active": True, "document_content": "二审主文"},
            ]
        )
        assert svc.get_judgment_main_text(1) == "二审主文"

    def test_joins_inactive_contents(self):
        svc = self._svc(
            [
                {"is_active": False, "document_content": "一审主文"},
                {"is_active": False, "document_content": "二审主文"},
            ]
        )
        assert svc.get_judgment_main_text(1) == "一审主文\n二审主文"

    def test_no_content_returns_empty(self):
        assert self._svc([{"is_active": True, "document_content": ""}]).get_judgment_main_text(1) == ""


# ── enforcement_media_publication ───────────────────────────────────


class TestEnforcementMediaPublicationService:
    def _svc(self, parties):
        from apps.documents.services.placeholders.litigation.enforcement_media_publication_service import (
            EnforcementMediaPublicationRequestService,
        )

        svc = EnforcementMediaPublicationRequestService()
        svc.case_details_accessor = _accessor(parties)
        return svc

    def test_no_case_id_returns_empty(self):
        assert self._svc([]).generate({}) == {}

    def test_builds_publication_request_text(self):
        parties = [
            _party_dict(name="被告甲", legal_status="defendant"),
            _party_dict(name="被申请人乙", legal_status="respondent"),
        ]
        result = self._svc(parties).generate({"case_id": 1})[Keys.ENFORCEMENT_MEDIA_PUBLICATION_REQUEST]
        assert result.startswith("请求贵院依法将被申请人被告甲、被申请人乙")
        assert result.endswith("通过报纸、广播、电视、互联网等媒体公布。")

    def test_dedupes_names(self):
        parties = [
            _party_dict(name="被告甲", legal_status="defendant"),
            _party_dict(name="被告甲", legal_status="respondent"),
        ]
        result = self._svc(parties).generate({"case_id": 1})[Keys.ENFORCEMENT_MEDIA_PUBLICATION_REQUEST]
        assert "被告甲、被告甲" not in result

    def test_no_respondents_returns_blank(self):
        assert self._svc([]).generate({"case_id": 1})[Keys.ENFORCEMENT_MEDIA_PUBLICATION_REQUEST] == ""


# ── enforcement exit/spending restriction ───────────────────────────


class TestEnforcementExitRestrictionService:
    def _svc(self, parties):
        from apps.documents.services.placeholders.litigation.enforcement_exit_restriction_service import (
            EnforcementExitRestrictionRequestService,
        )

        svc = EnforcementExitRestrictionRequestService()
        svc.case_details_accessor = _accessor(parties)
        return svc

    def test_no_case_id_returns_empty(self):
        assert self._svc([]).generate({}) == {}

    def test_builds_company_and_legal_rep_segments(self):
        parties = [
            _party_dict(
                name="甲公司", legal_status="respondent", client_type="enterprise", legal_representative="王五"
            ),
            _party_dict(name="自然人乙", legal_status="respondent", client_type="natural"),
        ]
        result = self._svc(parties).generate({"case_id": 1})[Keys.ENFORCEMENT_EXIT_RESTRICTION_REQUEST]
        assert "甲公司的法定代表人王五、自然人乙" in result
        assert result.startswith("请求贵院依法决定对被申请人")

    def test_natural_person_same_as_legal_rep_not_duplicated(self):
        parties = [
            _party_dict(
                name="甲公司", legal_status="respondent", client_type="enterprise", legal_representative="王五"
            ),
            _party_dict(name="王五", legal_status="respondent", client_type="natural"),
        ]
        result = self._svc(parties).generate({"case_id": 1})[Keys.ENFORCEMENT_EXIT_RESTRICTION_REQUEST]
        assert result.count("王五") == 1

    def test_no_respondents_returns_blank(self):
        assert self._svc([]).generate({"case_id": 1})[Keys.ENFORCEMENT_EXIT_RESTRICTION_REQUEST] == ""


class TestEnforcementSpendingRestrictionService:
    def _svc(self, parties):
        from apps.documents.services.placeholders.litigation.enforcement_spending_restriction_service import (
            EnforcementSpendingRestrictionRequestService,
        )

        svc = EnforcementSpendingRestrictionRequestService()
        svc.case_details_accessor = _accessor(parties)
        return svc

    def test_no_case_id_returns_empty(self):
        assert self._svc([]).generate({}) == {}

    def test_builds_spending_restriction_text(self):
        parties = [
            _party_dict(
                name="甲公司", legal_status="respondent", client_type="enterprise", legal_representative="王五"
            ),
            _party_dict(name="自然人乙", legal_status="respondent", client_type="natural"),
        ]
        result = self._svc(parties).generate({"case_id": 1})[Keys.ENFORCEMENT_SPENDING_RESTRICTION_REQUEST]
        assert "甲公司及其法定代表人王五、自然人乙" in result
        assert result.endswith("采取高消费限制令。")

    def test_company_without_legal_rep(self):
        parties = [
            _party_dict(name="甲公司", legal_status="respondent", client_type="enterprise", legal_representative="")
        ]
        result = self._svc(parties).generate({"case_id": 1})[Keys.ENFORCEMENT_SPENDING_RESTRICTION_REQUEST]
        assert "对被申请人甲公司采取" in result

    def test_no_respondents_returns_blank(self):
        assert self._svc([]).generate({"case_id": 1})[Keys.ENFORCEMENT_SPENDING_RESTRICTION_REQUEST] == ""


# ── enforcement_applicant_property_clue ─────────────────────────────


class TestEnforcementApplicantPropertyClueService:
    @contextmanager
    def _patched(self, plaintiff_dtos, applicant_dtos, clues):
        from apps.documents.services.placeholders.litigation.enforcement_applicant_property_clue_service import (
            EnforcementApplicantPropertyClueService,
        )

        client_service = MagicMock()
        client_service.get_property_clues_by_client_internal.side_effect = lambda cid: clues.get(cid, [])
        case_service = MagicMock()
        case_service.get_case_parties_internal.side_effect = lambda case_id, legal_status: (
            plaintiff_dtos if legal_status == LegalStatus.PLAINTIFF else applicant_dtos
        )
        with (
            patch(f"{WIRING}.get_client_service", return_value=client_service),
            patch(f"{WIRING}.get_case_service", return_value=case_service),
        ):
            yield EnforcementApplicantPropertyClueService(), case_service

    def test_no_case_id_returns_blank(self):
        with self._patched([], {}, {}) as (svc, _cs):
            assert svc.generate({})[Keys.ENFORCEMENT_APPLICANT_PROPERTY_CLUE] == ""

    def test_collects_stripped_lines(self):
        clue = SimpleNamespace(content="  房产一处\n\n车辆一台  ")
        dtos = [SimpleNamespace(client_id=7)]
        with self._patched(dtos, [], {7: [clue]}) as (svc, _cs):
            result = svc.generate({"case_id": 1})[Keys.ENFORCEMENT_APPLICANT_PROPERTY_CLUE]
        assert result == "房产一处\a车辆一台"

    def test_falls_back_to_applicant_status(self):
        clue = SimpleNamespace(content="银行存款")
        applicant_dtos = [SimpleNamespace(client_id=8)]
        with self._patched([], applicant_dtos, {8: [clue]}) as (svc, case_service):
            result = svc.generate({"case_id": 1})[Keys.ENFORCEMENT_APPLICANT_PROPERTY_CLUE]
        assert result == "银行存款"
        statuses = [call.kwargs.get("legal_status") for call in case_service.get_case_parties_internal.call_args_list]
        assert statuses == [LegalStatus.PLAINTIFF, LegalStatus.APPLICANT]

    def test_no_applicants_returns_empty(self):
        with self._patched([], [], {}) as (svc, _cs):
            assert svc.generate({"case_id": 1})[Keys.ENFORCEMENT_APPLICANT_PROPERTY_CLUE] == ""


# ── preservation 系列 ───────────────────────────────────────────────


class TestPreservationPartyService:
    def _svc(self, parties):
        from apps.documents.services.placeholders.litigation.preservation_party_service import PreservationPartyService

        svc = PreservationPartyService()
        svc.case_details_accessor = _accessor(parties)
        return svc

    def test_no_case_id_returns_blank(self):
        assert self._svc([]).generate({})["财产保全申请书当事人信息"] == ""

    def test_remaps_roles_and_excludes_third_party(self):
        parties = [
            _party_dict(name="原告甲", legal_status="plaintiff"),
            _party_dict(name="被告乙", legal_status="defendant", client_type="enterprise", legal_representative="王五"),
            _party_dict(name="第三人丙", legal_status="third"),
        ]
        result = self._svc(parties).generate({"case_id": 1})["财产保全申请书当事人信息"]
        assert "申请人：原告甲" in result
        assert "被申请人：被告乙" in result
        assert "第三人" not in result

    def test_no_parties_returns_empty(self):
        assert self._svc([]).generate({"case_id": 1})["财产保全申请书当事人信息"] == ""


class TestPreservationSignatureService:
    def _svc(self, parties):
        from apps.documents.services.placeholders.litigation.preservation_signature_service import (
            PreservationSignatureService,
        )

        svc = PreservationSignatureService()
        svc.case_details_accessor = _accessor(parties)
        return svc

    def test_no_case_id_returns_blank(self):
        assert self._svc([]).generate({})["财产保全申请书签名盖章信息"] == ""

    def test_signature_blocks_with_role_mapping(self):
        parties = [
            _party_dict(name="张三", legal_status="plaintiff"),
            _party_dict(
                name="原告公司", legal_status="plaintiff", client_type="enterprise", legal_representative="李四"
            ),
        ]
        result = self._svc(parties).generate({"case_id": 1})["财产保全申请书签名盖章信息"]
        blocks = result.split("\n\n")
        assert blocks[0] == "申请人（签名+指模）：张三\n日期：2026年01月02日"
        assert "申请人（盖章）：原告公司" in blocks[1]

    def test_third_party_role_kept(self):
        parties = [_party_dict(name="第三人甲", legal_status="third")]
        result = self._svc(parties).generate({"case_id": 1})["财产保全申请书签名盖章信息"]
        assert result.startswith("第三人（签名+指模）：第三人甲")

    def test_no_matching_parties_returns_empty(self):
        assert self._svc([]).generate({"case_id": 1})["财产保全申请书签名盖章信息"] == ""


class TestPreservationAmountService:
    def _svc(self):
        from apps.documents.services.placeholders.litigation.preservation_amount_service import (
            PreservationAmountService,
        )

        return PreservationAmountService()

    def test_no_case_returns_blank(self):
        assert self._svc().generate({})["财产保全申请书保全金额"] == ""

    def test_amount_trailing_zeros_stripped(self):
        case = SimpleNamespace(id=1, preservation_amount="100000.00")
        assert self._svc().generate({"case": case})["财产保全申请书保全金额"] == "100000"

    def test_integer_amount_kept(self):
        case = SimpleNamespace(id=1, preservation_amount=50000)
        assert self._svc().generate({"case": case})["财产保全申请书保全金额"] == "50000"

    def test_missing_amount_returns_blank(self):
        case = SimpleNamespace(id=1)
        assert self._svc().generate({"case": case})["财产保全申请书保全金额"] == ""


# ── case_lawyer ─────────────────────────────────────────────────────


class TestCaseLawyerService:
    def _patch_assignments(self, assignments, exists=True):
        """替身查询集：exists() 可控，迭代返回给定分配列表。"""
        qs = MagicMock()
        qs.exists.return_value = exists
        qs.__iter__.return_value = iter(assignments)
        manager = MagicMock()
        manager.filter.return_value.select_related.return_value = qs
        return patch(f"{LITIGATION}.case_lawyer_service.CaseAssignment", objects=manager)

    def _lawyer(self, license_no="LIC1", phone="13800000000", address="律所地址"):
        return SimpleNamespace(
            license_no=license_no,
            phone=phone,
            law_firm=SimpleNamespace(address=address),
        )

    def test_no_case_id_returns_blanks(self):
        from apps.documents.services.placeholders.litigation.case_lawyer_service import CaseLawyerService

        result = CaseLawyerService().generate({})
        assert result == {Keys.CASE_LAWYER_ID: "", Keys.CASE_LAWYER_PHONE: "", Keys.CASE_LAWYER_ADDRESS: ""}

    def test_no_assignments_returns_blanks(self):
        from apps.documents.services.placeholders.litigation.case_lawyer_service import CaseLawyerService

        with self._patch_assignments([], exists=False):
            result = CaseLawyerService().generate({"case_id": 1})
        assert result == {Keys.CASE_LAWYER_ID: "", Keys.CASE_LAWYER_PHONE: "", Keys.CASE_LAWYER_ADDRESS: ""}

    def test_collects_unique_lawyer_fields(self):
        from apps.documents.services.placeholders.litigation.case_lawyer_service import CaseLawyerService

        assignments = [
            SimpleNamespace(lawyer=self._lawyer("LIC1", "13800000000", "地址A")),
            SimpleNamespace(lawyer=self._lawyer("LIC1", "13900000000", "地址A")),  # 重复证号/地址
            SimpleNamespace(lawyer=None),  # 无律师的分配
        ]
        with self._patch_assignments(assignments):
            result = CaseLawyerService().generate({"case_id": 1})
        assert result[Keys.CASE_LAWYER_ID] == "LIC1"
        assert result[Keys.CASE_LAWYER_PHONE] == "13800000000、13900000000"
        assert result[Keys.CASE_LAWYER_ADDRESS] == "地址A"

    def test_lawyer_without_firm_address_skipped(self):
        from apps.documents.services.placeholders.litigation.case_lawyer_service import CaseLawyerService

        lawyer = SimpleNamespace(license_no="LIC2", phone="", law_firm=SimpleNamespace(address=""))
        with self._patch_assignments([SimpleNamespace(lawyer=lawyer)]):
            result = CaseLawyerService().generate({"case_id": 1})
        assert result[Keys.CASE_LAWYER_ID] == "LIC2"
        assert result[Keys.CASE_LAWYER_PHONE] == ""
        assert result[Keys.CASE_LAWYER_ADDRESS] == ""

    def test_case_object_id_used(self):
        from apps.documents.services.placeholders.litigation.case_lawyer_service import CaseLawyerService

        with self._patch_assignments([SimpleNamespace(lawyer=self._lawyer())]):
            result = CaseLawyerService().generate({"case": SimpleNamespace(id=9)})
        assert result[Keys.CASE_LAWYER_ID] == "LIC1"


# ── filename_service ────────────────────────────────────────────────


class TestFilenameService:
    def _patch_case(self, case):
        case_service = MagicMock()
        case_service.get_case_by_id_internal.return_value = case
        return patch(f"{LITIGATION}.filename_service.get_case_service", return_value=case_service)

    def test_generate_complaint_filename(self):
        from apps.core.services.filename_template_service import FilenameTemplateService
        from apps.documents.services.placeholders.litigation.filename_service import FilenameService

        with (
            self._patch_case(SimpleNamespace(name="王小三案件")),
            patch.object(
                FilenameTemplateService, "render_generated_doc", return_value="起诉状（王小三案件）V1_20260102"
            ) as mock_render,
        ):
            filename = FilenameService().generate_complaint_filename(1)
        assert filename == "起诉状（王小三案件）V1_20260102.docx"
        assert mock_render.call_args.kwargs["doc_type"] == "起诉状"

    def test_generate_defense_filename(self):
        from apps.core.services.filename_template_service import FilenameTemplateService
        from apps.documents.services.placeholders.litigation.filename_service import FilenameService

        with (
            self._patch_case(SimpleNamespace(name="王小三案件")),
            patch.object(
                FilenameTemplateService, "render_generated_doc", return_value="答辩状（王小三案件）V1_20260102"
            ),
        ):
            filename = FilenameService().generate_defense_filename(1)
        assert filename == "答辩状（王小三案件）V1_20260102.docx"

    def test_case_not_found_raises(self):
        from apps.core.exceptions import NotFoundError
        from apps.documents.services.placeholders.litigation.filename_service import FilenameService

        with self._patch_case(None):
            with pytest.raises(NotFoundError):
                FilenameService().generate_complaint_filename(1)

    def test_unnamed_case_falls_back(self):
        from apps.core.services.filename_template_service import FilenameTemplateService
        from apps.documents.services.placeholders.litigation.filename_service import FilenameService

        with (
            self._patch_case(SimpleNamespace(name="")),
            patch.object(
                FilenameTemplateService, "render_generated_doc", return_value="答辩状（未命名案件）V1_20260102"
            ) as mr,
        ):
            FilenameService().generate_defense_filename(1)
        assert mr.call_args.kwargs["case_name"] == "未命名案件"

    def test_format_date_format(self):
        from apps.documents.services.placeholders.litigation.filename_service import FilenameService

        result = FilenameService()._format_date()
        assert len(result) == 8 and result.isdigit()
