"""Regression tests for case import dependency binding."""

from __future__ import annotations

from typing import Any

import pytest

from apps.cases.models import Case as CaseModel
from apps.cases.services.case_import_service import CaseImportService
from apps.contracts.models import Contract as ContractModel
from apps.contracts.services.contract_import_service import ContractImportService
from apps.testing.factories import ContractFactory


class _ClientResolverNoop:
    def resolve_with_attachments(self, data: dict[str, Any]) -> Any:
        return None


class _LawyerResolverNoop:
    def resolve(self, data: dict[str, Any]) -> Any:
        return None


class _ContractImportFake:
    def __init__(self, contract: Any) -> None:
        self.contract = contract
        self.calls: list[dict[str, Any]] = []

    def resolve(self, data: dict[str, Any]) -> Any:
        self.calls.append(data)
        return self.contract


@pytest.mark.django_db
def test_case_import_service_supports_late_contract_binding() -> None:
    service = CaseImportService(
        contract_import=None,
        client_resolve=_ClientResolverNoop(),
        lawyer_resolve=_LawyerResolverNoop(),
    )
    contract = ContractFactory(name="late-bind-contract")
    contract_import = _ContractImportFake(contract)
    service.bind_contract_import(contract_import)

    created_case = service.import_one(
        {
            "name": "late-bind-case",
            "contract": {
                "name": "nested-contract",
                "cases": [{"name": "should-be-ignored"}],
            },
        }
    )

    assert contract_import.calls == [{"name": "nested-contract"}]
    assert created_case.contract_id == contract.id


@pytest.mark.django_db
def test_case_import_service_keeps_old_behavior_without_contract_import() -> None:
    service = CaseImportService(
        contract_import=None,
        client_resolve=_ClientResolverNoop(),
        lawyer_resolve=_LawyerResolverNoop(),
    )

    created_case = service.import_one(
        {
            "name": "no-contract-import-case",
            "contract": {"name": "ignored-contract"},
        }
    )

    assert created_case.contract_id is None


@pytest.mark.django_db
def test_case_import_service_preserves_contract_cases_filtering_behavior() -> None:
    case_service = CaseImportService(
        contract_import=None,
        client_resolve=_ClientResolverNoop(),
        lawyer_resolve=_LawyerResolverNoop(),
    )
    contract_service = ContractImportService(
        client_resolve=_ClientResolverNoop(),
        lawyer_resolve=_LawyerResolverNoop(),
        case_import_fn=case_service.import_one,
    )
    case_service.bind_contract_import(contract_service)

    created_case = case_service.import_one(
        {
            "name": "root-case",
            "contract": {
                "name": "root-contract",
                "cases": [{"name": "should-not-be-imported"}],
            },
        }
    )

    assert created_case.contract_id is not None
    assert ContractModel.objects.filter(id=created_case.contract_id, name="root-contract").exists() is True
    assert CaseModel.objects.filter(name="should-not-be-imported").exists() is False
