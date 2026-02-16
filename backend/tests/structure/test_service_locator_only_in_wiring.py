from pathlib import Path


def test_selected_services_do_not_import_service_locator():
    root = Path(__file__).resolve().parents[2]
    targets = [
        root / "apps" / "cases" / "services" / "case" / "case_service.py",
        root / "apps" / "automation" / "services" / "sms" / "case_matcher.py",
        root / "apps" / "automation" / "services" / "sms" / "case_number_extractor_service.py",
        root / "apps" / "cases" / "services" / "party" / "case_party_service.py",
        root / "apps" / "cases" / "services" / "party" / "case_assignment_service.py",
        root / "apps" / "cases" / "services" / "template" / "case_template_binding_service.py",
        root / "apps" / "cases" / "services" / "template" / "folder_binding_service.py",
        root / "apps" / "documents" / "services" / "evidence_service.py",
        root / "apps" / "contracts" / "services" / "assignment" / "lawyer_assignment_service.py",
        root / "apps" / "contracts" / "services" / "contract" / "contract_service.py",
        root / "apps" / "contracts" / "services" / "contract" / "contract_service_adapter.py",
        root / "apps" / "contracts" / "services" / "payment" / "contract_payment_service.py",
        root / "apps" / "organization" / "services" / "org_access_computation_service.py",
    ]

    for path in targets:
        assert path.exists(), f"missing: {path}"
        content = path.read_text(encoding="utf-8")
        assert (
            "from apps.core.interfaces import ServiceLocator" not in content
        ), f"{path} should not import ServiceLocator"
