"""Unit tests for contracts.services.contract.contract_service module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestContractServiceInit:
    """测试 ContractService 初始化"""

    def test_init_with_defaults(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        assert svc.config is not None

    def test_init_with_custom_config(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        config = MagicMock()
        svc = ContractService(config=config)
        assert svc.config is config

    def test_init_stores_services(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        case_service = MagicMock()
        svc = ContractService(case_service=case_service)
        assert svc._case_service is case_service


class TestContractServiceProperties:
    """测试 ContractService 延迟初始化属性"""

    def test_query_service_lazy_init(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        # query_service should be None initially
        assert svc._query_service is None

    def test_access_policy_lazy_init(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        assert svc._access_policy is None

    def test_query_facade_lazy_init(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        assert svc._query_facade is None

    def test_workflow_service_lazy_init(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        assert svc._workflow_service is None

    def test_validator_lazy_init(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        assert svc._validator is None

    def test_mutation_service_lazy_init(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        assert svc._mutation_service is None

    def test_party_service_lazy_init(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        assert svc._party_service is None

    def test_finance_mutation_service_lazy_init(self) -> None:
        from apps.contracts.services.contract.contract_service import ContractService

        svc = ContractService()
        assert svc._finance_mutation_service is None
