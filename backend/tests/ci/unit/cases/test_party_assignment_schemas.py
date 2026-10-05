"""party_schemas / assignment_schemas 解析器（resolve_*）单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.cases.schemas.assignment_schemas import CaseAssignmentIn, CaseAssignmentOut, CaseAssignmentUpdate
from apps.cases.schemas.party_schemas import CasePartyIn, CasePartyOut, CasePartyUpdate


class TestCasePartyOutResolveClientDetail:
    @staticmethod
    def _client_payload(cid: int) -> dict:
        return {
            "id": cid,
            "name": f"客户{cid}",
            "is_our_client": True,
            "client_type": "legal",
            "client_type_label": "法人",
            "identity_docs": [],
        }

    def test_dict_with_client_detail_key(self) -> None:
        result = CasePartyOut.resolve_client_detail({"client_detail": self._client_payload(1)})
        assert result.id == 1
        assert result.name == "客户1"

    def test_dict_falls_back_to_client_key(self) -> None:
        result = CasePartyOut.resolve_client_detail({"client": self._client_payload(2)})
        assert result.id == 2

    def test_dict_with_client_detail_instance(self) -> None:
        from apps.core.api.schemas_shared import ClientLiteOut

        client = ClientLiteOut(**self._client_payload(3))
        result = CasePartyOut.resolve_client_detail({"client_detail": client})
        assert result is client

    def test_model_with_client_fk(self) -> None:
        """FK 模型走真实 ClientLiteOut.from_model 全链（零 mock，免疫任何类状态污染）。

        此前用类级/名字绑定补丁，全量套件下单进程顺序下补丁会静默失效
        （真实 from_model 执行报 Mock 无 id）——直测真实转换更强也更稳。
        """
        client = SimpleNamespace(
            _meta=object(),  # _meta 标记引导 resolver 走 from_model 分支
            id=7,
            name="测试客户",
            is_our_client=True,
            phone="13800000000",
            address="某市某区",
            client_type="legal",
            id_number=None,
            legal_representative="李代表",
            legal_representative_id_number=None,
            identity_docs=None,
        )
        client_type_display_map = {"legal": "法人"}
        client.get_client_type_display = lambda: client_type_display_map.get(client.client_type, "")
        party = SimpleNamespace(client_detail=None, client=client)

        result = CasePartyOut.resolve_client_detail(party)

        assert result.id == 7
        assert result.name == "测试客户"
        assert result.is_our_client is True
        assert result.client_type_label == "法人"
        assert result.identity_docs == []

    def test_none_client_returned_as_is(self) -> None:
        party = MagicMock()
        party.client_detail = None
        party.client = None
        assert CasePartyOut.resolve_client_detail(party) is None


class TestCasePartyOutResolveLegalStatus:
    def test_model_with_display_method(self) -> None:
        party = MagicMock()
        party.legal_status = "plaintiff"
        party.get_legal_status_display.return_value = "原告"
        assert CasePartyOut.resolve_legal_status(party) == "原告"

    def test_model_blank_legal_status_returns_none(self) -> None:
        party = MagicMock()
        party.legal_status = ""
        assert CasePartyOut.resolve_legal_status(party) is None

    def test_dict_input(self) -> None:
        assert CasePartyOut.resolve_legal_status({"legal_status": "defendant"}) == "defendant"

    def test_plain_object_fallback(self) -> None:
        class Obj:
            legal_status = "third"

        assert CasePartyOut.resolve_legal_status(Obj()) == "third"


class TestCasePartySchemasBasic:
    def test_case_party_in_fields(self) -> None:
        schema = CasePartyIn(case_id=1, client_id=2, legal_status="plaintiff")
        assert schema.case_id == 1
        assert schema.client_id == 2

    def test_case_party_update_optional_fields(self) -> None:
        schema = CasePartyUpdate()
        assert schema.case_id is None
        assert schema.legal_status is None

    def test_case_party_in_legal_status_default_none(self) -> None:
        assert CasePartyIn(case_id=1, client_id=2).legal_status is None


class TestCaseAssignmentOutResolveLawyerDetail:
    def test_dict_with_dict_detail(self) -> None:
        result = CaseAssignmentOut.resolve_lawyer_detail({"lawyer_detail": {"id": 1, "username": "u"}})
        assert result.id == 1
        assert result.username == "u"

    def test_dict_with_precomputed_detail(self) -> None:
        detail = MagicMock()
        result = CaseAssignmentOut.resolve_lawyer_detail({"lawyer_detail": detail})
        assert result is detail

    def test_model_with_lawyer_fk(self) -> None:
        """FK 模型走真实 LawyerOutFromDTO.from_model 全链（零 mock）。"""
        lawyer = SimpleNamespace(_meta=object(), id=3, username="lawyer_3", real_name="王律师", phone="13900000000")
        assignment = SimpleNamespace(lawyer=lawyer, lawyer_detail=None)

        result = CaseAssignmentOut.resolve_lawyer_detail(assignment)

        assert result.id == 3
        assert result.username == "lawyer_3"
        assert result.real_name == "王律师"
        assert result.phone == "13900000000"

    def test_attr_dict_detail_converted(self) -> None:
        obj = MagicMock()
        obj.lawyer = None
        detail = {"id": 5, "username": "lawyer_5"}
        obj.lawyer_detail = detail
        result = CaseAssignmentOut.resolve_lawyer_detail(obj)
        assert result.id == 5
        assert result.username == "lawyer_5"

    def test_lawyer_id_fallback(self) -> None:
        obj = MagicMock()
        obj.lawyer = None
        obj.lawyer_detail = None
        obj.lawyer_id = 42
        result = CaseAssignmentOut.resolve_lawyer_detail(obj)
        assert result.id == 42
        assert result.username == "lawyer_42"

    def test_no_resolution_raises(self) -> None:
        obj = MagicMock()
        obj.lawyer = None
        obj.lawyer_detail = None
        obj.lawyer_id = None
        with pytest.raises(ValueError, match="无法解析 lawyer_detail"):
            CaseAssignmentOut.resolve_lawyer_detail(obj)


class TestCaseAssignmentSchemasBasic:
    def test_case_assignment_in_fields(self) -> None:
        schema = CaseAssignmentIn(case_id=3, lawyer_id=4)
        assert schema.case_id == 3
        assert schema.lawyer_id == 4

    def test_case_assignment_update_optional(self) -> None:
        schema = CaseAssignmentUpdate()
        assert schema.case_id is None
        assert schema.lawyer_id is None
