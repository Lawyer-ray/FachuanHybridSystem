"""CaseInternalQueryService 单元测试。

覆盖 get_case_internal 异常分支、各委托方法的透传，以及
search_cases_for_binding_internal 的真实 DB 检索与访问过滤。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from apps.cases.models import CaseNumber, CaseParty
from apps.cases.services.case.case_internal_query_service import CaseInternalQueryService
from apps.core.exceptions import NotFoundError
from apps.testing.factories import CaseFactory, ClientFactory, LawyerFactory


def _make_service() -> tuple[CaseInternalQueryService, MagicMock]:
    orchestrator = MagicMock()
    service = CaseInternalQueryService(orchestrator=orchestrator)
    return service, orchestrator


class TestOrchestratorLazyInit:
    def test_orchestrator_lazy_created_once(self) -> None:
        """未注入 orchestrator 时延迟构造并复用同一实例。"""
        service = CaseInternalQueryService()
        first = service.orchestrator
        assert first is not None
        assert service.orchestrator is first


class TestGetCaseInternal:
    def test_returns_dto(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.get_case.return_value = "case-dto"
        assert service.get_case_internal(11) == "case-dto"
        orchestrator.get_case.assert_called_once_with(11)

    def test_not_found_returns_none(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.get_case.side_effect = NotFoundError("案件不存在")
        assert service.get_case_internal(404) is None

    def test_unexpected_error_reraised(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.get_case.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError, match="boom"):
            service.get_case_internal(1)


class TestDelegation:
    """各 internal 方法按签名委托给 orchestrator 并透传返回值。"""

    def test_get_cases_by_contract_internal(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.get_cases_by_contract.return_value = ["dto"]
        assert service.get_cases_by_contract_internal(7) == ["dto"]
        orchestrator.get_cases_by_contract.assert_called_once_with(7)

    def test_get_cases_by_ids_internal(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.get_cases_by_ids.return_value = ["dto1", "dto2"]
        assert service.get_cases_by_ids_internal([1, 2]) == ["dto1", "dto2"]
        orchestrator.get_cases_by_ids.assert_called_once_with([1, 2])

    def test_validate_case_active_internal(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.validate_case_active.return_value = True
        assert service.validate_case_active_internal(3) is True
        orchestrator.validate_case_active.assert_called_once_with(3)

    def test_get_case_current_stage_internal(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.get_case_current_stage.return_value = "first_instance"
        assert service.get_case_current_stage_internal(3) == "first_instance"
        orchestrator.get_case_current_stage.assert_called_once_with(3)

    def test_check_case_access_internal(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.check_case_access.return_value = False
        assert service.check_case_access_internal(3, 9) is False
        orchestrator.check_case_access.assert_called_once_with(3, 9)

    def test_get_primary_lawyer_names_by_case_ids_internal(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.get_primary_lawyer_names_by_case_ids.return_value = {1: "张三"}
        assert service.get_primary_lawyer_names_by_case_ids_internal([1]) == {1: "张三"}
        orchestrator.get_primary_lawyer_names_by_case_ids.assert_called_once_with([1])

    def test_get_primary_case_numbers_by_case_ids_internal(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.get_primary_case_numbers_by_case_ids.return_value = {1: "(2026)京01民初1号"}
        assert service.get_primary_case_numbers_by_case_ids_internal([1]) == {1: "(2026)京01民初1号"}
        orchestrator.get_primary_case_numbers_by_case_ids.assert_called_once_with([1])

    def test_search_cases_by_party_internal(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.search_cases_by_party.return_value = ["dto"]
        assert service.search_cases_by_party_internal(["张三"], status="active") == ["dto"]
        orchestrator.search_cases_by_party.assert_called_once_with(["张三"], status="active")

    def test_get_case_numbers_by_case_internal(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.get_case_numbers_by_case.return_value = ["n1"]
        assert service.get_case_numbers_by_case_internal(5) == ["n1"]
        orchestrator.get_case_numbers_by_case.assert_called_once_with(5)

    def test_get_case_party_names_internal(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.get_case_party_names.return_value = ["张三"]
        assert service.get_case_party_names_internal(5) == ["张三"]
        orchestrator.get_case_party_names.assert_called_once_with(5)

    def test_search_cases_by_case_number_internal(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.search_cases_by_case_number.return_value = ["dto"]
        assert service.search_cases_by_case_number_internal("（2026）京01民初1号") == ["dto"]
        orchestrator.search_cases_by_case_number.assert_called_once_with("（2026）京01民初1号")

    def test_list_cases_internal(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.list_cases.return_value = ["dto"]
        result = service.list_cases_internal(status="active", limit=5, order_by="-created_at")
        assert result == ["dto"]
        orchestrator.list_cases.assert_called_once_with(status="active", limit=5, order_by="-created_at")

    def test_search_cases_internal(self) -> None:
        service, orchestrator = _make_service()
        orchestrator.search_cases.return_value = ["dto"]
        assert service.search_cases_internal("合同", status="active", limit=10) == ["dto"]
        orchestrator.search_cases.assert_called_once_with(query="合同", status="active", limit=10)


@pytest.mark.django_db
class TestSearchCasesForBindingInternal:
    """真实 DB 检索：默认在办列表、名称/案号/当事人搜索、limit 与权限过滤。"""

    def _make_case_with_party(self, name: str, number: str | None = None, client_name: str = "甲公司") -> Any:
        case = CaseFactory(name=name)
        client = ClientFactory(name=client_name)
        CaseParty.objects.create(case=case, client=client, legal_status="plaintiff")
        if number:
            CaseNumber.objects.create(case=case, number=number)
        return case

    def test_empty_term_returns_active_cases_desc(self) -> None:
        case_old = self._make_case_with_party("案件A", client_name="客户A")
        case_new = self._make_case_with_party("案件B", client_name="客户B")

        results = CaseInternalQueryService().search_cases_for_binding_internal(search_term="  ", perm_open_access=True)

        assert [r["id"] for r in results] == [case_new.id, case_old.id]
        first = results[0]
        assert first["name"] == "案件B"
        assert first["parties"] == ["客户B"]
        assert first["case_numbers"] == []
        assert first["created_at"] is not None

    def test_search_by_name(self) -> None:
        target = self._make_case_with_party("张三诉李四案", client_name="张三")
        self._make_case_with_party("无关案件", client_name="王五")

        results = CaseInternalQueryService().search_cases_for_binding_internal(
            search_term="张三诉李四", perm_open_access=True
        )

        assert [r["id"] for r in results] == [target.id]

    def test_search_by_case_number(self) -> None:
        target = self._make_case_with_party("案号案件", number="（2026）粤06民终100号")
        self._make_case_with_party("其他案件", client_name="其他客户")

        results = CaseInternalQueryService().search_cases_for_binding_internal(
            search_term="粤06民终100", perm_open_access=True
        )

        assert [r["id"] for r in results] == [target.id]
        assert results[0]["case_numbers"] == ["（2026）粤06民终100号"]

    def test_search_by_party_name(self) -> None:
        target = self._make_case_with_party("当事人案件", client_name="乙有限公司")
        self._make_case_with_party("无关案件", client_name="丙公司")

        results = CaseInternalQueryService().search_cases_for_binding_internal(
            search_term="乙有限公司", perm_open_access=True
        )

        assert [r["id"] for r in results] == [target.id]

    def test_limit_clamped_and_applied(self) -> None:
        for i in range(3):
            self._make_case_with_party(f"限流案件{i}", client_name=f"客户{i}")

        results = CaseInternalQueryService().search_cases_for_binding_internal(
            search_term="", limit=2, perm_open_access=True
        )
        assert len(results) == 2

    def test_user_without_access_sees_nothing(self) -> None:
        """非管理员用户未被指派案件时，默认列表被访问策略清空。"""
        self._make_case_with_party("受限案件", client_name="受限客户")
        stranger = LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}")

        results = CaseInternalQueryService().search_cases_for_binding_internal(
            search_term="", user=stranger, org_access=None, perm_open_access=False
        )

        assert results == []

    def test_assigned_user_sees_case(self) -> None:
        from apps.cases.models import CaseAssignment

        case = self._make_case_with_party("指派案件", client_name="指派客户")
        lawyer = LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}")
        CaseAssignment.objects.create(case=case, lawyer=lawyer)

        results = CaseInternalQueryService().search_cases_for_binding_internal(
            search_term="", user=lawyer, org_access=None, perm_open_access=False
        )

        assert [r["id"] for r in results] == [case.id]
