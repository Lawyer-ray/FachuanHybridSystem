"""Regression tests for contract import dependency binding."""

from __future__ import annotations

from typing import Any

import pytest

from apps.cases.models import Case
from apps.cases.services.case_import_service import CaseImportService
from apps.contracts.services.contract_import_service import ContractImportService


class _ClientResolverNoop:
    def resolve_with_attachments(self, data: dict[str, Any]) -> Any:
        return None


class _LawyerResolverNoop:
    def resolve(self, data: dict[str, Any]) -> Any:
        return None


@pytest.mark.django_db
def test_contract_import_service_supports_late_case_binding() -> None:
    service = ContractImportService(
        client_resolve=_ClientResolverNoop(),
        lawyer_resolve=_LawyerResolverNoop(),
        case_import_fn=None,
    )
    captured_calls: list[tuple[str, int]] = []

    def _case_import(case_data: dict[str, Any], contract: Any) -> Any:
        captured_calls.append((str(case_data.get("name")), int(contract.id)))
        return None

    service.bind_case_import(_case_import)

    contract = service.resolve(
        {
            "name": "late-bind-contract",
            "cases": [{"name": "nested-case"}],
        }
    )

    assert captured_calls == [("nested-case", contract.id)]


@pytest.mark.django_db
def test_contract_import_service_keeps_old_behavior_without_case_import() -> None:
    service = ContractImportService(
        client_resolve=_ClientResolverNoop(),
        lawyer_resolve=_LawyerResolverNoop(),
        case_import_fn=None,
    )

    contract = service.resolve(
        {
            "name": "no-case-import-contract",
            "cases": [{"name": "ignored-case"}],
        }
    )

    assert contract.id is not None
    assert Case.objects.filter(name="ignored-case").exists() is False


@pytest.mark.django_db
def test_contract_import_service_imports_cases_when_case_import_is_bound() -> None:
    case_service = CaseImportService(
        contract_import=None,
        client_resolve=_ClientResolverNoop(),
        lawyer_resolve=_LawyerResolverNoop(),
    )
    service = ContractImportService(
        client_resolve=_ClientResolverNoop(),
        lawyer_resolve=_LawyerResolverNoop(),
        case_import_fn=case_service.import_one,
    )
    case_service.bind_contract_import(service)

    contract = service.resolve(
        {
            "name": "contract-with-cases",
            "cases": [{"name": "imported-case"}],
        }
    )

    assert contract.id is not None
    assert Case.objects.filter(name="imported-case", contract_id=contract.id).exists() is True
