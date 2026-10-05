"""案件查询侧低覆盖服务测试。

覆盖 CaseDetailsQueryService / CaseSearchServiceAdapter / CasePartyInternalQueryService。
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from apps.cases.models import CaseAssignment, CaseNumber, CaseParty
from apps.cases.services.case.case_details_query_service import CaseDetailsQueryService
from apps.cases.services.case.case_party_internal_query_service import CasePartyInternalQueryService
from apps.cases.services.case.case_search_service_adapter import CaseSearchServiceAdapter
from apps.testing.factories import CaseFactory, ClientFactory, LawyerFactory


@pytest.mark.django_db
class TestCaseDetailsQueryService:
    def _make_case(self) -> tuple:
        from apps.cases.models import SupervisingAuthority

        case = CaseFactory(name="张三诉李四案", cause_of_action="合同纠纷", target_amount="10000.50")
        client = ClientFactory(name="张三", client_type="natural", is_our_client=True)
        CaseParty.objects.create(case=case, client=client, legal_status="plaintiff")
        CaseNumber.objects.create(case=case, number="（2026）京01民初1号", remarks="一审案号", is_active=True)
        lawyer = LawyerFactory(real_name="王律师", username=f"lawyer-{uuid4().hex[:8]}")
        CaseAssignment.objects.create(case=case, lawyer=lawyer)
        SupervisingAuthority.objects.create(case=case, name="北京市第一中级人民法院")
        return case, client, lawyer

    def test_get_case_model_internal_found(self) -> None:
        case, _, _ = self._make_case()
        assert CaseDetailsQueryService().get_case_model_internal(case.id).name == "张三诉李四案"

    def test_get_case_model_internal_missing(self) -> None:
        assert CaseDetailsQueryService().get_case_model_internal(99999) is None

    def test_get_case_with_details_full_payload(self) -> None:
        case, client, lawyer = self._make_case()

        payload = CaseDetailsQueryService().get_case_with_details_internal(case.id)

        assert payload is not None
        assert payload["id"] == case.id
        assert payload["name"] == "张三诉李四案"
        assert payload["case_parties"] == [
            {
                "id": payload["case_parties"][0]["id"],
                "client_id": client.id,
                "client_name": "张三",
                "client_type": "natural",
                "id_number": None,
                "legal_representative": "",
                "address": "",
                "phone": "",
                "legal_status": "plaintiff",
                "is_our_client": True,
            }
        ]
        assert payload["case_numbers"][0]["number"] == "（2026）京01民初1号"
        assert payload["case_numbers"][0]["is_active"] is True
        assert payload["case_numbers"][0]["remarks"] == "一审案号"
        assert payload["assignments"][0]["lawyer_id"] == lawyer.id
        assert payload["assignments"][0]["lawyer_name"] == "王律师"
        assert payload["assignments"][0]["law_firm_name"] is None
        assert payload["supervising_authorities"][0]["name"] == "北京市第一中级人民法院"
        assert payload["target_amount"] == 10000.5
        assert payload["preservation_amount"] is None
        assert payload["contract_name"] is not None

    def test_get_case_with_details_missing_case(self) -> None:
        assert CaseDetailsQueryService().get_case_with_details_internal(99999) is None


@pytest.mark.django_db
class TestCaseSearchServiceAdapter:
    def _make_case(self, name: str, number: str | None = None, client_name: str | None = None):
        case = CaseFactory(name=name)
        if client_name:
            CaseParty.objects.create(case=case, client=ClientFactory(name=client_name), legal_status="plaintiff")
        if number:
            CaseNumber.objects.create(case=case, number=number)
        return case

    def test_empty_query_returns_recent_cases(self) -> None:
        first = self._make_case("案件一")
        second = self._make_case("案件二")

        results = CaseSearchServiceAdapter().search_cases("")

        assert [r.id for r in results] == [second.id, first.id]
        assert results[0].name == "案件二"
        assert results[0].case_numbers == []
        assert results[0].parties == []
        assert results[0].created_at is not None

    def test_search_by_name(self) -> None:
        target = self._make_case("合同纠纷案件")
        self._make_case("无关案件")

        results = CaseSearchServiceAdapter().search_cases("合同纠纷")

        assert [r.id for r in results] == [target.id]

    def test_search_by_number(self) -> None:
        target = self._make_case("案号案件", number="（2026）粤06民终55号")
        self._make_case("其他案件")

        results = CaseSearchServiceAdapter().search_cases("粤06民终55")

        assert [r.id for r in results] == [target.id]
        assert results[0].case_numbers == ["（2026）粤06民终55号"]

    def test_search_by_party_name(self) -> None:
        target = self._make_case("当事人案件", client_name="乙公司")
        self._make_case("无关案件", client_name="丙公司")

        results = CaseSearchServiceAdapter().search_cases("乙公司")

        assert [r.id for r in results] == [target.id]
        assert results[0].parties == ["乙公司"]

    def test_limit_applied(self) -> None:
        for i in range(3):
            self._make_case(f"限量案件{i}")
        results = CaseSearchServiceAdapter().search_cases("", limit=2)
        assert len(results) == 2

    def test_limit_clamped_to_20(self) -> None:
        for i in range(25):
            self._make_case(f"clamp-{i:02d}")
        results = CaseSearchServiceAdapter().search_cases("", limit=100)
        assert len(results) == 20


@pytest.mark.django_db
class TestCasePartyInternalQueryService:
    def _make_parties(self):
        case = CaseFactory()
        our = ClientFactory(name="我方客户", is_our_client=True)
        opponent = ClientFactory(name="对方客户", is_our_client=False)
        CaseParty.objects.create(case=case, client=our, legal_status="plaintiff")
        CaseParty.objects.create(case=case, client=opponent, legal_status="defendant")
        return case, our, opponent

    def test_by_legal_status_returns_names(self) -> None:
        case, _, opponent = self._make_parties()
        result = CasePartyInternalQueryService().get_case_parties_by_legal_status_internal(case.id, "defendant")
        assert result == ["对方客户"]

    def test_by_legal_status_empty(self) -> None:
        case, _, _ = self._make_parties()
        assert CasePartyInternalQueryService().get_case_parties_by_legal_status_internal(case.id, "third") == []

    def test_internal_returns_all_parties(self) -> None:
        case, our, opponent = self._make_parties()
        result = CasePartyInternalQueryService().get_case_parties_internal(case.id)
        assert len(result) == 2
        by_client = {dto.client_id: dto for dto in result}
        our_dto = by_client[our.id]
        assert our_dto.client_name == "我方客户"
        assert our_dto.client_type == "legal"
        assert our_dto.legal_status == "plaintiff"
        assert our_dto.is_our_client is True
        opponent_dto = by_client[opponent.id]
        assert opponent_dto.is_our_client is False

    def test_internal_filters_by_legal_status(self) -> None:
        case, _, opponent = self._make_parties()
        result = CasePartyInternalQueryService().get_case_parties_internal(case.id, legal_status="defendant")
        assert [dto.client_id for dto in result] == [opponent.id]

    def test_internal_missing_case_returns_empty(self) -> None:
        assert CasePartyInternalQueryService().get_case_parties_internal(99999) == []


@pytest.mark.django_db
class TestCasePartyInternalQueryErrorPaths:
    """ORM 异常路径：记录日志后原样抛出。"""

    def test_by_legal_status_error_reraised(self) -> None:
        with patch(
            "apps.cases.services.case.case_party_internal_query_service.CaseParty.objects.filter",
            side_effect=RuntimeError("db down"),
        ):
            with pytest.raises(RuntimeError, match="db down"):
                CasePartyInternalQueryService().get_case_parties_by_legal_status_internal(1, "plaintiff")

    def test_internal_error_reraised(self) -> None:
        with patch(
            "apps.cases.services.case.case_party_internal_query_service.CaseParty.objects.select_related",
            side_effect=RuntimeError("db down"),
        ):
            with pytest.raises(RuntimeError, match="db down"):
                CasePartyInternalQueryService().get_case_parties_internal(1)
