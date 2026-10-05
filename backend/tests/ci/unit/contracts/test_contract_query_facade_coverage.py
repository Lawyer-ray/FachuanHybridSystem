"""补充覆盖测试: contracts/services/contract/query/facade.py

覆盖: ContractQueryFacade 的延迟加载 property、list_contracts /
list_contracts_ctx / get_contract / get_contract_ctx 的委托与装配链路。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.contract.query.facade import ContractQueryFacade


def _make_facade() -> tuple[ContractQueryFacade, dict[str, MagicMock]]:
    deps = {
        "query_service": MagicMock(name="query"),
        "access_policy": MagicMock(name="policy"),
        "list_assembler": MagicMock(name="assembler"),
    }
    facade = ContractQueryFacade(
        query_service=deps["query_service"],
        access_policy=deps["access_policy"],
        list_assembler=deps["list_assembler"],
    )
    return facade, deps


# ── 延迟加载 property ─────────────────────────────────────────────


class TestLazyProperties:
    def test_query_service_lazy_created_with_policy(self):
        facade = ContractQueryFacade()
        assert facade._query_service is None
        with (
            patch("apps.contracts.services.contract.query.facade.ContractQueryService") as query_cls,
            patch("apps.contracts.services.contract.query.facade.ContractAccessPolicy") as policy_cls,
        ):
            first = facade.query_service
            second = facade.query_service
        assert first is query_cls.return_value
        assert second is first
        query_cls.assert_called_once_with(access_policy=policy_cls.return_value)

    def test_access_policy_lazy_created(self):
        facade = ContractQueryFacade()
        with patch("apps.contracts.services.contract.query.facade.ContractAccessPolicy") as policy_cls:
            first = facade.access_policy
            second = facade.access_policy
        assert first is policy_cls.return_value
        assert second is first

    def test_list_assembler_lazy_created(self):
        facade = ContractQueryFacade()
        with patch("apps.contracts.services.contract.query.facade.ContractListAssembler") as assembler_cls:
            first = facade.list_assembler
            second = facade.list_assembler
        assert first is assembler_cls.return_value
        assert second is first

    def test_injected_dependencies_returned_as_is(self):
        facade, deps = _make_facade()
        assert facade.query_service is deps["query_service"]
        assert facade.access_policy is deps["access_policy"]
        assert facade.list_assembler is deps["list_assembler"]


# ── get_contract_queryset ─────────────────────────────────────────


class TestGetContractQueryset:
    def test_delegates_to_query_service(self):
        facade, deps = _make_facade()
        qs = MagicMock(name="queryset")
        deps["query_service"].get_contract_queryset.return_value = qs
        assert facade.get_contract_queryset() is qs
        deps["query_service"].get_contract_queryset.assert_called_once_with()


# ── list_contracts ────────────────────────────────────────────────


class TestListContracts:
    def test_enriches_and_returns_list(self):
        facade, deps = _make_facade()
        c1, c2 = MagicMock(name="c1"), MagicMock(name="c2")
        deps["query_service"].list_contracts.return_value = MagicMock(name="qs", __iter__=lambda s: iter([c1, c2]))
        result = facade.list_contracts(case_type="civil", status="active")
        assert result == [c1, c2]
        deps["query_service"].list_contracts.assert_called_once_with(
            case_type="civil",
            status="active",
            search=None,
            fee_mode=None,
            is_filed=None,
            user=None,
            org_access=None,
            perm_open_access=False,
        )
        deps["list_assembler"].enrich.assert_called_once_with([c1, c2])

    def test_all_kwargs_passed_through(self):
        facade, deps = _make_facade()
        user = MagicMock(name="user")
        org_access = {"law_firm_ids": [3]}
        deps["query_service"].list_contracts.return_value = iter([])
        facade.list_contracts(
            case_type="criminal",
            status="archived",
            search="关键字",
            fee_mode="FIXED",
            is_filed=True,
            user=user,
            org_access=org_access,
            perm_open_access=True,
        )
        deps["query_service"].list_contracts.assert_called_once_with(
            case_type="criminal",
            status="archived",
            search="关键字",
            fee_mode="FIXED",
            is_filed=True,
            user=user,
            org_access=org_access,
            perm_open_access=True,
        )


class TestListContractsCtx:
    def test_ctx_path_enriches_and_returns_list(self):
        facade, deps = _make_facade()
        ctx = MagicMock(name="ctx")
        c1 = MagicMock(name="c1")
        deps["query_service"].list_contracts_ctx.return_value = MagicMock(name="qs", __iter__=lambda s: iter([c1]))
        result = facade.list_contracts_ctx(ctx=ctx, case_type="civil", is_filed=False)
        assert result == [c1]
        deps["query_service"].list_contracts_ctx.assert_called_once_with(
            ctx=ctx,
            case_type="civil",
            status=None,
            search=None,
            fee_mode=None,
            is_filed=False,
        )
        deps["list_assembler"].enrich.assert_called_once_with([c1])

    def test_empty_result_no_crash(self):
        facade, deps = _make_facade()
        deps["query_service"].list_contracts_ctx.return_value = MagicMock(name="qs", __iter__=lambda s: iter([]))
        assert facade.list_contracts_ctx(ctx=MagicMock()) == []
        deps["list_assembler"].enrich.assert_called_once_with([])


# ── get_contract / get_contract_ctx ───────────────────────────────


class TestGetContract:
    def test_access_check_and_enrich(self):
        facade, deps = _make_facade()
        contract = MagicMock(name="contract")
        user = MagicMock(name="user")
        org_access = {"law_firm_ids": [4]}
        deps["query_service"].get_contract_internal.return_value = contract
        result = facade.get_contract(7, user=user, org_access=org_access, perm_open_access=True)
        assert result is contract
        deps["query_service"].get_contract_internal.assert_called_once_with(7)
        deps["access_policy"].ensure_access.assert_called_once_with(
            contract_id=7,
            user=user,
            org_access=org_access,
            perm_open_access=True,
            contract=contract,
            message="无权限访问该合同",
        )
        deps["list_assembler"].enrich.assert_called_once_with([contract])

    def test_access_denied_propagates(self):
        from apps.core.exceptions import PermissionDenied

        facade, deps = _make_facade()
        contract = MagicMock(name="contract")
        deps["query_service"].get_contract_internal.return_value = contract
        deps["access_policy"].ensure_access.side_effect = PermissionDenied(
            message="无权限访问该合同", code="CONTRACT_ACCESS_DENIED"
        )
        with pytest.raises(PermissionDenied):
            facade.get_contract(8)
        deps["list_assembler"].enrich.assert_not_called()


class TestGetContractCtx:
    def test_ctx_access_check_and_enrich(self):
        facade, deps = _make_facade()
        contract = MagicMock(name="contract")
        ctx = MagicMock(name="ctx")
        deps["query_service"].get_contract_internal.return_value = contract
        result = facade.get_contract_ctx(contract_id=9, ctx=ctx)
        assert result is contract
        deps["access_policy"].ensure_access_ctx.assert_called_once_with(
            contract_id=9, ctx=ctx, contract=contract, message="无权限访问该合同"
        )
        deps["list_assembler"].enrich.assert_called_once_with([contract])

    def test_ctx_access_denied_propagates(self):
        from apps.core.exceptions import PermissionDenied

        facade, deps = _make_facade()
        deps["query_service"].get_contract_internal.return_value = MagicMock()
        deps["access_policy"].ensure_access_ctx.side_effect = PermissionDenied(
            message="无权限访问该合同", code="CONTRACT_ACCESS_DENIED"
        )
        with pytest.raises(PermissionDenied):
            facade.get_contract_ctx(contract_id=10, ctx=MagicMock())


# ── 真实依赖冒烟: 延迟构造不爆 ────────────────────────────────────


@pytest.mark.django_db
class TestLazyConstructionSmoke:
    def test_defaults_construct_real_services(self):
        facade = ContractQueryFacade()
        # 真实构造仅验证依赖图完整（不发 SQL）
        qs = facade.query_service
        assert qs is facade.query_service
        assert facade.access_policy is not None
        assert facade.list_assembler is not None
