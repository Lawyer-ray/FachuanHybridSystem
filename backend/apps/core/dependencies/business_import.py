"""Cross-app import service wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.cases.services.case_import_service import CaseImportService
    from apps.contracts.services.contract_import_service import ContractImportService


def build_case_and_contract_import_services_for_admin() -> tuple[CaseImportService, ContractImportService]:
    """Build paired import services with bidirectional binding for admin JSON import."""
    from apps.cases.services.case_import_service import CaseImportService
    from apps.client.services.client_resolve_service import ClientResolveService
    from apps.contracts.services.contract_import_service import ContractImportService
    from apps.organization.services.lawyer_resolve_service import LawyerResolveService

    client_svc = ClientResolveService()
    lawyer_svc = LawyerResolveService()
    case_svc = CaseImportService(contract_import=None, client_resolve=client_svc, lawyer_resolve=lawyer_svc)
    contract_svc = ContractImportService(
        client_resolve=client_svc,
        lawyer_resolve=lawyer_svc,
        case_import_fn=case_svc.import_one,
    )
    case_svc.bind_contract_import(contract_svc)
    return case_svc, contract_svc
