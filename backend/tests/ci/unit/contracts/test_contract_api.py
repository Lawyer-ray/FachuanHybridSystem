"""Unit tests for contracts.api.contract_api module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestContractApiModule:
    """测试 contract_api 模块结构"""

    def test_router_exists(self) -> None:
        from apps.contracts.api.contract_api import router
        assert router is not None

    def test_get_contract_service_callable(self) -> None:
        from apps.contracts.api.contract_api import _get_contract_service
        assert callable(_get_contract_service)

    def test_get_domain_service_callable(self) -> None:
        from apps.contracts.api.contract_api import _get_domain_service
        assert callable(_get_domain_service)


class TestContractApiEndpoints:
    """测试 contract API 端点函数存在"""

    def test_list_contracts_endpoint(self) -> None:
        from apps.contracts.api.contract_api import list_contracts
        assert callable(list_contracts)

    def test_get_contract_endpoint(self) -> None:
        from apps.contracts.api.contract_api import get_contract
        assert callable(get_contract)

    def test_create_contract_endpoint(self) -> None:
        from apps.contracts.api.contract_api import create_contract
        assert callable(create_contract)

    def test_update_contract_endpoint(self) -> None:
        from apps.contracts.api.contract_api import update_contract
        assert callable(update_contract)

    def test_delete_contract_endpoint(self) -> None:
        from apps.contracts.api.contract_api import delete_contract
        assert callable(delete_contract)

    def test_create_contract_with_cases_endpoint(self) -> None:
        from apps.contracts.api.contract_api import create_contract_with_cases
        assert callable(create_contract_with_cases)

    def test_update_contract_lawyers_endpoint(self) -> None:
        from apps.contracts.api.contract_api import update_contract_lawyers
        assert callable(update_contract_lawyers)

    def test_get_contract_all_parties_endpoint(self) -> None:
        from apps.contracts.api.contract_api import get_contract_all_parties
        assert callable(get_contract_all_parties)


class TestContractWithCasesIn:
    """测试 ContractWithCasesIn schema"""

    def test_has_cases_field(self) -> None:
        from apps.contracts.api.contract_api import ContractWithCasesIn
        fields = ContractWithCasesIn.model_fields
        assert "cases" in fields
