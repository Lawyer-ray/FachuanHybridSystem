from __future__ import annotations


def test_cases_build_case_service_requires_explicit_contract_service():
    from apps.cases.services.case.composition import build_case_service

    dummy_contract_service = object()
    service = build_case_service(contract_service=dummy_contract_service)  # type: ignore[arg-type]
    assert service.contract_service is dummy_contract_service


def test_contract_wiring_uses_service_locator_contract_service(monkeypatch):
    from apps.contracts.services.contract import wiring

    class _Adapter:
        def __init__(self):
            self.contract_service = object()

    adapter = _Adapter()
    monkeypatch.setattr(wiring.ServiceLocator, "get_contract_service", lambda: adapter)

    assert wiring.get_contract_domain_service() is adapter.contract_service
