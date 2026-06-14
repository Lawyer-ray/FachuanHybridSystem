"""Unit tests for contracts.services.contract.mutation.facade."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import PermissionDenied


class TestContractMutationFacadeInit:
    """Test constructor defaults."""

    def test_init_with_defaults(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        assert facade._mutation_service is None
        assert facade._workflow_service is None
        assert facade._finance_mutation_service is None
        assert facade._access_policy is None

    def test_init_with_all_services(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        ms = MagicMock()
        ws = MagicMock()
        fms = MagicMock()
        ap = MagicMock()
        facade = ContractMutationFacade(
            mutation_service=ms,
            workflow_service=ws,
            finance_mutation_service=fms,
            access_policy=ap,
        )
        assert facade._mutation_service is ms
        assert facade._workflow_service is ws
        assert facade._finance_mutation_service is fms
        assert facade._access_policy is ap


class TestContractMutationFacadeMutationServiceProperty:
    """mutation_service property tests."""

    def test_raises_if_not_set(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        with pytest.raises(RuntimeError, match="requires mutation_service"):
            _ = facade.mutation_service

    def test_returns_set_value(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        ms = MagicMock()
        facade = ContractMutationFacade(mutation_service=ms)
        assert facade.mutation_service is ms


class TestContractMutationFacadeWorkflowServiceProperty:
    """workflow_service property tests."""

    def test_raises_if_not_set(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        with pytest.raises(RuntimeError, match="requires workflow_service"):
            _ = facade.workflow_service

    def test_returns_set_value(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        ws = MagicMock()
        facade = ContractMutationFacade(workflow_service=ws)
        assert facade.workflow_service is ws


class TestContractMutationFacadeFinanceMutationServiceProperty:
    """finance_mutation_service property tests."""

    def test_raises_if_not_set(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        with pytest.raises(RuntimeError, match="requires finance_mutation_service"):
            _ = facade.finance_mutation_service

    def test_returns_set_value(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        fms = MagicMock()
        facade = ContractMutationFacade(finance_mutation_service=fms)
        assert facade.finance_mutation_service is fms


class TestContractMutationFacadeQueryServiceProperty:
    """query_service property tests."""

    def test_raises_if_not_set(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        with pytest.raises(RuntimeError, match="requires query_service"):
            _ = facade.query_service

    def test_returns_set_value(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        qs = MagicMock()
        facade = ContractMutationFacade(query_service=qs)
        assert facade.query_service is qs


class TestContractMutationFacadeAccessPolicyProperty:
    """access_policy lazy init."""

    def test_creates_on_access(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        with patch(
            "apps.contracts.services.contract.domain.ContractAccessPolicy"
        ) as mock_ap:
            mock_ap.return_value = MagicMock()
            result = facade.access_policy
            mock_ap.assert_called_once()


class TestContractMutationFacadeAdminMutationServiceProperty:
    """admin_mutation_service lazy init."""

    def test_creates_on_access(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        with patch(
            "apps.contracts.services.contract.admin.ContractAdminMutationService"
        ) as mock_ams:
            mock_ams.return_value = MagicMock()
            result = facade.admin_mutation_service
            mock_ams.assert_called_once()


class TestContractMutationFacadeCreateContractWithCases:
    """create_contract_with_cases tests."""

    def test_permission_denied_if_not_authorized(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        facade._access_policy = MagicMock()
        facade._access_policy.can_create_contract.return_value = False

        with pytest.raises(PermissionDenied, match="未登录用户无权限"):
            facade.create_contract_with_cases(
                contract_data={"name": "test"},
                user=None,
            )

    def test_delegates_to_workflow(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        facade._access_policy = MagicMock()
        facade._access_policy.can_create_contract.return_value = True
        facade._workflow_service = MagicMock()
        expected = MagicMock()
        facade._workflow_service.create_contract_with_cases.return_value = expected

        result = facade.create_contract_with_cases(
            contract_data={"name": "test"},
            cases_data=[],
            assigned_lawyer_ids=[],
            payments_data=[],
            confirm_finance=False,
            user=MagicMock(),
        )
        assert result is expected


class TestContractMutationFacadeUpdateContractWithFinance:
    """update_contract_with_finance tests."""

    def test_delegates(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        facade._access_policy = MagicMock()
        facade._finance_mutation_service = MagicMock()
        expected = MagicMock()
        facade._finance_mutation_service.update_contract_with_finance.return_value = expected

        result = facade.update_contract_with_finance(
            contract_id=1,
            update_data={"name": "x"},
            user=MagicMock(),
        )
        assert result is expected
        facade._access_policy.ensure_access.assert_called_once()


class TestContractMutationFacadeUpdateContractLawyers:
    """update_contract_lawyers tests."""

    def test_delegates(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        facade._access_policy = MagicMock()
        facade._mutation_service = MagicMock()
        facade._query_service = MagicMock()
        contract = MagicMock()
        facade._query_service.get_contract_internal.return_value = contract

        result = facade.update_contract_lawyers(
            contract_id=1,
            lawyer_ids=[10, 20],
            user=MagicMock(),
        )
        facade._mutation_service.update_contract_lawyers.assert_called_once_with(1, [10, 20])
        assert result is contract


class TestContractMutationFacadeDeleteContract:
    """delete_contract tests."""

    def test_delegates(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        facade._access_policy = MagicMock()
        facade._mutation_service = MagicMock()

        facade.delete_contract(contract_id=1, user=MagicMock())
        facade._mutation_service.delete_contract.assert_called_once_with(1)


class TestContractMutationFacadeDuplicateContract:
    """duplicate_contract tests."""

    def test_delegates(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        facade._access_policy = MagicMock()
        facade._admin_mutation_service = MagicMock()
        expected = MagicMock()
        facade._admin_mutation_service.duplicate_contract.return_value = expected

        result = facade.duplicate_contract(contract_id=1, user=MagicMock())
        assert result is expected


class TestContractMutationFacadeRenewAdvisorContract:
    """renew_advisor_contract tests."""

    def test_delegates(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        facade._access_policy = MagicMock()
        facade._admin_mutation_service = MagicMock()
        expected = MagicMock()
        facade._admin_mutation_service.renew_advisor_contract.return_value = expected

        result = facade.renew_advisor_contract(contract_id=1, user=MagicMock())
        assert result is expected


class TestContractMutationFacadeCreateCaseFromContract:
    """create_case_from_contract tests."""

    def test_delegates(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        facade._access_policy = MagicMock()
        facade._admin_mutation_service = MagicMock()
        expected = MagicMock()
        facade._admin_mutation_service.create_case_from_contract.return_value = expected

        result = facade.create_case_from_contract(
            contract_id=1,
            user=MagicMock(),
            org_access=None,
            perm_open_access=False,
        )
        assert result is expected


class TestContractMutationFacadeCtxVariants:
    """Context variants (xxx_ctx methods) tests."""

    def test_create_contract_with_cases_ctx(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        facade._access_policy = MagicMock()
        facade._access_policy.can_create_contract.return_value = True
        facade._workflow_service = MagicMock()
        expected = MagicMock()
        facade._workflow_service.create_contract_with_cases.return_value = expected

        ctx = MagicMock()
        ctx.user = MagicMock()
        ctx.org_access = {}
        ctx.perm_open_access = False

        result = facade.create_contract_with_cases_ctx(
            contract_data={"name": "x"},
            ctx=ctx,
        )
        assert result is expected

    def test_delete_contract_ctx(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        facade._access_policy = MagicMock()
        facade._mutation_service = MagicMock()

        ctx = MagicMock()
        ctx.user = MagicMock()
        ctx.org_access = {}
        ctx.perm_open_access = False

        facade.delete_contract_ctx(contract_id=1, ctx=ctx)
        facade._mutation_service.delete_contract.assert_called_once_with(1)

    def test_duplicate_contract_ctx(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        facade._access_policy = MagicMock()
        facade._admin_mutation_service = MagicMock()
        expected = MagicMock()
        facade._admin_mutation_service.duplicate_contract.return_value = expected

        ctx = MagicMock()
        ctx.user = MagicMock()
        ctx.org_access = {}
        ctx.perm_open_access = False

        result = facade.duplicate_contract_ctx(contract_id=1, ctx=ctx)
        assert result is expected

    def test_renew_advisor_contract_ctx(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        facade._access_policy = MagicMock()
        facade._admin_mutation_service = MagicMock()
        expected = MagicMock()
        facade._admin_mutation_service.renew_advisor_contract.return_value = expected

        ctx = MagicMock()
        ctx.user = MagicMock()
        ctx.org_access = {}
        ctx.perm_open_access = False

        result = facade.renew_advisor_contract_ctx(contract_id=1, ctx=ctx)
        assert result is expected

    def test_create_case_from_contract_ctx(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        facade._access_policy = MagicMock()
        facade._admin_mutation_service = MagicMock()
        expected = MagicMock()
        facade._admin_mutation_service.create_case_from_contract.return_value = expected

        ctx = MagicMock()
        ctx.user = MagicMock()
        ctx.org_access = {}
        ctx.perm_open_access = False

        result = facade.create_case_from_contract_ctx(contract_id=1, ctx=ctx)
        assert result is expected

    def test_update_contract_with_finance_ctx(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        facade._access_policy = MagicMock()
        facade._finance_mutation_service = MagicMock()
        expected = MagicMock()
        facade._finance_mutation_service.update_contract_with_finance.return_value = expected

        ctx = MagicMock()
        ctx.user = MagicMock()
        ctx.org_access = {}
        ctx.perm_open_access = False

        result = facade.update_contract_with_finance_ctx(
            contract_id=1,
            update_data={"name": "x"},
            ctx=ctx,
        )
        assert result is expected

    def test_update_contract_lawyers_ctx(self) -> None:
        from apps.contracts.services.contract.mutation.facade import ContractMutationFacade

        facade = ContractMutationFacade()
        facade._access_policy = MagicMock()
        facade._mutation_service = MagicMock()
        facade._query_service = MagicMock()
        contract = MagicMock()
        facade._query_service.get_contract_internal.return_value = contract

        ctx = MagicMock()
        ctx.user = MagicMock()
        ctx.org_access = {}
        ctx.perm_open_access = False

        result = facade.update_contract_lawyers_ctx(
            contract_id=1,
            lawyer_ids=[10],
            ctx=ctx,
        )
        assert result is contract
